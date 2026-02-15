#!/usr/bin/env python3
"""
Validate binary hero ID detection against tournament truth data.
Tests the new BINARY_HERO_ID_MAP at offset 0x0A9.
"""

import json
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent / "core"))
from vgr_parser import VGRParser

HERO_NORM = {
    "mallene": "Malene", "ishutar": "Ishtar",
}

def normalize(name):
    return HERO_NORM.get(name.lower().strip(), name.strip())


def main():
    truth_path = Path(__file__).parent.parent / "output" / "tournament_truth.json"
    with open(truth_path, 'r', encoding='utf-8') as f:
        truth = json.load(f)

    total = 0
    correct = 0
    wrong = 0
    not_detected = 0
    not_in_truth = 0
    mismatches = []
    per_hero = Counter()
    per_hero_correct = Counter()

    for match in truth.get("matches", []):
        replay_file = match.get("replay_file", "")
        replay_name = match.get("replay_name", "")
        truth_players = match.get("players", {})

        path = Path(replay_file)
        if not path.exists():
            continue

        parser = VGRParser(str(path), auto_truth=False)
        parsed = parser.parse()

        # Build lookup from parsed players
        parsed_players = {}
        for team_label in ("left", "right"):
            for p in parsed["teams"].get(team_label, []):
                parsed_players[p["name"]] = p

        # Match against truth
        for truth_name, truth_data in truth_players.items():
            expected_hero = normalize(truth_data["hero_name"])

            # Find matching parsed player
            found = None
            for pname, pdata in parsed_players.items():
                clean_t = truth_name.split("_", 1)[-1] if "_" in truth_name else truth_name
                clean_p = pname.split("_", 1)[-1] if "_" in pname else pname
                if (pname == truth_name or
                    pname.lower() == truth_name.lower() or
                    clean_p.lower() == clean_t.lower()):
                    found = pdata
                    break

            if not found:
                not_in_truth += 1
                continue

            detected_hero = found.get("hero_name", "Unknown")
            total += 1
            per_hero[expected_hero] += 1

            if detected_hero == expected_hero:
                correct += 1
                per_hero_correct[expected_hero] += 1
            elif detected_hero == "Unknown" or detected_hero.startswith("unknown_"):
                not_detected += 1
                mismatches.append({
                    "player": truth_name,
                    "replay": replay_name[:40],
                    "expected": expected_hero,
                    "detected": detected_hero,
                    "type": "not_detected",
                })
            else:
                wrong += 1
                mismatches.append({
                    "player": truth_name,
                    "replay": replay_name[:40],
                    "expected": expected_hero,
                    "detected": detected_hero,
                    "type": "wrong",
                })

    accuracy = correct / total * 100 if total > 0 else 0

    print("=" * 70)
    print("BINARY HERO ID VALIDATION RESULTS")
    print("=" * 70)
    print(f"Total players tested:  {total}")
    print(f"Correct:               {correct} ({accuracy:.1f}%)")
    print(f"Wrong hero:            {wrong}")
    print(f"Not detected:          {not_detected}")
    print(f"Not matched to truth:  {not_in_truth}")
    print()

    if mismatches:
        print(f"--- MISMATCHES ({len(mismatches)}) ---")
        for m in mismatches:
            print(f"  [{m['type']}] {m['player']}: expected={m['expected']}, got={m['detected']}")
        print()

    print("--- PER-HERO ACCURACY ---")
    for hero in sorted(per_hero.keys()):
        h_total = per_hero[hero]
        h_correct = per_hero_correct.get(hero, 0)
        h_acc = h_correct / h_total * 100 if h_total > 0 else 0
        status = "OK" if h_acc == 100 else "FAIL"
        print(f"  {hero:<20} {h_correct:>3}/{h_total:<3} ({h_acc:>5.1f}%) {status}")

    # Save results
    result = {
        "total": total,
        "correct": correct,
        "accuracy_pct": round(accuracy, 2),
        "wrong": wrong,
        "not_detected": not_detected,
        "mismatches": mismatches,
    }
    output_path = Path(__file__).parent.parent / "output" / "binary_hero_validation.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to: {output_path}")


if __name__ == "__main__":
    main()
