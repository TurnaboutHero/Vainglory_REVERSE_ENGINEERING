#!/usr/bin/env python3
"""
Combo Event Analysis - Phase 2.4
복합 이벤트 패턴 분석: 여러 액션 코드 조합이 K/D/A를 나타낼 수 있음
"""

import json
import sys
from pathlib import Path
from collections import defaultdict
from itertools import combinations

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'core'))
from vgr_parser import VGRParser


def load_truth_data():
    truth_path = Path(__file__).parent.parent / 'output' / 'tournament_truth.json'
    with open(truth_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def count_all_actions_for_entity(replay_dir: Path, replay_name: str, entity_id: int) -> dict:
    """Count all action codes for an entity."""
    entity_bytes = entity_id.to_bytes(2, 'little')
    pattern = entity_bytes + b'\x00\x00'

    action_counts = defaultdict(int)
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

    return dict(action_counts)


def main():
    print("=" * 70)
    print("Combo Event Analysis")
    print("=" * 70)
    print()

    truth = load_truth_data()

    # Collect all player data
    all_players = []

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

                action_counts = count_all_actions_for_entity(replay_dir, replay_name, entity_id)

                all_players.append({
                    'name': player_name,
                    'kills': truth_player.get('kills', 0),
                    'deaths': truth_player.get('deaths', 0),
                    'assists': truth_player.get('assists', 0),
                    'action_counts': action_counts
                })

    print(f"\nTotal players: {len(all_players)}")
    print()

    # Try subtracting common events to find rare death events
    # Hypothesis: death = rare_action - common_action
    print("=" * 70)
    print("Testing: action_A - action_B = deaths")
    print("=" * 70)
    print()

    # Find actions that appear for most players
    action_frequency = defaultdict(int)
    for p in all_players:
        for action in p['action_counts']:
            action_frequency[action] += 1

    common_actions = [a for a, freq in action_frequency.items() if freq >= 80]
    print(f"Common actions (appear in 80+ players): {len(common_actions)}")

    best_combos = []

    for action_a in common_actions:
        for action_b in common_actions:
            if action_a == action_b:
                continue

            exact_kills = 0
            exact_deaths = 0
            exact_assists = 0
            total = 0

            for p in all_players:
                count_a = p['action_counts'].get(action_a, 0)
                count_b = p['action_counts'].get(action_b, 0)
                diff = count_a - count_b

                if diff >= 0:  # Only positive differences
                    total += 1
                    if diff == p['kills'] and p['kills'] > 0:
                        exact_kills += 1
                    if diff == p['deaths'] and p['deaths'] > 0:
                        exact_deaths += 1
                    if diff == p['assists'] and p['assists'] > 0:
                        exact_assists += 1

            if exact_kills > 15 or exact_deaths > 15 or exact_assists > 15:
                best_combos.append({
                    'a': action_a,
                    'b': action_b,
                    'kills': exact_kills,
                    'deaths': exact_deaths,
                    'assists': exact_assists,
                    'total': total
                })

    # Sort by best death match
    best_combos.sort(key=lambda x: x['deaths'], reverse=True)

    print()
    print(f"{'A-B':<15} {'Kills':>10} {'Deaths':>10} {'Assists':>10}")
    print("-" * 50)

    for combo in best_combos[:30]:
        formula = f"0x{combo['a']:02X}-0x{combo['b']:02X}"
        print(f"{formula:<15} {combo['kills']:>10} {combo['deaths']:>10} {combo['assists']:>10}")

    # Also try sum of two actions
    print()
    print("=" * 70)
    print("Testing: action_A + action_B = deaths")
    print("=" * 70)

    sum_combos = []

    for action_a, action_b in combinations(common_actions, 2):
        exact_kills = 0
        exact_deaths = 0
        exact_assists = 0
        total = len(all_players)

        for p in all_players:
            count_a = p['action_counts'].get(action_a, 0)
            count_b = p['action_counts'].get(action_b, 0)
            total_count = count_a + count_b

            if total_count == p['kills'] and p['kills'] > 0:
                exact_kills += 1
            if total_count == p['deaths'] and p['deaths'] > 0:
                exact_deaths += 1
            if total_count == p['assists'] and p['assists'] > 0:
                exact_assists += 1

        if exact_deaths > 20:
            sum_combos.append({
                'a': action_a,
                'b': action_b,
                'kills': exact_kills,
                'deaths': exact_deaths,
                'assists': exact_assists,
                'total': total
            })

    sum_combos.sort(key=lambda x: x['deaths'], reverse=True)

    print()
    print(f"{'A+B':<15} {'Kills':>10} {'Deaths':>10} {'Assists':>10}")
    print("-" * 50)

    for combo in sum_combos[:20]:
        formula = f"0x{combo['a']:02X}+0x{combo['b']:02X}"
        print(f"{formula:<15} {combo['kills']:>10} {combo['deaths']:>10} {combo['assists']:>10}")

    # Try action / 2 = deaths
    print()
    print("=" * 70)
    print("Testing: action_count / 2 = deaths")
    print("=" * 70)

    divisor_results = []

    for action in common_actions:
        for divisor in [2, 3, 4, 5]:
            exact_deaths = 0

            for p in all_players:
                count = p['action_counts'].get(action, 0)
                if count > 0 and count % divisor == 0:
                    if count // divisor == p['deaths'] and p['deaths'] > 0:
                        exact_deaths += 1

            if exact_deaths > 10:
                divisor_results.append({
                    'action': action,
                    'divisor': divisor,
                    'deaths': exact_deaths
                })

    divisor_results.sort(key=lambda x: x['deaths'], reverse=True)

    print()
    print(f"{'Formula':<20} {'Deaths Match':>15}")
    print("-" * 40)

    for r in divisor_results[:15]:
        formula = f"0x{r['action']:02X} / {r['divisor']}"
        print(f"{formula:<20} {r['deaths']:>15}")


if __name__ == "__main__":
    main()
