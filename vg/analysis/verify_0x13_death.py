#!/usr/bin/env python3
"""
Verify 0x13 as potential death event.
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


def count_action_for_entity(replay_dir: Path, replay_name: str,
                             entity_id: int, target_action: int) -> int:
    """Count occurrences of a specific action for an entity."""
    entity_bytes = entity_id.to_bytes(2, 'little')
    pattern = entity_bytes + b'\x00\x00'

    count = 0
    frame_files = sorted(replay_dir.glob(f"{replay_name}.*.vgr"),
                        key=lambda p: int(p.stem.split('.')[-1]))

    for frame_path in frame_files:
        data = frame_path.read_bytes()
        idx = 0

        while True:
            idx = data.find(pattern, idx)
            if idx == -1:
                break

            if idx + 5 <= len(data):
                action = data[idx + 4]
                if action == target_action:
                    count += 1
            idx += 1

    return count


def main():
    print("=" * 70)
    print("Verifying 0x13 as Death Event")
    print("=" * 70)
    print()

    truth = load_truth_data()

    # Test multiple action codes
    test_actions = [0x13, 0x78, 0xDB, 0x9C, 0xB3, 0x90, 0x08, 0x34]

    results = {action: {'exact': 0, 'total': 0, 'pairs': []} for action in test_actions}

    for match_idx, match in enumerate(truth['matches']):
        replay_file = match['replay_file']
        replay_dir = Path(replay_file).parent
        replay_name = match['replay_name']

        print(f"Match {match_idx + 1}: {replay_name[:40]}...")

        # Parse replay to get entity IDs
        parser = VGRParser(replay_file, auto_truth=False)
        parsed = parser.parse()

        for team in ('left', 'right'):
            for player in parsed['teams'][team]:
                entity_id = player.get('entity_id')
                player_name = player['name']
                truth_player = match['players'].get(player_name, {})

                if not entity_id or not truth_player:
                    continue

                truth_deaths = truth_player.get('deaths', 0)

                for action in test_actions:
                    count = count_action_for_entity(replay_dir, replay_name, entity_id, action)

                    results[action]['total'] += 1
                    results[action]['pairs'].append({
                        'player': player_name,
                        'count': count,
                        'deaths': truth_deaths
                    })

                    if count == truth_deaths:
                        results[action]['exact'] += 1

    print()
    print("=" * 70)
    print("Results Summary")
    print("=" * 70)
    print()
    print(f"{'Action':<10} {'Exact Match':>15} {'Rate':>10}")
    print("-" * 40)

    for action in test_actions:
        r = results[action]
        rate = r['exact'] / r['total'] * 100 if r['total'] > 0 else 0
        print(f"0x{action:02X}       {r['exact']:>4}/{r['total']:<4}        {rate:>6.1f}%")

    # Show best candidate details
    best_action = max(test_actions, key=lambda a: results[a]['exact'] / results[a]['total'] if results[a]['total'] > 0 else 0)
    print()
    print("=" * 70)
    print(f"Best Candidate: 0x{best_action:02X}")
    print("=" * 70)
    print()
    print(f"{'Player':<25} {'Count':>8} {'Deaths':>8} {'Match':>8}")
    print("-" * 55)

    for pair in results[best_action]['pairs']:
        match_str = "OK" if pair['count'] == pair['deaths'] else ""
        print(f"{pair['player']:<25} {pair['count']:>8} {pair['deaths']:>8} {match_str:>8}")


if __name__ == "__main__":
    main()
