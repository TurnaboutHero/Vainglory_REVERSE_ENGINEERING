"""
Validate heartbeat offset +27 as damage dealt metric

Hypothesis: Offset +27 in [18 04 3E] player heartbeat accumulates damage dealt

Validation approach:
1. Extract final offset +27 values for all players
2. Compare with player performance (kills, winner)
3. Check if values correlate with expected damage hierarchy
"""

import struct
from pathlib import Path
from collections import defaultdict
import json

def extract_final_damage_values(replay_dir: str):
    """Extract final offset +27 values from last frames"""

    print(f"\n=== Final Damage Values (Offset +27) ===")

    replay_path = Path(replay_dir)
    frame_files = sorted(replay_path.glob('*.vgr'))

    heartbeat_header = bytes([0x18, 0x04, 0x3E])

    # Track latest value for each player
    player_damage = {}

    # Scan last 10 frames
    for frame_file in frame_files[-10:]:
        data = frame_file.read_bytes()

        pos = 0
        while True:
            pos = data.find(heartbeat_header, pos)
            if pos == -1:
                break

            if pos + 35 <= len(data):  # Need offset +27 (+4 bytes)
                try:
                    eid_be = struct.unpack('>H', data[pos+5:pos+7])[0]

                    if 50000 <= eid_be <= 60000:
                        # Read offset +27
                        damage = struct.unpack('>f', data[pos+27:pos+31])[0]

                        if 0 <= damage <= 100000:
                            player_damage[eid_be] = damage
                except:
                    pass

            pos += 1

    print(f"Players with damage data: {len(player_damage)}")
    for eid, damage in sorted(player_damage.items(), key=lambda x: -x[1]):
        print(f"  Entity {eid}: {damage:.2f}")

    return player_damage

def correlate_with_match_truth(replay_name: str, player_damage: dict):
    """Correlate damage values with truth data"""

    print(f"\n=== Correlation with Truth Data ===")

    # Load truth
    truth_path = Path(__file__).parent.parent / "output" / "tournament_truth.json"
    with open(truth_path) as f:
        truth_data = json.load(f)

    # Find matching replay
    match_data = None
    for match in truth_data['matches']:
        if replay_name in match['replay_file']:
            match_data = match
            break

    if not match_data:
        print("Match not found in truth data")
        return

    print(f"Match: {match_data['match_info']['score_left']}-{match_data['match_info']['score_right']}")
    print(f"Winner: {match_data['match_info']['winner']}")

    # Get player stats
    players = match_data['players']
    print(f"\nPlayer stats:")
    print(f"{'Player':<20} {'Team':<6} {'K/D/A':<10} {'Damage (offset+27)':<20}")
    print(f"{'-'*70}")

    for player_name, stats in players.items():
        kda = f"{stats['kills']}/{stats['deaths']}/{stats['assists']}"
        team = stats['team']

        # Try to find matching damage value (we don't have eid->player mapping yet)
        # Just show all available damage values
        damage_str = "Unknown (need eid mapping)"

        print(f"{player_name:<20} {team:<6} {kda:<10} {damage_str}")

    print(f"\nAvailable damage values:")
    for eid, damage in sorted(player_damage.items(), key=lambda x: -x[1]):
        print(f"  Entity {eid}: {damage:.2f}")

    # Summary statistics
    if player_damage:
        values = list(player_damage.values())
        total_damage = sum(values)
        avg_damage = total_damage / len(values)
        print(f"\nDamage statistics:")
        print(f"  Total: {total_damage:.2f}")
        print(f"  Average per player: {avg_damage:.2f}")
        print(f"  Min: {min(values):.2f}")
        print(f"  Max: {max(values):.2f}")

def scan_all_heartbeat_offsets(replay_dir: str):
    """Scan ALL offsets in heartbeat payload to find other accumulating stats"""

    print(f"\n=== All Heartbeat Offset Analysis ===")

    replay_path = Path(replay_dir)
    frame_files = sorted(replay_path.glob('*.vgr'))

    heartbeat_header = bytes([0x18, 0x04, 0x3E])

    # Track sequences for each offset
    offset_sequences = defaultdict(lambda: defaultdict(list))

    # Sample frames throughout match
    sample_frames = [0, 20, 40, 60, 80, len(frame_files)-1]

    for frame_idx in sample_frames:
        if frame_idx >= len(frame_files):
            continue

        data = frame_files[frame_idx].read_bytes()

        pos = 0
        while True:
            pos = data.find(heartbeat_header, pos)
            if pos == -1:
                break

            if pos + 39 <= len(data):
                try:
                    eid_be = struct.unpack('>H', data[pos+5:pos+7])[0]

                    if 50000 <= eid_be <= 60000:
                        # Read all float offsets
                        for offset in range(7, 39, 4):
                            if pos + offset + 4 <= len(data):
                                value = struct.unpack('>f', data[pos+offset:pos+offset+4])[0]

                                if 0 <= value <= 100000:
                                    offset_sequences[offset][eid_be].append({
                                        'frame': frame_idx,
                                        'value': value
                                    })
                except:
                    pass

            pos += 1

    # Find accumulating offsets
    print(f"\nAccumulating offsets (potential stats):")
    for offset in sorted(offset_sequences.keys()):
        sequences = offset_sequences[offset]

        # Check if any player shows accumulation
        accumulating_count = 0
        max_growth = 0

        for eid, sequence in sequences.items():
            if len(sequence) >= 4:
                values = [s['value'] for s in sequence]
                growth = values[-1] - values[0]

                if growth > 500:  # Significant growth
                    accumulating_count += 1
                    max_growth = max(max_growth, growth)

        if accumulating_count > 0:
            print(f"  Offset +{offset}: {accumulating_count} players accumulating, max growth: {max_growth:.2f}")

def main():
    match1_dir = Path("D:/Desktop/My Folder/Game/VG/vg replay/Tournament_Replays/SFC vs Team Stooopid (Semi)/1")

    if not match1_dir.exists():
        print(f"Directory not found: {match1_dir}")
        return

    replay_name = "d8736287-e35e-4c76-89b0-c78c76fd0b05-8c6e1a3e-68a0-4853-8786-44c899ff1e8a"

    # Extract damage values
    player_damage = extract_final_damage_values(str(match1_dir))

    # Correlate with truth
    correlate_with_match_truth(replay_name, player_damage)

    # Scan all offsets
    scan_all_heartbeat_offsets(str(match1_dir))

    print("\n[CONCLUSION]")
    print("If offset +27 shows:")
    print("  - Higher values for carries (high kill players)")
    print("  - Higher total for winning team")
    print("  - Reasonable range (10k-50k per player)")
    print("Then offset +27 is likely DAMAGE DEALT")

if __name__ == '__main__':
    main()
