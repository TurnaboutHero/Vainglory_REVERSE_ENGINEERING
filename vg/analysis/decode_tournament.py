#!/usr/bin/env python3
"""
Tournament Decoder - Validate UnifiedDecoder against tournament truth data.

Runs UnifiedDecoder on all matches in tournament_truth.json and compares
detected values (hero, team, K/D, winner) against ground truth.

Usage:
    python -m vg.analysis.decode_tournament
    python -m vg.analysis.decode_tournament --truth path/to/truth.json
    python -m vg.analysis.decode_tournament --verbose
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from vg.core.unified_decoder import UnifiedDecoder
from vg.core.vgr_mapping import normalize_hero_name


def load_truth(truth_path: str) -> List[Dict]:
    """Load all matches from tournament truth JSON."""
    with open(truth_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get("matches", [])


def _detect_team_swap(decoded_players, truth_players) -> bool:
    """
    Detect if team labels are uniformly swapped between detected and truth.

    Binary team_id (1/2) from the game engine is always consistent, but
    truth data captured from result screenshots may show blue/red teams
    on either side depending on the match. When ALL matched players have
    swapped labels, we apply a convention correction.

    Returns:
        True if labels are swapped (detected left = truth right for all).
    """
    matches = 0
    swaps = 0
    for player in decoded_players:
        tp = truth_players.get(player.name, {})
        truth_team = tp.get("team", "")
        if not truth_team or player.team == "unknown":
            continue
        matches += 1
        if player.team != truth_team:
            swaps += 1
    # Swap if ALL matched players disagree
    return matches > 0 and swaps == matches


def _flip_team(team: str) -> str:
    """Flip left↔right."""
    if team == "left":
        return "right"
    if team == "right":
        return "left"
    return team


def run_validation(truth_path: str, verbose: bool = False) -> Dict:
    """
    Run UnifiedDecoder on all truth matches and compute accuracy.

    Returns:
        Summary dict with per-field accuracy stats.
    """
    matches = load_truth(truth_path)
    if not matches:
        print("No matches found in truth file.")
        return {}

    # Counters
    total_players = 0
    hero_correct = 0
    hero_total = 0
    team_correct = 0
    team_total = 0
    kill_correct = 0
    kill_total = 0
    death_correct = 0
    death_total = 0
    assist_correct = 0
    assist_total = 0
    mk_correct = 0
    mk_total = 0
    winner_correct = 0
    winner_total = 0
    team_swapped_matches = 0
    match_results = []

    for i, truth_match in enumerate(matches):
        replay_name = truth_match.get("replay_name", f"match_{i}")
        replay_file = truth_match.get("replay_file", "")

        if not replay_file or not Path(replay_file).exists():
            print(f"[SKIP] Match {i+1}: {replay_name} - file not found")
            continue

        print(f"\n{'='*70}")
        print(f"Match {i+1}: {replay_name}")
        print(f"{'='*70}")

        try:
            decoder = UnifiedDecoder(replay_file)
            decoded = decoder.decode_with_truth(truth_path)
        except Exception as e:
            print(f"[ERROR] Failed to decode: {e}")
            continue

        truth_info = truth_match.get("match_info", {})
        truth_players = truth_match.get("players", {})
        truth_winner = truth_info.get("winner")
        truth_duration = truth_info.get("duration_seconds")

        # --- Detect team label swap ---
        is_swapped = _detect_team_swap(decoded.all_players, truth_players)
        if is_swapped:
            team_swapped_matches += 1
            if verbose:
                print(f"  [INFO] Team labels swapped (truth screenshot side differs from binary)")

        # --- Winner comparison (adjusted for swap) ---
        if truth_winner and decoded.winner:
            winner_total += 1
            effective_winner = _flip_team(decoded.winner) if is_swapped else decoded.winner
            if effective_winner == truth_winner:
                winner_correct += 1
                if verbose:
                    print(f"  [OK] Winner: {effective_winner}")
            else:
                print(f"  [MISS] Winner: detected={effective_winner}, truth={truth_winner}")

        # --- Per-player comparison ---
        match_k_ok = 0
        match_k_total = 0
        match_d_ok = 0
        match_d_total = 0
        match_a_ok = 0
        match_a_total = 0
        match_mk_ok = 0
        match_mk_total = 0

        for player in decoded.all_players:
            tp = truth_players.get(player.name, {})
            if not tp:
                if verbose:
                    print(f"  [WARN] Player {player.name} not in truth")
                continue

            total_players += 1

            # Hero (normalize both sides to handle OCR typos)
            truth_hero = tp.get("hero_name", "")
            if truth_hero:
                hero_total += 1
                detected_norm = normalize_hero_name(player.hero_name)
                truth_norm = normalize_hero_name(truth_hero)
                if detected_norm == truth_norm:
                    hero_correct += 1
                elif verbose:
                    print(f"  [MISS] Hero {player.name}: detected={player.hero_name}, truth={truth_hero}")

            # Team (adjusted for swap)
            truth_team = tp.get("team", "")
            if truth_team:
                team_total += 1
                effective_team = _flip_team(player.team) if is_swapped else player.team
                if effective_team == truth_team:
                    team_correct += 1
                elif verbose:
                    print(f"  [MISS] Team {player.name}: detected={effective_team}, truth={truth_team}")

            # Kills
            truth_k = tp.get("kills")
            if truth_k is not None:
                kill_total += 1
                match_k_total += 1
                if player.kills == truth_k:
                    kill_correct += 1
                    match_k_ok += 1
                else:
                    print(f"  [MISS] Kill {player.name}: detected={player.kills}, truth={truth_k}")

            # Deaths
            truth_d = tp.get("deaths")
            if truth_d is not None:
                death_total += 1
                match_d_total += 1
                if player.deaths == truth_d:
                    death_correct += 1
                    match_d_ok += 1
                else:
                    print(f"  [MISS] Death {player.name}: detected={player.deaths}, truth={truth_d}")

            # Assists
            truth_a = tp.get("assists")
            if truth_a is not None and player.assists is not None:
                assist_total += 1
                match_a_total += 1
                if player.assists == truth_a:
                    assist_correct += 1
                    match_a_ok += 1
                else:
                    print(f"  [MISS] Assist {player.name}: detected={player.assists}, truth={truth_a}")

            # Minion Kills
            truth_mk = tp.get("minion_kills")
            if truth_mk is not None:
                mk_total += 1
                match_mk_total += 1
                if player.minion_kills == truth_mk:
                    mk_correct += 1
                    match_mk_ok += 1
                else:
                    print(f"  [MISS] MinionKill {player.name}: detected={player.minion_kills}, truth={truth_mk}")

        # Match summary
        effective_winner = (_flip_team(decoded.winner) if is_swapped else decoded.winner) if decoded.winner else None
        match_result = {
            "match": i + 1,
            "replay_name": replay_name,
            "team_swapped": is_swapped,
            "winner_ok": effective_winner == truth_winner if truth_winner else None,
            "kill_accuracy": f"{match_k_ok}/{match_k_total}" if match_k_total else "N/A",
            "death_accuracy": f"{match_d_ok}/{match_d_total}" if match_d_total else "N/A",
            "assist_accuracy": f"{match_a_ok}/{match_a_total}" if match_a_total else "N/A",
            "mk_accuracy": f"{match_mk_ok}/{match_mk_total}" if match_mk_total else "N/A",
            "duration_detected": decoded.duration_seconds,
            "duration_truth": truth_duration,
        }
        match_results.append(match_result)

        if verbose:
            print(f"  Duration: detected={decoded.duration_seconds}s, truth={truth_duration}s")
            print(f"  Kills: {match_k_ok}/{match_k_total}, Deaths: {match_d_ok}/{match_d_total}, Assists: {match_a_ok}/{match_a_total}")

    # --- Summary ---
    print(f"\n{'='*70}")
    print("VALIDATION SUMMARY")
    print(f"{'='*70}")

    summary = {}

    if hero_total:
        pct = hero_correct / hero_total * 100
        summary["hero"] = {"correct": hero_correct, "total": hero_total, "pct": pct}
        print(f"Hero:   {hero_correct}/{hero_total} ({pct:.1f}%)")

    if team_total:
        pct = team_correct / team_total * 100
        summary["team"] = {"correct": team_correct, "total": team_total, "pct": pct}
        print(f"Team:   {team_correct}/{team_total} ({pct:.1f}%) [{team_swapped_matches} matches had screenshot-side swap]")

    if winner_total:
        pct = winner_correct / winner_total * 100
        summary["winner"] = {"correct": winner_correct, "total": winner_total, "pct": pct}
        print(f"Winner: {winner_correct}/{winner_total} ({pct:.1f}%) [swap-adjusted]")

    if kill_total:
        pct = kill_correct / kill_total * 100
        summary["kills"] = {"correct": kill_correct, "total": kill_total, "pct": pct}
        print(f"Kills:  {kill_correct}/{kill_total} ({pct:.1f}%)")

    if death_total:
        pct = death_correct / death_total * 100
        summary["deaths"] = {"correct": death_correct, "total": death_total, "pct": pct}
        print(f"Deaths: {death_correct}/{death_total} ({pct:.1f}%)")

    if assist_total:
        pct = assist_correct / assist_total * 100
        summary["assists"] = {"correct": assist_correct, "total": assist_total, "pct": pct}
        print(f"Assist: {assist_correct}/{assist_total} ({pct:.1f}%)")

    if mk_total:
        pct = mk_correct / mk_total * 100
        summary["minion_kills"] = {"correct": mk_correct, "total": mk_total, "pct": pct}
        print(f"Minion: {mk_correct}/{mk_total} ({pct:.1f}%)")

    combined = kill_correct + death_correct
    combined_total = kill_total + death_total
    if combined_total:
        pct = combined / combined_total * 100
        summary["combined_kd"] = {"correct": combined, "total": combined_total, "pct": pct}
        print(f"K+D:    {combined}/{combined_total} ({pct:.1f}%)")

    print(f"\nTotal players analyzed: {total_players}")
    print(f"Team-swapped matches: {team_swapped_matches}/{len(match_results)}")
    summary["total_players"] = total_players
    summary["team_swapped_matches"] = team_swapped_matches
    summary["match_results"] = match_results

    return summary


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='Validate UnifiedDecoder against tournament truth data'
    )
    parser.add_argument(
        '--truth',
        default=str(Path(__file__).resolve().parent.parent / "output" / "tournament_truth.json"),
        help='Path to tournament_truth.json'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Show detailed per-player results'
    )
    parser.add_argument(
        '-o', '--output',
        help='Save summary JSON to file'
    )

    args = parser.parse_args()

    if not Path(args.truth).exists():
        print(f"Truth file not found: {args.truth}")
        sys.exit(1)

    summary = run_validation(args.truth, verbose=args.verbose)

    if args.output and summary:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        print(f"\nSummary saved to {args.output}")


if __name__ == '__main__':
    main()
