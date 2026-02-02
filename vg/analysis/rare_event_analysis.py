#!/usr/bin/env python3
"""
Rare Event Analysis - Phase 2.3
프레임당 1회만 발생하는 희귀 이벤트 탐색
킬/데스는 희귀 이벤트일 가능성이 높음
"""

import json
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any, Set

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'core'))
from vgr_parser import VGRParser


def load_truth_data() -> Dict:
    """Load tournament truth data."""
    truth_path = Path(__file__).parent.parent / 'output' / 'tournament_truth.json'
    with open(truth_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def find_rare_events(replay_dir: Path, replay_name: str,
                      entity_ids: Set[int]) -> Dict[int, Dict]:
    """
    Find action codes that appear rarely (1-2 times per entity per game).
    These are candidates for kill/death events.
    """
    # Count total occurrences per entity per action
    entity_action_counts = defaultdict(lambda: defaultdict(int))

    frame_files = sorted(replay_dir.glob(f"{replay_name}.*.vgr"),
                        key=lambda p: int(p.stem.split('.')[-1]))

    total_frames = len(frame_files)

    for frame_path in frame_files:
        data = frame_path.read_bytes()

        for entity_id in entity_ids:
            entity_bytes = entity_id.to_bytes(2, 'little')
            pattern = entity_bytes + b'\x00\x00'
            idx = 0

            while True:
                idx = data.find(pattern, idx)
                if idx == -1:
                    break

                if idx + 5 <= len(data):
                    action = data[idx + 4]
                    entity_action_counts[entity_id][action] += 1
                idx += 1

    return entity_action_counts, total_frames


def analyze_rare_events_vs_kda(matches: List[Dict]) -> Dict:
    """
    For each rare event (1-10 occurrences per player), check correlation with K/D/A.
    """
    # action -> stat -> list of (count, stat_value) pairs
    action_stat_pairs = defaultdict(lambda: {'kills': [], 'deaths': [], 'assists': []})

    for match_idx, match in enumerate(matches):
        replay_file = match['replay_file']
        replay_dir = Path(replay_file).parent
        replay_name = match['replay_name']

        print(f"Processing match {match_idx + 1}/{len(matches)}: {replay_name[:40]}...")

        # Parse replay to get entity IDs
        parser = VGRParser(replay_file, auto_truth=False)
        parsed = parser.parse()

        # Build entity mapping
        entity_to_info = {}
        for team in ('left', 'right'):
            for player in parsed['teams'][team]:
                entity_id = player.get('entity_id')
                player_name = player['name']
                truth_player = match['players'].get(player_name, {})

                if entity_id and truth_player:
                    entity_to_info[entity_id] = {
                        'name': player_name,
                        'kills': truth_player.get('kills', 0),
                        'deaths': truth_player.get('deaths', 0),
                        'assists': truth_player.get('assists', 0)
                    }

        if not entity_to_info:
            continue

        # Find rare events
        entity_action_counts, total_frames = find_rare_events(
            replay_dir, replay_name, set(entity_to_info.keys())
        )

        # For each entity, record action counts vs K/D/A
        for entity_id, action_counts in entity_action_counts.items():
            info = entity_to_info.get(entity_id)
            if not info:
                continue

            for action, count in action_counts.items():
                # Focus on rare events (1-20 occurrences)
                if 1 <= count <= 20:
                    action_stat_pairs[action]['kills'].append((count, info['kills']))
                    action_stat_pairs[action]['deaths'].append((count, info['deaths']))
                    action_stat_pairs[action]['assists'].append((count, info['assists']))

    return action_stat_pairs


def calculate_exact_match_rate(pairs: List[tuple]) -> tuple:
    """Calculate how often event count exactly matches stat value."""
    if not pairs:
        return 0, 0, 0

    exact_matches = sum(1 for count, stat in pairs if count == stat and stat > 0)
    total_nonzero = sum(1 for count, stat in pairs if stat > 0)

    if total_nonzero == 0:
        return 0, 0, 0

    return exact_matches, total_nonzero, exact_matches / total_nonzero * 100


def main():
    print("=" * 60)
    print("Rare Event Analysis - K/D/A Correlation")
    print("=" * 60)
    print()

    truth = load_truth_data()

    # Analyze all matches
    action_stat_pairs = analyze_rare_events_vs_kda(truth['matches'])

    print()
    print("=" * 60)
    print("Results: Exact Match Rates")
    print("=" * 60)
    print()

    # Calculate match rates for each action
    results = []

    for action, stats in action_stat_pairs.items():
        kills_match, kills_total, kills_pct = calculate_exact_match_rate(stats['kills'])
        deaths_match, deaths_total, deaths_pct = calculate_exact_match_rate(stats['deaths'])
        assists_match, assists_total, assists_pct = calculate_exact_match_rate(stats['assists'])

        total_matches = kills_match + deaths_match + assists_match
        total_checked = kills_total + deaths_total + assists_total

        if total_matches > 0:
            results.append({
                'action': action,
                'kills': (kills_match, kills_total, kills_pct),
                'deaths': (deaths_match, deaths_total, deaths_pct),
                'assists': (assists_match, assists_total, assists_pct),
                'total_matches': total_matches,
                'total_checked': total_checked
            })

    # Sort by total matches
    results.sort(key=lambda x: x['total_matches'], reverse=True)

    print(f"{'Action':<8} {'Kills':>18} {'Deaths':>18} {'Assists':>18} {'Total':>10}")
    print("-" * 80)

    for r in results[:40]:
        action = f"0x{r['action']:02X}"
        kills = f"{r['kills'][0]}/{r['kills'][1]} ({r['kills'][2]:.0f}%)"
        deaths = f"{r['deaths'][0]}/{r['deaths'][1]} ({r['deaths'][2]:.0f}%)"
        assists = f"{r['assists'][0]}/{r['assists'][1]} ({r['assists'][2]:.0f}%)"
        total = f"{r['total_matches']}/{r['total_checked']}"

        print(f"{action:<8} {kills:>18} {deaths:>18} {assists:>18} {total:>10}")

    # Find best candidates for each stat
    print()
    print("=" * 60)
    print("Best Candidates by Stat")
    print("=" * 60)

    for stat_name in ['kills', 'deaths', 'assists']:
        print(f"\n--- {stat_name.upper()} ---")
        stat_results = [(r['action'], r[stat_name]) for r in results if r[stat_name][1] > 5]
        stat_results.sort(key=lambda x: x[1][2], reverse=True)

        for action, (matches, total, pct) in stat_results[:10]:
            print(f"  0x{action:02X}: {matches}/{total} ({pct:.1f}%)")

    # Deep dive into top candidates
    print()
    print("=" * 60)
    print("Deep Dive: Top Death Candidates")
    print("=" * 60)

    death_candidates = [(r['action'], r['deaths']) for r in results if r['deaths'][2] > 30]
    death_candidates.sort(key=lambda x: x[1][2], reverse=True)

    for action, (matches, total, pct) in death_candidates[:5]:
        print(f"\n0x{action:02X}: {matches}/{total} ({pct:.1f}%)")

        # Show actual pairs
        pairs = action_stat_pairs[action]['deaths']
        print("  Sample pairs (event_count, deaths):")
        for count, deaths in pairs[:10]:
            match_str = "MATCH" if count == deaths else ""
            print(f"    {count} vs {deaths} {match_str}")


if __name__ == "__main__":
    main()
