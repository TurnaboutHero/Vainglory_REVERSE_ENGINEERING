#!/usr/bin/env python3
"""
Batch Report - Process all replays and generate comprehensive statistics.

Usage:
    python -m vg.analysis.batch_report [replay_dir] [-o output.json]
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from vg.core.unified_decoder import UnifiedDecoder, DecodedMatch


def find_replays(directory: Path) -> list:
    replays = []
    for f in sorted(directory.rglob('*.0.vgr')):
        if f.name.startswith('._'):
            continue
        replays.append(f)
    return replays


def decode_all(replay_dir: str) -> list:
    dir_path = Path(replay_dir)
    replays = find_replays(dir_path)
    if not replays:
        print(f"No .0.vgr files found in {replay_dir}")
        return []

    print(f"Found {len(replays)} replay files")
    matches = []
    errors = []

    for i, replay in enumerate(replays):
        label = f"[{i+1}/{len(replays)}]"
        try:
            decoder = UnifiedDecoder(str(replay))
            match = decoder.decode()
            matches.append(match)
            dur = f"{match.duration_seconds}s" if match.duration_seconds else "?"
            print(f"  {label} {replay.parent.name}/{replay.stem} OK ({dur})")
        except Exception as e:
            errors.append((str(replay), str(e)))
            print(f"  {label} {replay.parent.name}/{replay.stem} ERROR: {e}")

    print(f"\nDecoded: {len(matches)}/{len(replays)} ({len(errors)} errors)")
    return matches


def generate_report(matches: list) -> dict:
    if not matches:
        return {}

    # === Hero Statistics ===
    hero_stats = defaultdict(lambda: {
        'picks': 0, 'wins': 0, 'kills': 0, 'deaths': 0,
        'assists': 0, 'minion_kills': 0, 'gold_earned': 0,
    })

    for match in matches:
        for player in match.all_players:
            h = hero_stats[player.hero_name]
            h['picks'] += 1
            if match.winner and player.team == match.winner:
                h['wins'] += 1
            h['kills'] += player.kills
            h['deaths'] += player.deaths
            h['assists'] += (player.assists or 0)
            h['minion_kills'] += player.minion_kills
            h['gold_earned'] += player.gold_earned

    total_matches = len(matches)
    hero_table = []
    for name, s in sorted(hero_stats.items(), key=lambda x: -x[1]['picks']):
        n = s['picks']
        hero_table.append({
            'hero': name,
            'picks': n,
            'pick_rate': round(n / total_matches * 100, 1),
            'win_rate': round(s['wins'] / n * 100, 1) if n else 0,
            'avg_kills': round(s['kills'] / n, 1),
            'avg_deaths': round(s['deaths'] / n, 1),
            'avg_assists': round(s['assists'] / n, 1),
            'avg_minion_kills': round(s['minion_kills'] / n, 1),
            'avg_gold': round(s['gold_earned'] / n),
        })

    # === Match Statistics ===
    durations = [m.duration_seconds for m in matches if m.duration_seconds]
    all_players = [p for m in matches for p in m.all_players]
    total_kills = sum(p.kills for p in all_players)
    total_gold = sum(p.gold_earned for p in all_players)

    match_stats = {
        'total_matches': total_matches,
        'total_players': len(all_players),
        'avg_duration_s': round(sum(durations) / len(durations)) if durations else 0,
        'min_duration_s': min(durations) if durations else 0,
        'max_duration_s': max(durations) if durations else 0,
        'avg_kills_per_match': round(total_kills / total_matches, 1),
        'avg_gold_per_player': round(total_gold / len(all_players)) if all_players else 0,
        'left_wins': sum(1 for m in matches if m.winner == 'left'),
        'right_wins': sum(1 for m in matches if m.winner == 'right'),
        'no_winner': sum(1 for m in matches if not m.winner),
    }

    # === Game Mode Distribution ===
    mode_dist = Counter(m.game_mode for m in matches)

    # === Duration Distribution ===
    buckets = {'<10min': 0, '10-15min': 0, '15-20min': 0,
               '20-25min': 0, '25-30min': 0, '>30min': 0}
    for d in durations:
        mins = d / 60
        if mins < 10:
            buckets['<10min'] += 1
        elif mins < 15:
            buckets['10-15min'] += 1
        elif mins < 20:
            buckets['15-20min'] += 1
        elif mins < 25:
            buckets['20-25min'] += 1
        elif mins < 30:
            buckets['25-30min'] += 1
        else:
            buckets['>30min'] += 1

    # === Objective Events ===
    obj_counts = Counter()
    for m in matches:
        for evt in m.objective_events:
            obj_counts[evt.event_type] += 1

    obj_stats = {
        'total_gold_mine_captures': obj_counts.get('GOLD_MINE_CAPTURE', 0),
        'total_kraken_deaths': obj_counts.get('KRAKEN_DEATH', 0),
        'total_kraken_waves': obj_counts.get('KRAKEN_WAVE', 0),
        'total_minion_waves': obj_counts.get('MINION_WAVE', 0),
        'avg_gold_mines_per_match': round(obj_counts.get('GOLD_MINE_CAPTURE', 0) / total_matches, 2),
        'avg_krakens_per_match': round(obj_counts.get('KRAKEN_DEATH', 0) / total_matches, 2),
    }

    return {
        'match_stats': match_stats,
        'game_mode_distribution': dict(mode_dist),
        'duration_distribution': buckets,
        'objective_stats': obj_stats,
        'hero_stats': hero_table,
    }


def print_report(report: dict):
    ms = report.get('match_stats', {})
    print(f"\n{'='*70}")
    print(f"  BATCH REPLAY ANALYSIS REPORT")
    print(f"{'='*70}")

    print(f"\n  Match Statistics:")
    print(f"  {'─'*50}")
    print(f"  Total matches:       {ms.get('total_matches', 0)}")
    print(f"  Total players:       {ms.get('total_players', 0)}")
    avg_dur = ms.get('avg_duration_s', 0)
    print(f"  Avg duration:        {avg_dur//60}m {avg_dur%60}s")
    mn = ms.get('min_duration_s', 0)
    mx = ms.get('max_duration_s', 0)
    print(f"  Duration range:      {mn//60}m{mn%60}s - {mx//60}m{mx%60}s")
    print(f"  Avg kills/match:     {ms.get('avg_kills_per_match', 0)}")
    print(f"  Avg gold/player:     {ms.get('avg_gold_per_player', 0)}")
    print(f"  Winners (L/R/none):  {ms.get('left_wins',0)}/{ms.get('right_wins',0)}/{ms.get('no_winner',0)}")
    print(f"    (Note: left/right labels are non-deterministic)")

    print(f"\n  Game Mode Distribution:")
    print(f"  {'─'*50}")
    for mode, cnt in sorted(report.get('game_mode_distribution', {}).items(), key=lambda x: -x[1]):
        print(f"  {mode:30s} {cnt}")

    print(f"\n  Duration Distribution:")
    print(f"  {'─'*50}")
    for bucket, cnt in report.get('duration_distribution', {}).items():
        bar = '#' * cnt
        print(f"  {bucket:12s} {cnt:3d} {bar}")

    obj = report.get('objective_stats', {})
    print(f"\n  Objective Events:")
    print(f"  {'─'*50}")
    print(f"  Gold Mine captures:  {obj.get('total_gold_mine_captures', 0)} (avg {obj.get('avg_gold_mines_per_match', 0)}/match)")
    print(f"  Kraken deaths:       {obj.get('total_kraken_deaths', 0)} (avg {obj.get('avg_krakens_per_match', 0)}/match)")
    print(f"  Kraken waves:        {obj.get('total_kraken_waves', 0)}")
    print(f"  Minion waves:        {obj.get('total_minion_waves', 0)}")

    heroes = report.get('hero_stats', [])
    print(f"\n  Hero Statistics (top 20):")
    print(f"  {'─'*80}")
    print(f"  {'Hero':20s} {'Picks':>5s} {'Pick%':>6s} {'Win%':>6s} {'K':>5s} {'D':>5s} {'A':>5s} {'MK':>6s} {'Gold':>7s}")
    print(f"  {'─'*80}")
    for h in heroes[:20]:
        print(f"  {h['hero']:20s} {h['picks']:5d} {h['pick_rate']:5.1f}% {h['win_rate']:5.1f}%"
              f" {h['avg_kills']:5.1f} {h['avg_deaths']:5.1f} {h['avg_assists']:5.1f}"
              f" {h['avg_minion_kills']:6.1f} {h['avg_gold']:7d}")

    if len(heroes) > 20:
        print(f"  ... and {len(heroes) - 20} more heroes")


def main():
    parser = argparse.ArgumentParser(description='Batch VGR replay analysis report')
    parser.add_argument(
        'replay_dir', nargs='?',
        default=r'D:\Desktop\My Folder\Game\VG\vg replay',
        help='Directory containing replay files'
    )
    parser.add_argument('-o', '--output', help='Output JSON file path')
    args = parser.parse_args()

    matches = decode_all(args.replay_dir)
    if not matches:
        return

    report = generate_report(matches)
    print_report(report)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"\nJSON report saved to: {out_path}")


if __name__ == '__main__':
    main()
