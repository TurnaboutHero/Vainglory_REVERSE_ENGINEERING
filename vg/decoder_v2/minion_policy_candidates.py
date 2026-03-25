"""Evaluate conservative candidate policies for partial minion acceptance."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

from .minion_ratio_profile import build_minion_ratio_profile


def _series_is_finals(series: str) -> bool:
    return "Law Enforcers (Finals)" in series


def _score_policy(rows: List[Dict[str, object]], accepted_rows: List[Dict[str, object]], policy_name: str) -> Dict[str, object]:
    accepted_exact = sum(1 for row in accepted_rows if row["residual_vs_0e"] == 0)
    accepted_error = len(accepted_rows) - accepted_exact
    precision = accepted_exact / len(accepted_rows) if accepted_rows else 0.0
    coverage = len(accepted_rows) / len(rows) if rows else 0.0
    finals_rows = [row for row in accepted_rows if _series_is_finals(row["series"])]
    nonfinals_rows = [row for row in accepted_rows if not _series_is_finals(row["series"])]
    return {
        "policy": policy_name,
        "accepted_rows": len(accepted_rows),
        "accepted_exact": accepted_exact,
        "accepted_error": accepted_error,
        "precision": precision,
        "coverage": coverage,
        "accepted_finals_rows": len(finals_rows),
        "accepted_nonfinals_rows": len(nonfinals_rows),
    }


def build_minion_policy_candidates(truth_path: str) -> Dict[str, object]:
    """Evaluate simple conservative policy candidates for partial minion export."""
    profile = build_minion_ratio_profile(truth_path)
    rows = profile["rows"]
    metrics = ["solo_ratio", "mixed_ratio"] + [
        key for key in rows[0].keys()
        if key.endswith("_ratio") and key not in {"solo_ratio", "mixed_ratio"}
    ]

    policies = []

    nonfinals = [row for row in rows if not _series_is_finals(row["series"])]
    policies.append(_score_policy(rows, nonfinals, "accept_nonfinals_only"))

    for metric in metrics:
        thresholds = sorted({row[metric] for row in rows if row[metric] is not None})
        for threshold in thresholds:
            accepted = [row for row in rows if row[metric] is not None and row[metric] <= threshold]
            policies.append(_score_policy(rows, accepted, f"{metric}<={threshold}"))

            hybrid = [
                row for row in rows
                if (not _series_is_finals(row["series"]))
                or (row[metric] is not None and row[metric] <= threshold)
            ]
            policies.append(_score_policy(rows, hybrid, f"nonfinals_or_{metric}<={threshold}"))

    policies.sort(
        key=lambda row: (
            row["precision"],
            row["coverage"],
            -row["accepted_error"],
        ),
        reverse=True,
    )

    return {
        "truth_path": str(Path(truth_path).resolve()),
        "row_count": len(rows),
        "top_policies": policies[:40],
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate conservative candidate policies for partial minion acceptance.")
    parser.add_argument("--truth", default="vg/output/tournament_truth.json", help="Truth JSON path")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(argv)

    report = build_minion_policy_candidates(args.truth)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Minion policy candidates saved to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
