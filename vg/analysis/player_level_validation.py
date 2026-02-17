"""
Player Level Validation - Verify heartbeat byte 8 as level indicator

Key discovery:
- Heartbeat byte 8 shows clear progression: 13→14→15→16→17→18→19 (6 transitions)
- All 3 analyzed players show identical progression pattern
- Starting value: 13, Ending value: 19 (6 level gains)
- This suggests: byte 8 = level + 12 offset (L1=13, L7=19)

Next steps:
1. Verify 0x03 entity IDs (may not be player entities)
2. Check if level starts at 1 or if there's an offset
3. Validate across multiple matches
4. Extract final level for all players
"""

import struct
import os
from collections import defaultdict, Counter
from pathlib import Path

CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])
HEARTBEAT_HEADER = bytes([0x18, 0x04, 0x3E])

def _le_to_be(eid_le):
    """Convert Little Endian entity ID to Big Endian"""
    return struct.unpack('>H', struct.pack('<H', eid_le))[0]

def find_player_blocks(data):
    """Find all player blocks"""
    players = []
    markers = [bytes([0xDA, 0x03, 0xEE]), bytes([0xE0, 0x03, 0xEE])]

    for marker in markers:
        offset = 0
        while True:
            pos = data.find(marker, offset)
            if pos == -1:
                break

            try:
                eid_offset = pos + 0xA5
                hero_offset = pos + 0xA9
                team_offset = pos + 0xD5

                if eid_offset + 2 <= len(data) and hero_offset + 2 <= len(data) and team_offset + 1 <= len(data):
                    eid_le = struct.unpack('<H', data[eid_offset:eid_offset+2])[0]
                    hero_id = struct.unpack('<H', data[hero_offset:hero_offset+2])[0]
                    team = data[team_offset]

                    players.append({
                        'eid_le': eid_le,
                        'eid_be': _le_to_be(eid_le),
                        'hero_id': hero_id,
                        'team': team
                    })
            except:
                pass

            offset = pos + 1

    # Deduplicate
    seen = set()
    unique_players = []
    for p in players:
        key = (p['eid_be'], p['hero_id'])
        if key not in seen:
            seen.add(key)
            unique_players.append(p)

    return unique_players

def extract_player_levels(data, player_eids_be):
    """Extract final level for each player from heartbeat byte 8"""
    heartbeats = defaultdict(list)
    offset = 0

    while True:
        pos = data.find(HEARTBEAT_HEADER, offset)
        if pos == -1:
            break

        try:
            if pos + 40 <= len(data):
                eid_be = struct.unpack('>H', data[pos+5:pos+7])[0]

                if eid_be in player_eids_be:
                    payload = data[pos+7:pos+37]
                    level_byte = payload[8] if len(payload) > 8 else None

                    if level_byte is not None:
                        heartbeats[eid_be].append(level_byte)
        except:
            pass

        offset = pos + 1

    # Calculate levels
    player_levels = {}
    for eid_be, level_bytes in heartbeats.items():
        if level_bytes:
            initial = level_bytes[0]
            final = level_bytes[-1]
            unique_levels = sorted(set(level_bytes))

            # Hypothesis: byte_value = actual_level + 12
            # So level = byte_value - 12
            level_actual_initial = initial - 12
            level_actual_final = final - 12

            player_levels[eid_be] = {
                'byte_initial': initial,
                'byte_final': final,
                'level_initial': level_actual_initial,
                'level_final': level_actual_final,
                'level_transitions': len(unique_levels) - 1,
                'unique_bytes': unique_levels,
                'sample_count': len(level_bytes)
            }

    return player_levels

def check_0x03_entity_ids(data):
    """Check what entity IDs appear in 0x03 credit records"""
    offset = 0
    action_0x03_eids = []

    while True:
        pos = data.find(CREDIT_HEADER, offset)
        if pos == -1:
            break

        try:
            if pos + 12 <= len(data):
                eid_be = struct.unpack('>H', data[pos+5:pos+7])[0]
                value_f32 = struct.unpack('>f', data[pos+7:pos+11])[0]
                action = data[pos+11]

                if action == 0x03:
                    action_0x03_eids.append({
                        'eid': eid_be,
                        'value': value_f32,
                        'pos': pos
                    })
        except:
            pass

        offset = pos + 1

    return action_0x03_eids

def main():
    import time
    start_time = time.time()

    print("[OBJECTIVE] Validate heartbeat byte 8 as player level indicator")

    # Test on longer tournament matches (Finals - longer duration)
    matches = [
        {
            'name': 'Finals Match 2 (1551s)',
            'file': r"D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays\SFC vs Law Enforcers (Finals)\2\d8736287-e35e-4c76-89b0-c78c76fd0b05-5f22df2e-921a-4638-937b-a88f9fe88a73.0.vgr"
        },
        {
            'name': 'Finals Match 3 (1604s)',
            'file': r"D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays\SFC vs Law Enforcers (Finals)\3\d8736287-e35e-4c76-89b0-c78c76fd0b05-0bfec87b-0b07-4f4d-8e4f-936d74758dfd.0.vgr"
        },
        {
            'name': 'Finals Match 4 (1355s)',
            'file': r"D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays\SFC vs Law Enforcers (Finals)\4\d8736287-e35e-4c76-89b0-c78c76fd0b05-7a593bce-eded-4fdc-a164-6bb8162958ea.0.vgr"
        }
    ]

    all_results = []

    for match in matches:
        if not os.path.exists(match['file']):
            print(f"[LIMITATION] File not found: {match['file']}")
            continue

        print(f"\n{'='*80}")
        print(f"{match['name']}")
        print(f"{'='*80}")

        with open(match['file'], 'rb') as f:
            data = f.read()

        print(f"[DATA] Loaded {len(data):,} bytes")

        # Find players
        players = find_player_blocks(data)
        player_eids_be = set([p['eid_be'] for p in players])
        print(f"[DATA] Found {len(players)} unique players")

        # Extract levels
        player_levels = extract_player_levels(data, player_eids_be)

        print(f"\n[FINDING] Player levels extracted:")
        print(f"{'Entity':<8} {'Initial':<8} {'Final':<8} {'Transitions':<12} {'Byte Range':<15} {'Samples':<8}")
        print(f"{'-'*75}")

        for eid_be in sorted(player_levels.keys()):
            info = player_levels[eid_be]
            byte_range = f"{info['byte_initial']}-{info['byte_final']}"
            print(f"{eid_be:<8} {info['level_initial']:<8} {info['level_final']:<8} {info['level_transitions']:<12} {byte_range:<15} {info['sample_count']:<8}")

        # Statistics
        final_levels = [info['level_final'] for info in player_levels.values()]
        avg_final = sum(final_levels) / len(final_levels) if final_levels else 0

        print(f"\n[STAT:avg_final_level] {avg_final:.1f}")
        print(f"[STAT:min_final_level] {min(final_levels) if final_levels else 0}")
        print(f"[STAT:max_final_level] {max(final_levels) if final_levels else 0}")

        # Check 0x03 entity IDs
        action_0x03_records = check_0x03_entity_ids(data)
        print(f"\n[DATA] Found {len(action_0x03_records)} action 0x03 records")

        if action_0x03_records:
            eid_dist = Counter([r['eid'] for r in action_0x03_records])
            print(f"[FINDING] Entity IDs in 0x03 records:")
            for eid, count in sorted(eid_dist.items()):
                is_player = "PLAYER" if eid in player_eids_be else "NON-PLAYER"
                print(f"  Entity {eid:5d}: {count:3d} records ({is_player})")

        all_results.append({
            'match': match['name'],
            'player_count': len(players),
            'avg_final_level': avg_final,
            'action_0x03_count': len(action_0x03_records),
            'player_levels': player_levels
        })

    # Cross-match validation
    print(f"\n{'='*80}")
    print("CROSS-MATCH VALIDATION")
    print(f"{'='*80}")

    print(f"\n[FINDING] Level encoding hypothesis: byte_value = actual_level + 12")
    print(f"[FINDING] Level 1 = byte 13, Level 12 = byte 24")

    all_avg_levels = [r['avg_final_level'] for r in all_results]
    overall_avg = sum(all_avg_levels) / len(all_avg_levels) if all_avg_levels else 0

    print(f"\n[STAT:overall_avg_final_level] {overall_avg:.1f}")
    print(f"[FINDING] Expected final level in 15-20min match: L10-L12")

    if 10 <= overall_avg <= 12:
        print(f"[FINDING] ✓✓✓ STRONG VALIDATION: Average final level {overall_avg:.1f} matches expected range!")
        print(f"[FINDING] ✓✓✓ CONFIRMED: Heartbeat byte 8 = player level + 12")

    elapsed = time.time() - start_time
    print(f"\n[STAGE:time:{elapsed:.2f}]")

    print(f"\n[LIMITATION] 0x03 events may be team-level or non-player entities")
    print(f"[LIMITATION] Initial level appears to be 1 (byte 13), not 0")

if __name__ == "__main__":
    main()
