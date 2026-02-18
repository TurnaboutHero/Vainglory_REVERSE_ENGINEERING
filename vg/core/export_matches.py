#!/usr/bin/env python3
"""
Match Export Tool - Export decoded VGR replays to JSON and CSV formats.

Supports:
  - Single replay → JSON
  - Batch (directory of replays) → combined JSON + CSV
  - Tournament mode → JSON + CSV with truth comparison columns

Usage:
    # Single replay
    python -m vg.core.export_matches /path/to/replay.0.vgr

    # Batch (all replays in a directory)
    python -m vg.core.export_matches /path/to/replays/ --batch

    # Tournament with truth data
    python -m vg.core.export_matches /path/to/replays/ --batch --truth tournament_truth.json

    # Output to specific directory
    python -m vg.core.export_matches /path/to/replays/ --batch -o /output/dir/
"""

import csv
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from vg.core.unified_decoder import UnifiedDecoder, DecodedMatch


def export_match_json(match: DecodedMatch, output_path: Path) -> None:
    """Export a single decoded match to JSON."""
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(match.to_json(indent=2))


def match_to_csv_rows(match: DecodedMatch, match_idx: int = 0) -> List[Dict]:
    """Convert a decoded match to flat CSV rows (one row per player)."""
    rows = []
    for player in match.all_players:
        assists = player.assists if player.assists is not None else 0
        kda_ratio = round((player.kills + assists) / max(player.deaths, 1), 2)
        is_winner = 1 if match.winner and player.team == match.winner else 0
        row = {
            'match_idx': match_idx,
            'replay_name': match.replay_name,
            'game_mode': match.game_mode,
            'map': match.map_name,
            'team_size': match.team_size,
            'duration_s': match.duration_seconds or '',
            'winner': match.winner or '',
            'player_name': player.name,
            'team': player.team,
            'is_winner': is_winner,
            'hero': player.hero_name,
            'kills': player.kills,
            'deaths': player.deaths,
            'assists': player.assists if player.assists is not None else '',
            'kda_ratio': kda_ratio,
            'minion_kills': player.minion_kills,
            'gold_spent': player.gold_spent,
            'gold_earned': player.gold_earned,
            'items': ' | '.join(player.items) if player.items else '',
            'item_count': len(player.items),
        }
        if player.truth_kills is not None:
            row['truth_kills'] = player.truth_kills
            row['kill_match'] = 1 if player.kills == player.truth_kills else 0
        if player.truth_deaths is not None:
            row['truth_deaths'] = player.truth_deaths
            row['death_match'] = 1 if player.deaths == player.truth_deaths else 0
        rows.append(row)
    return rows


def match_to_summary_row(match: DecodedMatch, match_idx: int = 0) -> Dict:
    """Convert a decoded match to a single summary row."""
    left_kills = sum(p.kills for p in match.left_team)
    right_kills = sum(p.kills for p in match.right_team)
    left_deaths = sum(p.deaths for p in match.left_team)
    right_deaths = sum(p.deaths for p in match.right_team)
    left_gold = sum(p.gold_earned for p in match.left_team)
    right_gold = sum(p.gold_earned for p in match.right_team)

    obj_counts = {}
    for evt in match.objective_events:
        obj_counts[evt.event_type] = obj_counts.get(evt.event_type, 0) + 1

    return {
        'match_idx': match_idx,
        'replay_name': match.replay_name,
        'game_mode': match.game_mode,
        'map': match.map_name,
        'team_size': match.team_size,
        'duration_s': match.duration_seconds or '',
        'winner': match.winner or '',
        'left_kills': left_kills,
        'right_kills': right_kills,
        'left_deaths': left_deaths,
        'right_deaths': right_deaths,
        'left_gold': left_gold,
        'right_gold': right_gold,
        'gold_mine_captures': obj_counts.get('GOLD_MINE_CAPTURE', 0),
        'kraken_deaths': obj_counts.get('KRAKEN_DEATH', 0),
        'kraken_waves': obj_counts.get('KRAKEN_WAVE', 0),
        'crystal_death_ts': match.crystal_death_ts or '',
        'total_frames': match.total_frames,
    }


def export_csv(rows: List[Dict], output_path: Path) -> None:
    """Export flat rows to CSV."""
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def find_replays(directory: Path) -> List[Path]:
    """Find all .0.vgr replay files in a directory (recursive, skip macOS ._)."""
    replays = []
    for f in sorted(directory.rglob('*.0.vgr')):
        if f.name.startswith('._'):
            continue
        replays.append(f)
    return replays


def decode_single(replay_path: str, truth_path: Optional[str] = None) -> DecodedMatch:
    """Decode a single replay file."""
    decoder = UnifiedDecoder(replay_path)
    if truth_path:
        return decoder.decode_with_truth(truth_path)
    return decoder.decode()


def decode_batch(
    directory: str,
    truth_path: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> List[DecodedMatch]:
    """Decode all replays in a directory."""
    dir_path = Path(directory)
    replays = find_replays(dir_path)

    if not replays:
        print(f"No .0.vgr files found in {directory}")
        return []

    print(f"Found {len(replays)} replay files")
    out = Path(output_dir) if output_dir else dir_path
    out.mkdir(parents=True, exist_ok=True)

    matches = []
    all_csv_rows = []

    for i, replay in enumerate(replays):
        print(f"  [{i+1}/{len(replays)}] {replay.stem}...", end=' ')
        try:
            match = decode_single(str(replay), truth_path)
            matches.append(match)

            # Per-match JSON
            json_path = out / f"match_{i+1}.json"
            export_match_json(match, json_path)

            # Collect CSV rows
            csv_rows = match_to_csv_rows(match, match_idx=i+1)
            all_csv_rows.extend(csv_rows)

            n_players = len(match.all_players)
            print(f"OK ({n_players} players, winner={match.winner})")

        except Exception as e:
            print(f"ERROR: {e}")

    # Combined JSON
    if matches:
        combined = {
            'total_matches': len(matches),
            'matches': [m.to_dict() for m in matches],
        }
        combined_path = out / 'all_matches.json'
        with open(combined_path, 'w', encoding='utf-8') as f:
            json.dump(combined, f, indent=2, ensure_ascii=False)
        print(f"\nCombined JSON: {combined_path}")

    # Combined CSV
    if all_csv_rows:
        csv_path = out / 'all_matches.csv'
        export_csv(all_csv_rows, csv_path)
        print(f"Combined CSV:  {csv_path}")

    # Match summary CSV
    if matches:
        summary_rows = [match_to_summary_row(m, i+1) for i, m in enumerate(matches)]
        summary_path = out / 'match_summary.csv'
        export_csv(summary_rows, summary_path)
        print(f"Summary CSV:   {summary_path}")

    # Summary
    if matches:
        total_players = sum(len(m.all_players) for m in matches)
        total_kills = sum(p.kills for m in matches for p in m.all_players)
        total_deaths = sum(p.deaths for m in matches for p in m.all_players)
        print(f"\nSummary: {len(matches)} matches, {total_players} players")
        print(f"  Total K/D: {total_kills}/{total_deaths}")
        winners = [m.winner for m in matches if m.winner]
        left_wins = sum(1 for w in winners if w == 'left')
        right_wins = sum(1 for w in winners if w == 'right')
        print(f"  Winners: left={left_wins}, right={right_wins}, unknown={len(matches)-left_wins-right_wins}")

    return matches


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Export decoded VGR replays to JSON/CSV'
    )
    parser.add_argument(
        'path',
        help='Path to replay file (.0.vgr) or directory (with --batch)'
    )
    parser.add_argument(
        '--batch',
        action='store_true',
        help='Batch mode: decode all replays in directory'
    )
    parser.add_argument(
        '--truth',
        help='Path to tournament_truth.json for comparison'
    )
    parser.add_argument(
        '-o', '--output',
        help='Output directory (default: same as input)'
    )
    parser.add_argument(
        '--csv-only',
        action='store_true',
        help='Only output CSV (skip per-match JSON files)'
    )

    args = parser.parse_args()
    path = Path(args.path)

    if args.batch or path.is_dir():
        decode_batch(str(path), args.truth, args.output)
    else:
        match = decode_single(str(path), args.truth)
        if args.output:
            out = Path(args.output)
            if out.is_dir():
                json_path = out / f"{path.stem}_decoded.json"
            else:
                json_path = out
        else:
            json_path = path.parent / f"{path.stem}_decoded.json"

        export_match_json(match, json_path)
        print(f"Exported: {json_path}")

        # Also export CSV if requested
        csv_path = json_path.with_suffix('.csv')
        rows = match_to_csv_rows(match)
        export_csv(rows, csv_path)
        print(f"CSV:      {csv_path}")


if __name__ == '__main__':
    main()
