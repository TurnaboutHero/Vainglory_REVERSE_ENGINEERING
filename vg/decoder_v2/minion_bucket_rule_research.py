"""Research hero+bucket candidate rules for minion outlier detection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from vg.core.vgr_parser import VGRParser

from .minion_research import _load_player_credit_counters, _load_truth_matches


TARGET_PATTERNS = ("0x02@17.4", "0x02@14.34", "0x02@9.54", "0x02@4.0", "0x02@20.0", "0x02@-50.0")


def _pattern_count(counter: Dict[tuple, int], pattern: str) -> int:
    action = int(pattern[2:4], 16)
    raw_value = pattern.split("@", 1)[1]
    key = (action, float(raw_value))
    return counter.get(key, 0)


def _load_player_heroes(replay_file: str) -> Dict[str, str]:
    parsed = VGRParser(replay_file, auto_truth=False).parse()
    return {
        player["name"]: player.get("hero_name", "Unknown")
        for team in ("left", "right")
        for player in parsed["teams"][team]
    }


def build_minion_bucket_rule_research(truth_path: str) -> Dict[str, object]:
    """Score hero+bucket threshold rules against complete-fixture residual rows."""
    matches = _load_truth_matches(truth_path)
    complete_matches = [match for match in matches if "Incomplete" not in Path(match["replay_file"]).parent.name]

    rows = []
    for match in complete_matches:
        counters = _load_player_credit_counters(match["replay_file"])
        heroes = _load_player_heroes(match["replay_file"])
        for player_name, player_truth in match["players"].items():
            if player_name not in counters or player_truth.get("minion_kills") is None:
                continue
            baseline_0e = counters[player_name][(0x0E, 1.0)]
            row = {
                "replay_name": match["replay_name"],
                "fixture_directory": str(Path(match["replay_file"]).parent.resolve()),
                "player_name": player_name,
                "hero_name": heroes.get(player_name, "Unknown"),
                "residual_vs_0e": player_truth["minion_kills"] - baseline_0e,
            }
            for pattern in TARGET_PATTERNS:
                row[pattern] = _pattern_count(counters[player_name], pattern)
            rows.append(row)

    hero_pattern_rows = []
    hero_names = sorted({row["hero_name"] for row in rows})
    for hero_name in hero_names:
        hero_rows = [row for row in rows if row["hero_name"] == hero_name]
        if not hero_rows:
            continue
        positive_rows = [row for row in hero_rows if row["residual_vs_0e"] > 0]
        zero_rows = [row for row in hero_rows if row["residual_vs_0e"] == 0]
        if not positive_rows:
            continue

        for pattern in TARGET_PATTERNS:
            positive_values = [row[pattern] for row in positive_rows]
            zero_values = [row[pattern] for row in zero_rows]
            candidate_thresholds = sorted(set(positive_values + zero_values))
            best = None
            for threshold in candidate_thresholds:
                tp = sum(1 for value in positive_values if value > threshold)
                fp = sum(1 for value in zero_values if value > threshold)
                fn = sum(1 for value in positive_values if value <= threshold)
                precision = tp / (tp + fp) if (tp + fp) else 0.0
                recall = tp / (tp + fn) if (tp + fn) else 0.0
                f1 = (2 * precision * recall / (precision + recall)) if precision and recall else 0.0
                candidate = {
                    "threshold": threshold,
                    "tp": tp,
                    "fp": fp,
                    "fn": fn,
                    "precision": precision,
                    "recall": recall,
                    "f1": f1,
                }
                if best is None or (candidate["f1"], candidate["precision"], -candidate["fp"], candidate["threshold"]) > (
                    best["f1"],
                    best["precision"],
                    -best["fp"],
                    best["threshold"],
                ):
                    best = candidate

            hero_pattern_rows.append(
                {
                    "hero_name": hero_name,
                    "pattern": pattern,
                    "positive_row_count": len(positive_rows),
                    "zero_row_count": len(zero_rows),
                    "positive_values": positive_values,
                    "zero_values": zero_values,
                    "best_threshold_rule": best,
                }
            )

    hero_pattern_rows.sort(
        key=lambda row: (
            row["best_threshold_rule"]["f1"],
            row["best_threshold_rule"]["precision"],
            -row["best_threshold_rule"]["fp"],
        ),
        reverse=True,
    )

    return {
        "truth_path": str(Path(truth_path).resolve()),
        "rows": hero_pattern_rows,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Research hero+bucket candidate rules for minion outlier detection.")
    parser.add_argument("--truth", default="vg/output/tournament_truth.json", help="Truth JSON path")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(argv)

    report = build_minion_bucket_rule_research(args.truth)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Minion bucket rule research saved to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
