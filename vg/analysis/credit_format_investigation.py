#!/usr/bin/env python3
"""
Credit Format Investigation - Identify why different replays show different action bytes

Hypothesis: File format variation or different credit record types beyond [10 04 1D]
"""

import sys
from pathlib import Path
from collections import Counter
import struct
import json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def scan_all_credit_patterns(data: bytes) -> dict:
    """Scan for ALL potential credit-like patterns, not just [10 04 1D]"""

    results = {}

    # Known credit headers
    patterns = {
        '[10 04 1D]': bytes([0x10, 0x04, 0x1D]),  # Standard credit
        '[10 04 1E]': bytes([0x10, 0x04, 0x1E]),  # Alternative?
        '[10 04 1F]': bytes([0x10, 0x04, 0x1F]),  # Alternative?
        '[10 04 06]': bytes([0x10, 0x04, 0x06]),  # Gold income?
    }

    for name, pattern in patterns.items():
        count = 0
        i = 0
        action_bytes = []

        while i < len(data) - 12:
            if data[i:i+3] == pattern:
                count += 1
                # Try to extract action byte at offset +11
                if i + 11 < len(data):
                    action_bytes.append(data[i+11])
                i += 3
            else:
                i += 1

        results[name] = {
            'count': count,
            'action_byte_distribution': dict(Counter(action_bytes).most_common(20))
        }

    # Scan for sequences: [10 04 XX] where XX varies
    credit_prefix = bytes([0x10, 0x04])
    third_byte_distribution = []

    i = 0
    while i < len(data) - 3:
        if data[i:i+2] == credit_prefix:
            third_byte_distribution.append(data[i+2])
            i += 3
        else:
            i += 1

    results['[10 04 ??]_third_byte_scan'] = dict(Counter(third_byte_distribution).most_common(30))

    return results


def main():
    truth_path = Path(__file__).parent.parent / "output" / "tournament_truth.json"
    with open(truth_path) as f:
        truth_data = json.load(f)

    print("[OBJECTIVE] Investigate credit record format variation across replay files")
    print()

    # Analyze first 5 matches
    for idx, match in enumerate(truth_data['matches'][:5]):
        replay_path = Path(match['replay_file'])

        if not replay_path.exists():
            print(f"[LIMITATION] Match {idx+1}: File not found - {replay_path}")
            continue

        print(f"=" * 80)
        print(f"MATCH {idx+1}: {replay_path.name}")
        print(f"Duration: {match['match_info']['duration_seconds']}s")
        print("=" * 80)

        with open(replay_path, 'rb') as f:
            data = f.read()

        print(f"File size: {len(data):,} bytes")

        results = scan_all_credit_patterns(data)

        for pattern_name, pattern_results in results.items():
            if pattern_name == '[10 04 ??]_third_byte_scan':
                print(f"\n{pattern_name}:")
                print(json.dumps(pattern_results, indent=2))
            else:
                print(f"\n{pattern_name}: {pattern_results['count']} occurrences")
                if pattern_results['count'] > 0:
                    print(f"  Action bytes: {pattern_results['action_byte_distribution']}")

        print()


if __name__ == '__main__':
    main()
