"""
Deep dive into credit action bytes 0x02 and 0x03 - potential damage indicators

Key observations from initial scan:
- 0x02: 448-520 occurrences, values 6.3-15.2, mean ~10
- 0x03: 169 occurrences, always value=1.0
- These are NOT in documented list (0x06/0x08/0x0E/0x0F/0x0D/0x04)
"""

import struct
from pathlib import Path
from collections import defaultdict, Counter
import json

def analyze_action_02_and_03(replay_path: str, match_info: dict):
    """Deep analysis of action bytes 0x02 and 0x03"""
    print(f"\n=== Action 0x02/0x03 Deep Dive: {Path(replay_path).name} ===")

    data = Path(replay_path).read_bytes()
    credit_header = bytes([0x10, 0x04, 0x1D])

    # Find all credit records
    positions = []
    start = 0
    while True:
        pos = data.find(credit_header, start)
        if pos == -1:
            break
        positions.append(pos)
        start = pos + 1

    # Parse all credits
    action_02_records = []
    action_03_records = []

    for pos in positions:
        if pos + 12 <= len(data):
            eid_be = struct.unpack('>H', data[pos+5:pos+7])[0]
            value = struct.unpack('>f', data[pos+7:pos+11])[0]
            action_byte = data[pos+11]

            # Read timestamp if available (7 bytes before header)
            timestamp = None
            if pos >= 7:
                try:
                    timestamp = struct.unpack('>f', data[pos-4:pos])[0]
                except:
                    pass

            record = {
                'pos': pos,
                'eid': eid_be,
                'value': value,
                'timestamp': timestamp
            }

            if action_byte == 0x02:
                action_02_records.append(record)
            elif action_byte == 0x03:
                action_03_records.append(record)

    print(f"\nAction 0x02: {len(action_02_records)} records")
    print(f"Action 0x03: {len(action_03_records)} records")

    # Analyze 0x02
    if action_02_records:
        print(f"\n--- Action 0x02 Analysis ---")

        # Entity distribution
        eid_counts = Counter([r['eid'] for r in action_02_records])
        print(f"Unique entities: {len(eid_counts)}")
        print(f"Top entities:")
        for eid, count in eid_counts.most_common(10):
            entity_type = "player" if 50000 <= eid <= 60000 else "structure" if 1000 <= eid <= 20000 else "other"
            print(f"  eid {eid:5d} ({entity_type}): {count:3d} occurrences")

        # Value statistics
        values = [r['value'] for r in action_02_records]
        print(f"\nValue stats: min={min(values):.2f}, max={max(values):.2f}, mean={sum(values)/len(values):.2f}")

        # Sample records
        print(f"\nSample records (first 10):")
        for r in action_02_records[:10]:
            ts_str = f"{r['timestamp']:.2f}" if r['timestamp'] else "N/A"
            print(f"  eid={r['eid']:5d}, value={r['value']:7.2f}, ts={ts_str}")

    # Analyze 0x03
    if action_03_records:
        print(f"\n--- Action 0x03 Analysis ---")

        # Entity distribution
        eid_counts = Counter([r['eid'] for r in action_03_records])
        print(f"Unique entities: {len(eid_counts)}")
        print(f"Top entities:")
        for eid, count in eid_counts.most_common(10):
            entity_type = "player" if 50000 <= eid <= 60000 else "structure" if 1000 <= eid <= 20000 else "other"
            print(f"  eid {eid:5d} ({entity_type}): {count:3d} occurrences")

        # Value statistics
        values = [r['value'] for r in action_03_records]
        unique_values = set(values)
        print(f"\nUnique values: {unique_values}")

        # Sample records
        print(f"\nSample records (first 10):")
        for r in action_03_records[:10]:
            ts_str = f"{r['timestamp']:.2f}" if r['timestamp'] else "N/A"
            print(f"  eid={r['eid']:5d}, value={r['value']:7.2f}, ts={ts_str}")

    return action_02_records, action_03_records

def search_all_action_bytes(replay_path: str):
    """Find ALL unique action bytes in credit records"""
    print(f"\n=== Complete Action Byte Census ===")

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

    action_bytes = Counter()
    action_examples = defaultdict(list)

    for pos in positions:
        if pos + 12 <= len(data):
            action_byte = data[pos+11]
            action_bytes[action_byte] += 1

            if len(action_examples[action_byte]) < 3:
                eid_be = struct.unpack('>H', data[pos+5:pos+7])[0]
                value = struct.unpack('>f', data[pos+7:pos+11])[0]
                action_examples[action_byte].append({
                    'eid': eid_be,
                    'value': value
                })

    print(f"\nComplete action byte distribution:")
    print(f"{'Action':>8} | {'Count':>6} | {'Examples'}")
    print(f"{'-'*8}-+-{'-'*6}-+-{'-'*50}")

    for action_byte in sorted(action_bytes.keys()):
        count = action_bytes[action_byte]
        examples = action_examples[action_byte]
        example_str = ", ".join([f"eid={e['eid']} val={e['value']:.1f}" for e in examples[:2]])
        print(f"  0x{action_byte:02X}   | {count:6d} | {example_str}")

    return action_bytes

def compare_with_known_stats(action_02_records, action_03_records, match_info: dict):
    """Try to correlate action 0x02/0x03 with known match stats"""
    print(f"\n=== Correlation with Known Stats ===")

    # Get player stats from truth data
    players = match_info.get('players', {})

    print(f"\nMatch stats:")
    print(f"  Duration: {match_info['match_info']['duration_seconds']}s")
    print(f"  Score: {match_info['match_info']['score_left']}-{match_info['match_info']['score_right']}")
    print(f"  Players: {len(players)}")

    # Check if 0x02 total correlates with anything
    if action_02_records:
        total_02_value = sum(r['value'] for r in action_02_records)
        print(f"\nAction 0x02 total value: {total_02_value:.2f}")

        # Per-entity totals
        entity_totals = defaultdict(float)
        for r in action_02_records:
            entity_totals[r['eid']] += r['value']

        print(f"Action 0x02 per-entity totals (top 10):")
        for eid, total in sorted(entity_totals.items(), key=lambda x: -x[1])[:10]:
            print(f"  eid {eid:5d}: {total:8.2f}")

    # Check if 0x03 count correlates with kills/deaths/assists
    if action_03_records:
        total_03_count = len(action_03_records)
        print(f"\nAction 0x03 count: {total_03_count}")

        # Per-entity counts
        entity_counts = Counter([r['eid'] for r in action_03_records])
        print(f"Action 0x03 per-entity counts (top 10):")
        for eid, count in entity_counts.most_common(10):
            print(f"  eid {eid:5d}: {count:3d} occurrences")

        # Compare with KDA
        total_kills = match_info['match_info']['score_left'] + match_info['match_info']['score_right']
        print(f"\nTotal kills in match: {total_kills}")
        print(f"Action 0x03 count: {total_03_count}")
        print(f"Ratio: {total_03_count / total_kills if total_kills > 0 else 'N/A'}")

def main():
    # Load truth data
    truth_path = Path(__file__).parent.parent / "output" / "tournament_truth.json"
    with open(truth_path) as f:
        truth_data = json.load(f)

    # Analyze first 4 matches for better coverage
    matches = truth_data['matches'][:4]

    for i, match in enumerate(matches):
        replay_path = match['replay_file']
        print(f"\n{'='*80}")
        print(f"MATCH {i+1}: {Path(replay_path).stem}")
        print(f"{'='*80}")

        # Complete action byte census
        all_action_bytes = search_all_action_bytes(replay_path)

        # Deep dive on 0x02 and 0x03
        action_02_records, action_03_records = analyze_action_02_and_03(replay_path, match)

        # Correlation analysis
        compare_with_known_stats(action_02_records, action_03_records, match)

        print(f"\n{'='*80}\n")

    print("\n[RESEARCH FINDINGS]")
    print("- Action 0x02: Variable float values (6-15 range), appears on structures")
    print("- Action 0x03: Always value=1.0, appears on structures")
    print("- Need to check if these correlate with damage dealt to structures")

if __name__ == '__main__':
    main()
