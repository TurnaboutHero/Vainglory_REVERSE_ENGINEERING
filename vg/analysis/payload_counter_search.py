#!/usr/bin/env python3
"""
Payload Counter Search - Phase 2.5
페이로드 내부에 누적 K/D/A 카운터가 있는지 탐색
마지막 프레임의 페이로드에서 K/D/A 값을 직접 찾기
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


def get_last_frame_payloads(replay_dir: Path, replay_name: str, entity_id: int) -> dict:
    """Get payloads from the last frame for each action code."""
    entity_bytes = entity_id.to_bytes(2, 'little')
    pattern = entity_bytes + b'\x00\x00'

    frame_files = sorted(replay_dir.glob(f"{replay_name}.*.vgr"),
                        key=lambda p: int(p.stem.split('.')[-1]))

    if not frame_files:
        return {}

    # Get last frame
    last_frame = frame_files[-1]
    data = last_frame.read_bytes()

    payloads = defaultdict(list)
    idx = 0

    while True:
        idx = data.find(pattern, idx)
        if idx == -1:
            break

        if idx + 36 <= len(data):
            action = data[idx + 4]
            payload = data[idx + 5:idx + 36]
            payloads[action].append(list(payload))
        idx += 1

    return payloads


def search_value_in_payloads(payloads: dict, target_value: int) -> list:
    """Search for a specific value in all payloads."""
    matches = []

    for action, payload_list in payloads.items():
        for payload in payload_list:
            for offset, byte_val in enumerate(payload):
                if byte_val == target_value:
                    matches.append({
                        'action': action,
                        'offset': offset,
                        'type': 'byte'
                    })

                # Check 2-byte little-endian
                if offset < len(payload) - 1:
                    two_byte = payload[offset] | (payload[offset + 1] << 8)
                    if two_byte == target_value:
                        matches.append({
                            'action': action,
                            'offset': offset,
                            'type': '2byte_le'
                        })

    return matches


def main():
    print("=" * 70)
    print("Payload Counter Search - Finding K/D/A in Last Frame")
    print("=" * 70)
    print()

    truth = load_truth_data()

    # Track matches for each (action, offset, type) combination
    offset_matches = defaultdict(lambda: {'kills': 0, 'deaths': 0, 'assists': 0, 'total': 0})

    for match_idx, match in enumerate(truth['matches']):
        replay_file = match['replay_file']
        replay_dir = Path(replay_file).parent
        replay_name = match['replay_name']

        print(f"Processing match {match_idx + 1}: {replay_name[:40]}...")

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

                # Get last frame payloads
                payloads = get_last_frame_payloads(replay_dir, replay_name, entity_id)

                # Search for each stat value
                for stat_name, stat_value in [('kills', kills), ('deaths', deaths), ('assists', assists)]:
                    if stat_value == 0:
                        continue

                    matches = search_value_in_payloads(payloads, stat_value)

                    for m in matches:
                        key = (m['action'], m['offset'], m['type'])
                        offset_matches[key][stat_name] += 1
                        offset_matches[key]['total'] += 1

    print()
    print("=" * 70)
    print("Results: Payload Offsets Matching K/D/A Values")
    print("=" * 70)
    print()

    # Sort by total matches
    sorted_matches = sorted(offset_matches.items(), key=lambda x: x[1]['total'], reverse=True)

    print(f"{'Action':<8} {'Offset':>8} {'Type':>10} {'Kills':>8} {'Deaths':>8} {'Assists':>8} {'Total':>8}")
    print("-" * 70)

    for (action, offset, val_type), counts in sorted_matches[:50]:
        print(f"0x{action:02X}     {offset:>8} {val_type:>10} {counts['kills']:>8} {counts['deaths']:>8} {counts['assists']:>8} {counts['total']:>8}")

    # Focus on specific stat patterns
    print()
    print("=" * 70)
    print("Best Candidates for Each Stat")
    print("=" * 70)

    for stat_name in ['kills', 'deaths', 'assists']:
        print(f"\n--- {stat_name.upper()} ---")
        stat_sorted = sorted(
            [(k, v) for k, v in offset_matches.items() if v[stat_name] > 0],
            key=lambda x: x[1][stat_name],
            reverse=True
        )

        for (action, offset, val_type), counts in stat_sorted[:10]:
            print(f"  0x{action:02X} offset={offset:2d} type={val_type:10s}: {counts[stat_name]} matches")


if __name__ == "__main__":
    main()
