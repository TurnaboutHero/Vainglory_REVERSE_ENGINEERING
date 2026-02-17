"""Gold error summary: quick per-player error rates across all matches."""

import struct, math, json, sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from vg.core.unified_decoder import UnifiedDecoder, _le_to_be

_CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])


def compute_gold(replay_path):
    """Compute gold per player using simple frame sum."""
    decoder = UnifiedDecoder(replay_path)
    match = decoder.decode()
    result = {}
    for p in match.all_players:
        result[p.name] = {
            'gold_earned': p.gold_earned,
            'hero': p.hero_name,
        }
    return result


def main():
    truth_path = Path(__file__).parent.parent / "output" / "tournament_truth.json"
    with open(truth_path) as f:
        truth_data = json.load(f)

    total_5pct = 0
    total_10pct = 0
    total_players = 0
    errors_by_match = []

    for mi, match in enumerate(truth_data['matches']):
        replay_path = match['replay_file']
        is_incomplete = "Incomplete" in replay_path
        if is_incomplete:
            continue

        truth_players = match.get('players', {})
        detected = compute_gold(replay_path)

        match_errors = []
        for pname, pdata in truth_players.items():
            truth_gold = pdata.get('gold')
            if truth_gold is None:
                continue

            det_gold = detected.get(pname, {}).get('gold_earned', 0)
            hero = detected.get(pname, {}).get('hero', '?')

            if truth_gold > 0:
                err_pct = (det_gold - truth_gold) / truth_gold * 100
            else:
                err_pct = 0

            total_players += 1
            if abs(err_pct) < 5:
                total_5pct += 1
            if abs(err_pct) < 10:
                total_10pct += 1

            match_errors.append((pname, hero, det_gold, truth_gold, err_pct))

        errors_by_match.append((mi + 1, match_errors))

    # Print summary
    print(f"Overall: ±5% {total_5pct}/{total_players} ({total_5pct/total_players*100:.1f}%), "
          f"±10% {total_10pct}/{total_players} ({total_10pct/total_players*100:.1f}%)")

    print(f"\nPer-match breakdown:")
    for mi, errors in errors_by_match:
        within_5 = sum(1 for _, _, _, _, e in errors if abs(e) < 5)
        avg_err = sum(abs(e) for _, _, _, _, e in errors) / len(errors) if errors else 0
        print(f"\n  M{mi}: {within_5}/{len(errors)} within ±5%, avg |error| = {avg_err:.1f}%")

        # Show worst errors
        worst = sorted(errors, key=lambda x: -abs(x[4]))
        for pname, hero, det, truth, err in worst:
            flag = " ***" if abs(err) >= 5 else ""
            print(f"    {pname:20s} ({hero:15s}): det={det:6d}, truth={truth:6d}, err={err:+5.1f}%{flag}")


if __name__ == '__main__':
    main()
