"""
Search for player damage in credit records and other event types

Focus: Find action bytes or event headers that:
1. Appear on PLAYER entities (50000-60000 range)
2. Have large float values (damage range: 50-2000)
3. Occur frequently (100+ per player per match)
"""

import struct
from pathlib import Path
from collections import defaultdict, Counter
import json

def find_player_credit_actions(replay_path: str):
    """Find all credit action bytes that appear on PLAYER entities"""
    print(f"\n=== Player Credit Actions: {Path(replay_path).name} ===")

    data = Path(replay_path).read_bytes()
    credit_header = bytes([0x10, 0x04, 0x1D])

    positions = []
    start = 0
    while True:
        pos = data.find(credit_header, start)
        if pos == -1:
            break
        positions.append(pos)
        start = pos + 1

    player_action_bytes = Counter()
    player_action_examples = defaultdict(list)

    for pos in positions:
        if pos + 12 <= len(data):
            eid_be = struct.unpack('>H', data[pos+5:pos+7])[0]
            value = struct.unpack('>f', data[pos+7:pos+11])[0]
            action_byte = data[pos+11]

            # Only track PLAYER entities
            if 50000 <= eid_be <= 60000:
                player_action_bytes[action_byte] += 1

                if len(player_action_examples[action_byte]) < 5:
                    player_action_examples[action_byte].append({
                        'eid': eid_be,
                        'value': value,
                        'pos': pos
                    })

    print(f"\nPlayer entity credit actions:")
    print(f"{'Action':>8} | {'Count':>6} | {'Value Range':>20} | {'Examples'}")
    print(f"{'-'*8}-+-{'-'*6}-+-{'-'*20}-+-{'-'*40}")

    for action_byte in sorted(player_action_bytes.keys()):
        count = player_action_bytes[action_byte]
        examples = player_action_examples[action_byte]

        values = [e['value'] for e in examples]
        val_range = f"[{min(values):.1f}, {max(values):.1f}]"
        example_str = f"eid={examples[0]['eid']} val={examples[0]['value']:.1f}"

        print(f"  0x{action_byte:02X}   | {count:6d} | {val_range:>20} | {example_str}")

    return player_action_bytes, player_action_examples

def search_large_float_events(replay_path: str):
    """Search for ANY event headers with large float values on player entities"""
    print(f"\n=== Large Float Event Search ===")

    data = Path(replay_path).read_bytes()

    # Pattern: look for player entity IDs (50000-60000 BE) followed by large floats
    candidate_patterns = Counter()

    for i in range(len(data) - 15):
        # Try to read entity ID at current position
        try:
            eid_be = struct.unpack('>H', data[i:i+2])[0]

            # If it's a player entity
            if 50000 <= eid_be <= 60000:
                # Look for large float within next 8 bytes
                for offset in [2, 4, 6]:
                    if i + offset + 4 <= len(data):
                        try:
                            value = struct.unpack('>f', data[i+offset:i+offset+4])[0]

                            # Damage-like: 50-2000 range
                            if 50 <= value <= 2000:
                                # Get 3-byte header before this entity ID
                                if i >= 5:
                                    header = bytes(data[i-5:i-2])
                                    if header[1] == 0x04:  # Common event pattern
                                        candidate_patterns[header] += 1
                        except:
                            pass
        except:
            pass

    print(f"\nEvent headers with player eids + damage-like floats (50-2000):")
    for header, count in sorted(candidate_patterns.items(), key=lambda x: -x[1])[:15]:
        print(f"  {header.hex(' ').upper()}: {count:6d} occurrences")

    return candidate_patterns

def analyze_player_action_bytes_detailed(replay_path: str, player_action_bytes: dict,
                                        player_action_examples: dict, match_info: dict):
    """Deep analysis of player-specific action bytes"""
    print(f"\n=== Player Action Byte Deep Analysis ===")

    # Known action bytes
    known = {
        0x06: "gold income",
        0x08: "passive gold",
        0x0E: "minion kill",
        0x0F: "minion gold",
        0x0D: "jungle"
    }

    # Analyze unknown player action bytes
    unknown_actions = [ab for ab in player_action_bytes.keys() if ab not in known]

    if not unknown_actions:
        print("No unknown player action bytes found")
        return

    print(f"\nUnknown player action bytes: {[f'0x{ab:02X}' for ab in unknown_actions]}")

    data = Path(replay_path).read_bytes()
    credit_header = bytes([0x10, 0x04, 0x1D])

    # Extract ALL records for unknown actions
    for action_byte in unknown_actions:
        print(f"\n--- Action 0x{action_byte:02X} Analysis ---")

        positions = []
        start = 0
        while True:
            pos = data.find(credit_header, start)
            if pos == -1:
                break
            positions.append(pos)
            start = pos + 1

        records = []
        for pos in positions:
            if pos + 12 <= len(data):
                eid_be = struct.unpack('>H', data[pos+5:pos+7])[0]
                value = struct.unpack('>f', data[pos+7:pos+11])[0]
                ab = data[pos+11]

                if ab == action_byte and 50000 <= eid_be <= 60000:
                    records.append({
                        'eid': eid_be,
                        'value': value,
                        'pos': pos
                    })

        print(f"Total occurrences: {len(records)}")

        if records:
            values = [r['value'] for r in records]
            print(f"Value stats: min={min(values):.2f}, max={max(values):.2f}, mean={sum(values)/len(values):.2f}")

            # Per-player counts
            player_counts = Counter([r['eid'] for r in records])
            print(f"Per-player distribution:")
            for eid, count in player_counts.most_common(10):
                avg_value = sum(r['value'] for r in records if r['eid'] == eid) / count
                print(f"  eid {eid}: {count:4d} occurrences, avg value: {avg_value:.2f}")

            # Sample records
            print(f"Sample records:")
            for r in records[:5]:
                print(f"  eid={r['eid']:5d}, value={r['value']:8.2f}")

def search_for_damage_dealt_total(replay_path: str, match_info: dict):
    """Try to estimate total damage dealt from various sources"""
    print(f"\n=== Damage Dealt Estimation ===")

    # Expected damage range: avg 20k-50k per player in 15-20min match
    # Total match damage: ~200k-500k

    data = Path(replay_path).read_bytes()
    credit_header = bytes([0x10, 0x04, 0x1D])

    positions = []
    start = 0
    while True:
        pos = data.find(credit_header, start)
        if pos == -1:
            break
        positions.append(pos)
        start = pos + 1

    # Sum all positive credit values on player entities
    player_positive_credits = defaultdict(float)

    for pos in positions:
        if pos + 12 <= len(data):
            eid_be = struct.unpack('>H', data[pos+5:pos+7])[0]
            value = struct.unpack('>f', data[pos+7:pos+11])[0]
            action_byte = data[pos+11]

            if 50000 <= eid_be <= 60000 and value > 0:
                player_positive_credits[eid_be] += value

    print(f"\nTotal positive credit values by player entity:")
    for eid, total in sorted(player_positive_credits.items(), key=lambda x: -x[1]):
        print(f"  eid {eid:5d}: {total:10.2f}")

    total_all = sum(player_positive_credits.values())
    print(f"\nTotal across all players: {total_all:.2f}")

    # Compare with known stats
    players = match_info.get('players', {})
    total_gold = sum(p.get('gold', 0) for p in players.values())
    print(f"Total gold from truth: {total_gold}")
    print(f"Ratio (credits/gold): {total_all/total_gold if total_gold > 0 else 'N/A'}")

def main():
    # Load truth data
    truth_path = Path(__file__).parent.parent / "output" / "tournament_truth.json"
    with open(truth_path) as f:
        truth_data = json.load(f)

    # Analyze first 4 matches
    matches = truth_data['matches'][:4]

    for i, match in enumerate(matches):
        replay_path = match['replay_file']
        print(f"\n{'='*80}")
        print(f"MATCH {i+1}: {Path(replay_path).stem}")
        print(f"Duration: {match['match_info']['duration_seconds']}s, "
              f"Score: {match['match_info']['score_left']}-{match['match_info']['score_right']}")
        print(f"{'='*80}")

        # Find player credit actions
        player_action_bytes, player_action_examples = find_player_credit_actions(replay_path)

        # Detailed analysis
        analyze_player_action_bytes_detailed(replay_path, player_action_bytes,
                                            player_action_examples, match)

        # Search for large float events
        candidate_patterns = search_large_float_events(replay_path)

        # Damage estimation
        search_for_damage_dealt_total(replay_path, match)

        print(f"\n{'='*80}\n")

    print("\n[CONCLUSION]")
    print("If no player-specific action bytes with damage-like values found,")
    print("damage data may be in:")
    print("1. Player heartbeat [18 04 3E] payload")
    print("2. Player action [28 04 3F] events")
    print("3. Separate damage event headers not yet discovered")
    print("4. NOT stored in replay files at all")

if __name__ == '__main__':
    main()
