"""
Search for damage stats in player heartbeat [18 04 3E] and player action [28 04 3F] events

Strategy: Track accumulating float values that could represent total damage dealt/taken
"""

import struct
from pathlib import Path
from collections import defaultdict
import numpy as np

def analyze_player_heartbeat_payload(replay_dir: str):
    """Analyze player heartbeat [18 04 3E] 32-byte payload for damage stats"""

    print(f"\n=== Player Heartbeat Payload Analysis ===")

    replay_path = Path(replay_dir)
    frame_files = sorted(replay_path.glob('*.vgr'))

    heartbeat_header = bytes([0x18, 0x04, 0x3E])

    # Track each player's heartbeat sequence
    player_sequences = defaultdict(lambda: defaultdict(list))

    frames_to_check = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90]  # Sample throughout match

    for frame_idx in frames_to_check:
        if frame_idx >= len(frame_files):
            break

        data = frame_files[frame_idx].read_bytes()

        pos = 0
        while True:
            pos = data.find(heartbeat_header, pos)
            if pos == -1:
                break

            if pos + 39 <= len(data):  # Header(3) + padding(2) + eid(2) + payload(32)
                try:
                    eid_be = struct.unpack('>H', data[pos+5:pos+7])[0]

                    # Only track player entities
                    if 50000 <= eid_be <= 60000:
                        # Read floats at 4-byte intervals in payload
                        for offset in range(7, 39, 4):
                            if pos + offset + 4 <= len(data):
                                value = struct.unpack('>f', data[pos+offset:pos+offset+4])[0]

                                # Only track reasonable stat values
                                if 0 <= value <= 100000 and not np.isnan(value) and not np.isinf(value):
                                    player_sequences[eid_be][offset].append({
                                        'frame': frame_idx,
                                        'value': value
                                    })
                except:
                    pass

            pos += 1

    # Analyze sequences for accumulating patterns
    print(f"\nAnalyzed {len(player_sequences)} player entities across {len(frames_to_check)} frames")

    # For each player, find offsets with accumulating values
    for eid, offset_sequences in sorted(player_sequences.items()):
        print(f"\nPlayer entity {eid}:")

        for offset in sorted(offset_sequences.keys()):
            sequence = offset_sequences[offset]

            if len(sequence) >= 5:
                values = [s['value'] for s in sequence]

                # Check if mostly increasing (damage dealt accumulator)
                increasing = sum(1 for i in range(1, len(values)) if values[i] >= values[i-1])
                increasing_pct = increasing / (len(values) - 1) * 100 if len(values) > 1 else 0

                # Check total growth
                growth = values[-1] - values[0]

                # Potential damage stat: accumulating, grows by 1000+
                if increasing_pct > 70 and growth > 1000:
                    print(f"  Offset +{offset}: {values[0]:.1f} -> {values[-1]:.1f} "
                          f"(growth: {growth:.1f}, increasing: {increasing_pct:.0f}%)")
                    print(f"    Sequence: {[f'{v:.1f}' for v in values]}")

def analyze_player_action_events(replay_dir: str):
    """Analyze player action [28 04 3F] 48-byte events for damage values"""

    print(f"\n=== Player Action Event Analysis ===")

    replay_path = Path(replay_dir)
    frame_files = sorted(replay_path.glob('*.vgr'))

    action_header = bytes([0x28, 0x04, 0x3F])

    # Sample middle of match for action diversity
    frame_idx = len(frame_files) // 2
    if frame_idx >= len(frame_files):
        frame_idx = len(frame_files) - 1

    data = frame_files[frame_idx].read_bytes()

    action_count = data.count(action_header)
    print(f"Frame {frame_idx}: {action_count} player action events")

    # Parse first 20
    pos = 0
    for i in range(min(20, action_count)):
        pos = data.find(action_header, pos)
        if pos == -1:
            break

        if pos + 51 <= len(data):  # Header(3) + padding(2) + eid(2) + payload(48)
            try:
                eid_be = struct.unpack('>H', data[pos+5:pos+7])[0]

                # Only show player entities
                if 50000 <= eid_be <= 60000:
                    # Look for large floats in payload
                    large_floats = []
                    for offset in range(7, 51, 4):
                        if pos + offset + 4 <= len(data):
                            value = struct.unpack('>f', data[pos+offset:pos+offset+4])[0]
                            if 50 <= value <= 5000:  # Damage-like range
                                large_floats.append((offset, value))

                    if large_floats:
                        print(f"  eid {eid_be}: {len(large_floats)} damage-like floats")
                        for off, val in large_floats[:3]:
                            print(f"    offset +{off}: {val:.2f}")
            except:
                pass

        pos += 1

def search_all_player_events(replay_dir: str):
    """Search for ALL event types containing player entity IDs"""

    print(f"\n=== Player Event Type Discovery ===")

    replay_path = Path(replay_dir)
    frame_file = sorted(replay_path.glob('*.vgr'))[50]  # Mid-match frame

    data = frame_file.read_bytes()

    # Find all positions with player entity IDs (50000-60000 BE)
    player_event_headers = defaultdict(int)

    for i in range(len(data) - 20):
        try:
            eid_be = struct.unpack('>H', data[i:i+2])[0]

            if 50000 <= eid_be <= 60000:
                # Get 3-byte header before entity ID
                if i >= 5:
                    header = bytes(data[i-5:i-2])
                    if header[1] == 0x04:  # Common event pattern
                        player_event_headers[header] += 1
        except:
            pass

    print(f"Event headers containing player entity IDs:")
    for header, count in sorted(player_event_headers.items(), key=lambda x: -x[1])[:15]:
        print(f"  {header.hex(' ').upper()}: {count:5d} occurrences")

def main():
    match1_dir = Path("D:/Desktop/My Folder/Game/VG/vg replay/Tournament_Replays/SFC vs Team Stooopid (Semi)/1")

    if match1_dir.exists():
        analyze_player_heartbeat_payload(str(match1_dir))
        analyze_player_action_events(str(match1_dir))
        search_all_player_events(str(match1_dir))
    else:
        print(f"Directory not found: {match1_dir}")

if __name__ == '__main__':
    main()
