"""Research conservative gating rules for accepting baseline minion counts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

from .minion_ratio_profile import build_minion_ratio_profile


def build_minion_acceptance_gate_research(truth_path: str) -> Dict[str, object]:
    """Search simple one-dimensional gates that maximize exact accepted rows."""
    profile = build_minion_ratio_profile(truth_path)
    rows = profile["rows"]

    candidate_metrics = ["solo_ratio", "mixed_ratio"] + [
        key for key in rows[0].keys()
        if key.endswith("_ratio") and key not in {"solo_ratio", "mixed_ratio"}
    ]

    result_rows = []
    for metric in candidate_metrics:
        values = sorted({row[metric] for row in rows if row[metric] is not None})
        best = None
        for threshold in values:
            accepted = [row for row in rows if row[metric] <= threshold]
            withheld = [row for row in rows if row[metric] > threshold]
            accepted_exact = sum(1 for row in accepted if row["residual_vs_0e"] == 0)
            accepted_error = sum(1 for row in accepted if row["residual_vs_0e"] != 0)
            accepted_precision = accepted_exact / len(accepted) if accepted else 0.0
            coverage = len(accepted) / len(rows) if rows else 0.0
            candidate = {
                "threshold": threshold,
                "accepted_rows": len(accepted),
                "accepted_exact": accepted_exact,
                "accepted_error": accepted_error,
                "withheld_rows": len(withheld),
                "accepted_precision": accepted_precision,
                "coverage": coverage,
            }
            if best is None or (
                candidate["accepted_precision"],
                candidate["coverage"],
                -candidate["accepted_error"],
                candidate["threshold"],
            ) > (
                best["accepted_precision"],
                best["coverage"],
                -best["accepted_error"],
                best["threshold"],
            ):
                best = candidate

        result_rows.append(
            {
                "metric": metric,
                "best_gate": best,
            }
        )

    result_rows.sort(
        key=lambda row: (
            row["best_gate"]["accepted_precision"],
            row["best_gate"]["coverage"],
            -row["best_gate"]["accepted_error"],
        ),
        reverse=True,
    )

    # simple categorical gate for Finals vs non-Finals
    finals_rows = [row for row in rows if "Law Enforcers (Finals)" in row["series"]]
    non_finals_rows = [row for row in rows if "Law Enforcers (Finals)" not in row["series"]]
    non_finals_exact = sum(1 for row in non_finals_rows if row["residual_vs_0e"] == 0)
    finals_exact = sum(1 for row in finals_rows if row["residual_vs_0e"] == 0)

    return {
        "truth_path": str(Path(truth_path).resolve()),
        "row_count": len(rows),
        "metric_gates": result_rows,
        "series_gate": {
            "accept_non_finals_only": {
                "accepted_rows": len(non_finals_rows),
                "accepted_exact": non_finals_exact,
                "accepted_error": len(non_finals_rows) - non_finals_exact,
                "accepted_precision": (non_finals_exact / len(non_finals_rows)) if non_finals_rows else 0.0,
                "coverage": (len(non_finals_rows) / len(rows)) if rows else 0.0,
            },
            "accept_finals_only": {
                "accepted_rows": len(finals_rows),
                "accepted_exact": finals_exact,
                "accepted_error": len(finals_rows) - finals_exact,
                "accepted_precision": (finals_exact / len(finals_rows)) if finals_rows else 0.0,
                "coverage": (len(finals_rows) / len(rows)) if rows else 0.0,
            },
        },
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Research conservative gates for accepting baseline minion counts.")
    parser.add_argument("--truth", default="vg/output/tournament_truth.json", help="Truth JSON path")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(argv)

    report = build_minion_acceptance_gate_research(args.truth)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Minion acceptance gate research saved to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
