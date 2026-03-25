"""Research ratio-based rules for minion outlier detection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

from .minion_ratio_profile import build_minion_ratio_profile


def build_minion_ratio_rule_research(truth_path: str) -> Dict[str, object]:
    """Find best ratio thresholds for positive residual rows."""
    profile = build_minion_ratio_profile(truth_path)
    rows = profile["rows"]
    positive_rows = [row for row in rows if row["residual_vs_0e"] > 0]
    zero_rows = [row for row in rows if row["residual_vs_0e"] == 0]
    metrics = ["solo_ratio", "mixed_ratio"] + [
        key for key in rows[0].keys()
        if key.endswith("_ratio") and key not in {"solo_ratio", "mixed_ratio"}
    ]

    result_rows = []
    for metric in metrics:
        values = sorted({row[metric] for row in rows if row[metric] is not None})
        best = None
        for threshold in values:
            tp = sum(1 for row in positive_rows if row[metric] > threshold)
            fp = sum(1 for row in zero_rows if row[metric] > threshold)
            fn = sum(1 for row in positive_rows if row[metric] <= threshold)
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
                "metric": metric,
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
    parser = argparse.ArgumentParser(description="Research ratio-based rules for minion outlier detection.")
    parser.add_argument("--truth", default="vg/output/tournament_truth.json", help="Truth JSON path")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(argv)

    report = build_minion_ratio_rule_research(args.truth)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Minion ratio rule research saved to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
