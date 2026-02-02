#!/usr/bin/env python3
"""
Verify 0x05 Payload Pattern
0x05 페이로드의 특정 오프셋에 K/D/A가 저장되어 있는지 검증
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'core'))
from vgr_parser import VGRParser


def load_truth_data():
    truth_path = Path(__file__).parent.parent / 'output' / 'tournament_truth.json'
    with open(truth_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_0x05_payload_from_last_frame(replay_dir: Path, replay_name: str, entity_id: int) -> list:
    """Get all 0x05 payloads from the last frame."""
    entity_bytes = entity_id.to_bytes(2, 'little')
    pattern = entity_bytes + b'\x00\x00'

    frame_files = sorted(replay_dir.glob(f"{replay_name}.*.vgr"),
                        key=lambda p: int(p.stem.split('.')[-1]))

    if not frame_files:
        return []

    last_frame = frame_files[-1]
    data = last_frame.read_bytes()

    payloads = []
    idx = 0

    while True:
        idx = data.find(pattern, idx)
        if idx == -1:
            break

        if idx + 36 <= len(data):
            action = data[idx + 4]
            if action == 0x05:
                payload = list(data[idx + 5:idx + 36])
                payloads.append(payload)
        idx += 1

    return payloads


def main():
    print("=" * 80)
    print("Verifying 0x05 Payload Pattern for K/D/A")
    print("=" * 80)
    print()

    truth = load_truth_data()

    # Test specific offsets
    test_offsets = [4, 7, 10, 23]

    results = []

    for match_idx, match in enumerate(truth['matches'][:3]):  # First 3 matches for detail
        replay_file = match['replay_file']
        replay_dir = Path(replay_file).parent
        replay_name = match['replay_name']

        print(f"\n{'='*80}")
        print(f"Match {match_idx + 1}: {replay_name[:50]}...")
        print(f"{'='*80}")

        parser = VGRParser(replay_file, auto_truth=False)
        parsed = parser.parse()

        for team in ('left', 'right'):
            for player in parsed['teams'][team]:
                entity_id = player.get('entity_id')
                player_name = player['name']
                truth_player = match['players'].get(player_name, {})

                if not entity_id or not truth_player:
                    continue

                kills = truth_player.get('kills', 0)
                deaths = truth_player.get('deaths', 0)
                assists = truth_player.get('assists', 0)

                payloads = get_0x05_payload_from_last_frame(replay_dir, replay_name, entity_id)

                if not payloads:
                    print(f"{player_name}: No 0x05 payloads in last frame")
                    continue

                # Check first payload
                payload = payloads[0]

                print(f"\n{player_name} (K:{kills} D:{deaths} A:{assists})")
                print(f"  0x05 payloads: {len(payloads)}")
                print(f"  First payload bytes 0-10: {payload[:11]}")

                # Check each offset
                for offset in test_offsets:
                    if offset < len(payload):
                        val = payload[offset]
                        matches = []
                        if val == kills:
                            matches.append('K')
                        if val == deaths:
                            matches.append('D')
                        if val == assists:
                            matches.append('A')
                        match_str = ','.join(matches) if matches else '-'
                        print(f"    offset {offset:2d}: {val:3d} -> {match_str}")

                results.append({
                    'player': player_name,
                    'kills': kills,
                    'deaths': deaths,
                    'assists': assists,
                    'payload': payload[:15]
                })

    # Summary analysis
    print()
    print("=" * 80)
    print("Statistical Verification Across All Matches")
    print("=" * 80)

    # Check each offset for exact match rate
    offset_exact_matches = defaultdict(lambda: {'K': 0, 'D': 0, 'A': 0, 'total': 0})

    for match in truth['matches']:
        replay_file = match['replay_file']
        replay_dir = Path(replay_file).parent
        replay_name = match['replay_name']

        parser = VGRParser(replay_file, auto_truth=False)
        parsed = parser.parse()

        for team in ('left', 'right'):
            for player in parsed['teams'][team]:
                entity_id = player.get('entity_id')
                player_name = player['name']
                truth_player = match['players'].get(player_name, {})

                if not entity_id or not truth_player:
                    continue

                kills = truth_player.get('kills', 0)
                deaths = truth_player.get('deaths', 0)
                assists = truth_player.get('assists', 0)

                payloads = get_0x05_payload_from_last_frame(replay_dir, replay_name, entity_id)

                if not payloads:
                    continue

                payload = payloads[0]

                for offset in range(min(20, len(payload))):
                    val = payload[offset]
                    offset_exact_matches[offset]['total'] += 1

                    if val == kills and kills > 0:
                        offset_exact_matches[offset]['K'] += 1
                    if val == deaths and deaths > 0:
                        offset_exact_matches[offset]['D'] += 1
                    if val == assists and assists > 0:
                        offset_exact_matches[offset]['A'] += 1

    print()
    print(f"{'Offset':>8} {'Kills':>12} {'Deaths':>12} {'Assists':>12}")
    print("-" * 50)

    for offset in range(15):
        m = offset_exact_matches[offset]
        total = m['total']
        k_pct = m['K'] / total * 100 if total > 0 else 0
        d_pct = m['D'] / total * 100 if total > 0 else 0
        a_pct = m['A'] / total * 100 if total > 0 else 0

        print(f"{offset:>8} {m['K']:>4} ({k_pct:>4.1f}%) {m['D']:>4} ({d_pct:>4.1f}%) {m['A']:>4} ({a_pct:>4.1f}%)")


if __name__ == "__main__":
    main()
