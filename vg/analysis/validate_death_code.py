#!/usr/bin/env python3
"""
Find the action code that best matches death count.
Test all 256 action codes against tournament truth data.
"""

import json
from pathlib import Path
from collections import Counter, defaultdict


def count_all_actions_for_entity(replay_dir: Path, replay_name: str, entity_id: int) -> Counter:
    """Count all action codes for an entity across all frames."""
    entity_bytes = entity_id.to_bytes(2, 'little')
    pattern = entity_bytes + b'\x00\x00'

    action_counts = Counter()
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
                action_counts[action] += 1
            idx += 1

    return action_counts


def find_best_death_code():
    """Find action code that best matches death counts."""
    from vgr_parser import VGRParser

    truth_path = Path(r"d:\Desktop\My Folder\Game\VG\vg\tournament_truth.json")
    with open(truth_path, 'r', encoding='utf-8') as f:
        truth = json.load(f)

    print("=== Finding Best Death Action Code ===\n")

    # Collect all player data
    player_data = []

    for match in truth['matches']:
        replay_file = match['replay_file']
        replay_dir = Path(replay_file).parent
        replay_name = match['replay_name']

        print(f"Processing: {replay_name[:50]}...")

        # Parse replay to get entity IDs
        parser = VGRParser(replay_file, auto_truth=False)
        parsed = parser.parse()

        for team in ('left', 'right'):
            for player in parsed['teams'][team]:
                entity_id = player.get('entity_id')
                if not entity_id:
                    continue

                player_name = player['name']
                truth_player = match['players'].get(player_name, {})

                action_counts = count_all_actions_for_entity(replay_dir, replay_name, entity_id)

                player_data.append({
                    'name': player_name,
                    'entity_id': entity_id,
                    'deaths': truth_player.get('deaths', 0),
                    'kills': truth_player.get('kills', 0),
                    'assists': truth_player.get('assists', 0),
                    'action_counts': action_counts
                })

    print(f"\nTotal players: {len(player_data)}")
    print()

    # Test each action code against deaths
    action_match_counts = {}  # action -> exact matches

    for action in range(256):
        exact = 0
        close = 0
        for pd in player_data:
            count = pd['action_counts'].get(action, 0)
            deaths = pd['deaths']
            if count == deaths:
                exact += 1
            if abs(count - deaths) <= 1:
                close += 1

        if exact > 0:
            action_match_counts[action] = {'exact': exact, 'close': close}

    # Sort by exact matches
    sorted_actions = sorted(action_match_counts.items(),
                           key=lambda x: (-x[1]['exact'], -x[1]['close']))

    print("=== Top Action Codes Matching Deaths ===")
    print("(Checking if action_count == deaths for each player)")
    print()
    for action, counts in sorted_actions[:20]:
        pct = 100 * counts['exact'] / len(player_data)
        print(f"  0x{action:02X}: {counts['exact']}/{len(player_data)} exact ({pct:.1f}%), {counts['close']} close")

    print()

    # Also test kills
    print("=== Top Action Codes Matching Kills ===")
    action_kill_matches = {}
    for action in range(256):
        exact = 0
        for pd in player_data:
            count = pd['action_counts'].get(action, 0)
            kills = pd['kills']
            if count == kills:
                exact += 1
        if exact > 0:
            action_kill_matches[action] = exact

    sorted_kill_actions = sorted(action_kill_matches.items(), key=lambda x: -x[1])
    for action, exact in sorted_kill_actions[:10]:
        pct = 100 * exact / len(player_data)
        print(f"  0x{action:02X}: {exact}/{len(player_data)} exact ({pct:.1f}%)")

    print()

    # Check if any action code has a consistent ratio (e.g., 2x deaths)
    print("=== Checking for Ratio Patterns ===")
    for multiplier in [2, 3, 4, 5]:
        best_action = None
        best_count = 0
        for action in range(256):
            matches = 0
            for pd in player_data:
                count = pd['action_counts'].get(action, 0)
                deaths = pd['deaths']
                if deaths > 0 and count == deaths * multiplier:
                    matches += 1
            if matches > best_count:
                best_count = matches
                best_action = action

        if best_action is not None and best_count > 5:
            print(f"  Multiplier {multiplier}x: 0x{best_action:02X} with {best_count} matches")


if __name__ == "__main__":
    find_best_death_code()
