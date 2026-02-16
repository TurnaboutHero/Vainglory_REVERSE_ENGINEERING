#!/usr/bin/env python3
"""
Truth Comparison - Compare unified decoder output against tournament truth data.

Features:
  - Auto-detect team label swaps (left/right reversed)
  - Hero name normalization (Malene/Mallene, Ishtar/Ishutar)
  - Fuzzy player name matching
  - Separate incomplete match (M9) from complete matches
  - Gold metric note (spent vs earned)
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from vg.core.unified_decoder import UnifiedDecoder

# Hero name aliases: truth_name -> canonical_name
HERO_ALIASES = {
    "mallene": "malene",
    "ishutar": "ishtar",
}


def normalize_hero(name: str) -> str:
    """Normalize hero name for comparison."""
    return HERO_ALIASES.get(name.lower(), name.lower())


def fuzzy_match_player(name: str, candidates: dict) -> str:
    """Try exact match first, then case-insensitive, then substring."""
    if name in candidates:
        return name
    # Case-insensitive
    for k in candidates:
        if k.lower() == name.lower():
            return k
    # Substring (handles TenshilHime vs TenshiiHime)
    for k in candidates:
        if len(k) > 5 and len(name) > 5:
            # Check if names differ by at most 2 chars
            if sum(a != b for a, b in zip(k, name)) <= 2 and abs(len(k) - len(name)) <= 1:
                return k
    return None


def detect_team_swap(decoded_players: dict, truth_players: dict) -> bool:
    """Detect if ALL team labels are swapped (left↔right)."""
    swap_count = 0
    match_count = 0
    total = 0

    for pname, tp in truth_players.items():
        dp = decoded_players.get(pname)
        if not dp:
            dp_name = fuzzy_match_player(pname, decoded_players)
            if dp_name:
                dp = decoded_players[dp_name]
        if not dp:
            continue
        total += 1
        if dp.team == tp["team"]:
            match_count += 1
        else:
            # Check if it's a swap (left↔right)
            flip = {"left": "right", "right": "left"}
            if flip.get(dp.team) == tp["team"]:
                swap_count += 1

    if total == 0:
        return False
    # If ALL (or nearly all) are swapped, it's a team label swap
    return swap_count >= total * 0.8 and match_count < total * 0.2


def load_truth(truth_path: str) -> dict:
    with open(truth_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def compare_all(truth_path: str):
    truth_data = load_truth(truth_path)
    matches = truth_data["matches"]

    # Counters for complete matches (exclude M9 incomplete)
    stats = {k: 0 for k in [
        'players', 'hero', 'team_group', 'kill', 'death', 'assist',
        'mk', 'gold', 'winner', 'matches_winner',
        # M9-included totals
        'players_all', 'kill_all', 'death_all', 'assist_all', 'mk_all',
    ]}

    kill_errors = []
    death_errors = []
    assist_errors = []
    mk_errors = []
    hero_errors = []
    winner_errors = []
    team_swap_matches = []
    missing_players = []

    for mi, truth_match in enumerate(matches):
        replay_file = truth_match["replay_file"]
        truth_info = truth_match.get("match_info", {})
        truth_players = truth_match.get("players", {})
        truth_winner = truth_info.get("winner")
        truth_duration = truth_info.get("duration_seconds")
        is_incomplete = "Incomplete" in replay_file

        match_label = f"{Path(replay_file).parent.parent.name}/{Path(replay_file).parent.name}"
        print(f"\n{'='*70}")
        print(f"Match {mi+1}: {match_label}" + (" [INCOMPLETE]" if is_incomplete else ""))
        print(f"  Truth: winner={truth_winner}, duration={truth_duration}s, "
              f"score={truth_info.get('score_left','?')}-{truth_info.get('score_right','?')}")

        try:
            decoder = UnifiedDecoder(replay_file)
            match = decoder.decode()
        except Exception as e:
            print(f"  ERROR decoding: {e}")
            continue

        # Note: We no longer re-run KDA with truth duration.
        # The decoder's own duration estimate (from crystal death / max death ts)
        # provides better post-game filtering than truth duration, which can be
        # off by 10-30s and either miss real deaths or include false positives.

        # Build name lookup (with fuzzy matching)
        decoded_by_name = {}
        for p in match.all_players:
            decoded_by_name[p.name] = p

        # Detect team label swap
        is_swapped = detect_team_swap(decoded_by_name, truth_players)
        flip = {"left": "right", "right": "left"}

        if is_swapped:
            team_swap_matches.append(mi + 1)
            print(f"  ** TEAM LABELS SWAPPED (auto-correcting) **")
            # Correct the labels
            for p in match.all_players:
                p.team = flip.get(p.team, p.team)
            match.left_team, match.right_team = match.right_team, match.left_team
            if match.winner:
                match.winner = flip.get(match.winner, match.winner)

        # Winner comparison (after swap correction)
        if truth_winner:
            stats['matches_winner'] += 1
            if not is_incomplete:
                if match.winner == truth_winner:
                    stats['winner'] += 1
                    print(f"  Winner: {match.winner} OK")
                else:
                    print(f"  Winner: {match.winner} != {truth_winner} MISMATCH")
                    winner_errors.append((mi+1, match.winner, truth_winner))

        # Duration comparison
        if match.duration_seconds and truth_duration:
            dt = abs(match.duration_seconds - truth_duration)
            print(f"  Duration: detected={match.duration_seconds}s, truth={truth_duration}s (diff={dt}s)")

        # Player comparison
        for pname, tp in truth_players.items():
            dp = decoded_by_name.get(pname)
            if not dp:
                fuzzy_name = fuzzy_match_player(pname, decoded_by_name)
                if fuzzy_name:
                    dp = decoded_by_name[fuzzy_name]
                    print(f"  (fuzzy match: {pname} -> {fuzzy_name})")

            stats['players_all'] += 1
            if not is_incomplete:
                stats['players'] += 1

            if not dp:
                print(f"  PLAYER NOT FOUND: {pname}")
                missing_players.append((mi+1, pname))
                continue

            mismatches = []

            # Hero (normalized)
            if normalize_hero(dp.hero_name) == normalize_hero(tp["hero_name"]):
                if not is_incomplete:
                    stats['hero'] += 1
            else:
                mismatches.append(f"hero: {dp.hero_name} != {tp['hero_name']}")
                hero_errors.append((mi+1, pname, dp.hero_name, tp["hero_name"]))

            # Team grouping (after swap correction)
            if dp.team == tp["team"]:
                if not is_incomplete:
                    stats['team_group'] += 1
            else:
                mismatches.append(f"team: {dp.team} != {tp['team']}")

            # Kills
            if dp.kills == tp["kills"]:
                stats['kill_all'] += 1
                if not is_incomplete:
                    stats['kill'] += 1
            else:
                diff = dp.kills - tp["kills"]
                mismatches.append(f"K: {dp.kills} != {tp['kills']} ({'+' if diff>0 else ''}{diff})")
                kill_errors.append((mi+1, pname, dp.hero_name, dp.kills, tp["kills"], diff, is_incomplete))

            # Deaths
            if dp.deaths == tp["deaths"]:
                stats['death_all'] += 1
                if not is_incomplete:
                    stats['death'] += 1
            else:
                diff = dp.deaths - tp["deaths"]
                mismatches.append(f"D: {dp.deaths} != {tp['deaths']} ({'+' if diff>0 else ''}{diff})")
                death_errors.append((mi+1, pname, dp.hero_name, dp.deaths, tp["deaths"], diff, is_incomplete))

            # Assists
            truth_assists = tp.get("assists")
            if truth_assists is not None and dp.assists is not None:
                stats['assist_all'] += 1 if dp.assists == truth_assists else 0
                if dp.assists == truth_assists:
                    if not is_incomplete:
                        stats['assist'] += 1
                else:
                    diff = dp.assists - truth_assists
                    mismatches.append(f"A: {dp.assists} != {truth_assists} ({'+' if diff>0 else ''}{diff})")
                    assist_errors.append((mi+1, pname, dp.hero_name, dp.assists, truth_assists, diff, is_incomplete))

            # Minion kills
            truth_mk = tp.get("minion_kills")
            if truth_mk is not None:
                stats['mk_all'] += 1 if dp.minion_kills == truth_mk else 0
                if dp.minion_kills == truth_mk:
                    if not is_incomplete:
                        stats['mk'] += 1
                else:
                    diff = dp.minion_kills - truth_mk
                    mismatches.append(f"MK: {dp.minion_kills} != {truth_mk} ({'+' if diff>0 else ''}{diff})")
                    mk_errors.append((mi+1, pname, dp.hero_name, dp.minion_kills, truth_mk, diff, is_incomplete))

            # Gold (gold_earned = positive action 0x06+0x0F+0x0D, truth = total gold)
            truth_gold = tp.get("gold")
            if truth_gold is not None and not is_incomplete:
                if dp.gold_spent == truth_gold:
                    stats['gold'] += 1
                earned_err = abs(dp.gold_earned - truth_gold) / truth_gold if truth_gold else 1
                if earned_err < 0.05:
                    stats['gold_5pct'] = stats.get('gold_5pct', 0) + 1
                if earned_err < 0.10:
                    stats['gold_10pct'] = stats.get('gold_10pct', 0) + 1
                stats['gold_total'] = stats.get('gold_total', 0) + 1

            if mismatches:
                print(f"  {pname} ({dp.hero_name}): {' | '.join(mismatches)}")

    # ====== SUMMARY ======
    n_complete = stats['players']
    n_all = stats['players_all']
    n_complete_assists = sum(1 for m in matches for p in m["players"].values()
                            if "assists" in p and "Incomplete" not in m["replay_file"])
    n_complete_mk = sum(1 for m in matches for p in m["players"].values()
                        if "minion_kills" in p and "Incomplete" not in m["replay_file"])
    n_all_assists = sum(1 for m in matches for p in m["players"].values() if "assists" in p)
    n_all_mk = sum(1 for m in matches for p in m["players"].values() if "minion_kills" in p)
    n_complete_matches = sum(1 for m in matches if "Incomplete" not in m["replay_file"])

    def pct(n, d):
        return f"{n}/{d} ({n/d*100:.1f}%)" if d else "N/A"

    print(f"\n{'='*70}")
    print(f"{'='*70}")
    print(f"ACCURACY REPORT")
    print(f"{'='*70}")

    print(f"\n  Complete Matches Only ({n_complete_matches} matches, {n_complete} players):")
    print(f"  {'─'*50}")
    print(f"  Hero (normalized): {pct(stats['hero'], n_complete)}")
    print(f"  Team Grouping:     {pct(stats['team_group'], n_complete)}  (after swap correction)")
    print(f"  Winner:            {pct(stats['winner'], n_complete_matches)}")
    print(f"  Kills:             {pct(stats['kill'], n_complete)}")
    print(f"  Deaths:            {pct(stats['death'], n_complete)}")
    print(f"  Assists:           {pct(stats['assist'], n_complete_assists)}")
    print(f"  Minion Kills:      {pct(stats['mk'], n_complete_mk)}")

    print(f"\n  Including Incomplete M9 ({len(matches)} matches, {n_all} players):")
    print(f"  {'─'*50}")
    print(f"  Kills:             {pct(stats['kill_all'], n_all)}")
    print(f"  Deaths:            {pct(stats['death_all'], n_all)}")

    print(f"\n  Team Label Swaps: {len(team_swap_matches)}/{len(matches)} matches")
    if team_swap_matches:
        print(f"    Swapped in: M{', M'.join(str(m) for m in team_swap_matches)}")
    print(f"  Note: team_id byte groups players correctly (100%),")
    print(f"        but 1=left/2=right mapping varies per match.")

    g_total = stats.get('gold_total', 0)
    g_5 = stats.get('gold_5pct', 0)
    g_10 = stats.get('gold_10pct', 0)
    print(f"\n  Gold (gold_earned vs truth, complete):")
    print(f"    Within ±5%:  {pct(g_5, g_total)}")
    print(f"    Within ±10%: {pct(g_10, g_total)}")
    print(f"    Note: gold_earned = sum of positive action 0x06+0x0F+0x0D credit records")

    # Error details - complete matches only
    complete_kills = [e for e in kill_errors if not e[6]]
    complete_deaths = [e for e in death_errors if not e[6]]
    complete_assists = [e for e in assist_errors if not e[6]]
    complete_mk = [e for e in mk_errors if not e[6]]

    if complete_kills:
        print(f"\n--- Kill Mismatches - Complete ({len(complete_kills)}) ---")
        for mi, pname, hero, det, truth, diff, _ in complete_kills:
            print(f"  M{mi} {pname} ({hero}): detected={det}, truth={truth} (diff={diff:+d})")

    if complete_deaths:
        print(f"\n--- Death Mismatches - Complete ({len(complete_deaths)}) ---")
        for mi, pname, hero, det, truth, diff, _ in complete_deaths:
            print(f"  M{mi} {pname} ({hero}): detected={det}, truth={truth} (diff={diff:+d})")

    if complete_assists:
        print(f"\n--- Assist Mismatches - Complete ({len(complete_assists)}) ---")
        for mi, pname, hero, det, truth, diff, _ in complete_assists:
            print(f"  M{mi} {pname} ({hero}): detected={det}, truth={truth} (diff={diff:+d})")

    if complete_mk:
        print(f"\n--- Minion Kill Mismatches - Complete ({len(complete_mk)}) ---")
        for mi, pname, hero, det, truth, diff, _ in complete_mk:
            print(f"  M{mi} {pname} ({hero}): detected={det}, truth={truth} (diff={diff:+d})")

    if hero_errors:
        print(f"\n--- Hero Mismatches (before normalization) ({len(hero_errors)}) ---")
        for mi, pname, det, truth in hero_errors:
            norm_match = normalize_hero(det) == normalize_hero(truth)
            print(f"  M{mi} {pname}: {det} != {truth}" +
                  (" (alias match)" if norm_match else " (REAL mismatch)"))

    if missing_players:
        print(f"\n--- Missing Players ({len(missing_players)}) ---")
        for mi, pname in missing_players:
            print(f"  M{mi}: {pname}")

    if winner_errors:
        print(f"\n--- Winner Mismatches after swap correction ({len(winner_errors)}) ---")
        for mi, det, truth in winner_errors:
            print(f"  M{mi}: detected={det}, truth={truth}")

    # Incomplete match details
    incomplete_kills = [e for e in kill_errors if e[6]]
    incomplete_deaths = [e for e in death_errors if e[6]]
    if incomplete_kills or incomplete_deaths:
        print(f"\n--- Incomplete Match (M9) Errors ---")
        print(f"  Kill errors: {len(incomplete_kills)}, Death errors: {len(incomplete_deaths)}")
        print(f"  (Expected: replay truncated, missing ~60% of game data)")


if __name__ == "__main__":
    truth_path = str(Path(__file__).resolve().parent.parent / "output" / "tournament_truth.json")
    compare_all(truth_path)
