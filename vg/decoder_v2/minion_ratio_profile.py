"""Profile 0x02-derived ratios against residual classes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

from vg.core.vgr_parser import VGRParser

from .minion_research import _load_player_credit_counters, _load_truth_matches


PATTERNS = ("0x02@17.4", "0x02@14.34", "0x02@9.54", "0x02@4.0", "0x02@20.0", "0x02@-50.0")


def _pattern_count(counter: Dict[tuple, int], pattern: str) -> int:
    action = int(pattern[2:4], 16)
    raw_value = pattern.split("@", 1)[1]
    return counter.get((action, float(raw_value)), 0)


def build_minion_ratio_profile(truth_path: str) -> Dict[str, object]:
    """Profile subfamily/base ratios for complete fixtures."""
    matches = _load_truth_matches(truth_path)
    complete_matches = [match for match in matches if "Incomplete" not in Path(match["replay_file"]).parent.name]

    rows = []
    for match in complete_matches:
        counters = _load_player_credit_counters(match["replay_file"])
        for player_name, player_truth in match["players"].items():
            if player_name not in counters or player_truth.get("minion_kills") is None:
                continue
            baseline = counters[player_name][(0x0E, 1.0)]
            if baseline <= 0:
                continue
            row = {
                "series": str(Path(match["replay_file"]).parent.parent.resolve()),
                "replay_name": match["replay_name"],
                "fixture_directory": str(Path(match["replay_file"]).parent.resolve()),
                "player_name": player_name,
                "residual_vs_0e": player_truth["minion_kills"] - baseline,
                "baseline_0e": baseline,
            }
            solo_total = sum(_pattern_count(counters[player_name], pattern) for pattern in PATTERNS[:4])
            mixed_total = sum(_pattern_count(counters[player_name], pattern) for pattern in PATTERNS[4:])
            row["solo_ratio"] = solo_total / baseline
            row["mixed_ratio"] = mixed_total / baseline
            for pattern in PATTERNS:
                row[f"{pattern}_ratio"] = _pattern_count(counters[player_name], pattern) / baseline
            rows.append(row)

    classes = {
        "positive": [row for row in rows if row["residual_vs_0e"] > 0],
        "zero": [row for row in rows if row["residual_vs_0e"] == 0],
    }
    summary_rows = []
    for metric in ["solo_ratio", "mixed_ratio"] + [f"{pattern}_ratio" for pattern in PATTERNS]:
        metric_summary = {"metric": metric}
        for label, labeled_rows in classes.items():
            values = [row[metric] for row in labeled_rows]
            metric_summary[f"{label}_count"] = len(values)
            metric_summary[f"{label}_mean"] = (sum(values) / len(values)) if values else None
            metric_summary[f"{label}_max"] = max(values) if values else None
        summary_rows.append(metric_summary)

    return {
        "truth_path": str(Path(truth_path).resolve()),
        "summary": summary_rows,
        "rows": rows,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Profile 0x02-derived ratios against residual classes.")
    parser.add_argument("--truth", default="vg/output/tournament_truth.json", help="Truth JSON path")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(argv)

    report = build_minion_ratio_profile(args.truth)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Minion ratio profile saved to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
