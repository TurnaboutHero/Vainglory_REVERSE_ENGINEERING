"""Research series-gated hero+bucket rules for minion outlier detection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

from vg.core.vgr_parser import VGRParser

from .minion_research import _load_player_credit_counters, _load_truth_matches


TARGET_PATTERNS = ("0x02@17.4", "0x02@14.34", "0x02@9.54", "0x02@4.0", "0x02@20.0", "0x02@-50.0")


def _pattern_count(counter: Dict[tuple, int], pattern: str) -> int:
    action = int(pattern[2:4], 16)
    raw_value = pattern.split("@", 1)[1]
    return counter.get((action, float(raw_value)), 0)


def _load_player_heroes(replay_file: str) -> Dict[str, str]:
    parsed = VGRParser(replay_file, auto_truth=False).parse()
    return {
        player["name"]: player.get("hero_name", "Unknown")
        for team in ("left", "right")
        for player in parsed["teams"][team]
    }


def _series_key(replay_file: str) -> str:
    return str(Path(replay_file).parent.parent.resolve())


def build_minion_series_bucket_rule_research(truth_path: str) -> Dict[str, object]:
    """Score hero+bucket threshold rules within each series."""
    matches = _load_truth_matches(truth_path)
    complete_matches = [match for match in matches if "Incomplete" not in Path(match["replay_file"]).parent.name]

    rows = []
    for match in complete_matches:
        counters = _load_player_credit_counters(match["replay_file"])
        heroes = _load_player_heroes(match["replay_file"])
        series = _series_key(match["replay_file"])
        for player_name, player_truth in match["players"].items():
            if player_name not in counters or player_truth.get("minion_kills") is None:
                continue
            baseline_0e = counters[player_name][(0x0E, 1.0)]
            row = {
                "series": series,
                "replay_name": match["replay_name"],
                "fixture_directory": str(Path(match["replay_file"]).parent.resolve()),
                "player_name": player_name,
                "hero_name": heroes.get(player_name, "Unknown"),
                "residual_vs_0e": player_truth["minion_kills"] - baseline_0e,
            }
            for pattern in TARGET_PATTERNS:
                row[pattern] = _pattern_count(counters[player_name], pattern)
            rows.append(row)

    grouped: Dict[tuple, List[Dict[str, object]]] = {}
    for row in rows:
        for pattern in TARGET_PATTERNS:
            key = (row["series"], row["hero_name"], pattern)
            grouped.setdefault(key, []).append(row)

    result_rows = []
    for (series, hero_name, pattern), bucket_rows in grouped.items():
        positive_rows = [row for row in bucket_rows if row["residual_vs_0e"] > 0]
        zero_rows = [row for row in bucket_rows if row["residual_vs_0e"] == 0]
        if not positive_rows or not zero_rows:
            continue
        values = sorted({row[pattern] for row in bucket_rows})
        best = None
        for threshold in values:
            tp = sum(1 for row in positive_rows if row[pattern] > threshold)
            fp = sum(1 for row in zero_rows if row[pattern] > threshold)
            fn = sum(1 for row in positive_rows if row[pattern] <= threshold)
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

        result_rows.append(
            {
                "series": series,
                "hero_name": hero_name,
                "pattern": pattern,
                "positive_row_count": len(positive_rows),
                "zero_row_count": len(zero_rows),
                "positive_values": [row[pattern] for row in positive_rows],
                "zero_values": [row[pattern] for row in zero_rows],
                "best_threshold_rule": best,
            }
        )

    result_rows.sort(
        key=lambda row: (
            row["best_threshold_rule"]["f1"],
            row["best_threshold_rule"]["precision"],
            -row["best_threshold_rule"]["fp"],
        ),
        reverse=True,
    )

    return {
        "truth_path": str(Path(truth_path).resolve()),
        "rows": result_rows,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Research series-gated hero+bucket rules for minion outlier detection.")
    parser.add_argument("--truth", default="vg/output/tournament_truth.json", help="Truth JSON path")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(argv)

    report = build_minion_series_bucket_rule_research(args.truth)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Minion series bucket rule research saved to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
