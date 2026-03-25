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
    finals_exact = sum(1 for row in finals_rows if row["residual_vs_0e"] == 0)
    return {
        "policy": policy_name,
        "accepted_rows": len(accepted_rows),
        "accepted_exact": accepted_exact,
        "accepted_error": accepted_error,
        "precision": precision,
        "coverage": coverage,
        "accepted_finals_rows": len(finals_rows),
        "accepted_finals_exact": finals_exact,
        "accepted_finals_error": len(finals_rows) - finals_exact,
        "accepted_nonfinals_rows": len(nonfinals_rows),
    }


def _policy_complexity(policy_name: str) -> int:
    complexity = 0
    if "_and_" in policy_name:
        complexity += 2
    if "0x02@" in policy_name:
        complexity += 2
    if "solo_ratio" in policy_name:
        complexity += 1
    if "mixed_ratio" in policy_name:
        complexity += 1
    if "baseline_0e>=" in policy_name:
        complexity += 1
    return complexity


def _policy_tier(policy_name: str) -> str:
    if policy_name == "accept_nonfinals_only":
        return "product_candidate"
    if policy_name.startswith("nonfinals_or_mixed_ratio<=") and "_and_" not in policy_name:
        return "experimental_candidate"
    return "research_only"


def _rank_recommended(policies: List[Dict[str, object]]) -> List[Dict[str, object]]:
    def sort_key(row: Dict[str, object]) -> tuple:
        tier = row["policy_tier"]
        tier_rank = {
            "product_candidate": 0,
            "experimental_candidate": 1,
            "research_only": 2,
        }[tier]
        return (
            tier_rank,
            -float(row["precision"]),
            -float(row["coverage"]),
            int(row["complexity"]),
            int(row["accepted_error"]),
        )

    return sorted(policies, key=sort_key)


def build_minion_policy_candidates(truth_path: str) -> Dict[str, object]:
    """Evaluate simple conservative policy candidates for partial minion export."""
    profile = build_minion_ratio_profile(truth_path)
    rows = profile["rows"]
    if not rows:
        return {
            "truth_path": str(Path(truth_path).resolve()),
            "row_count": 0,
            "top_policies": [],
        }
    metrics = ["solo_ratio", "mixed_ratio"] + [
        key for key in rows[0].keys()
        if key.endswith("_ratio") and key not in {"solo_ratio", "mixed_ratio"}
    ]
    baseline_floors = sorted({int(row["baseline_0e"]) for row in rows if row.get("baseline_0e") is not None})

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

            for floor in baseline_floors:
                floored_hybrid = [
                    row for row in rows
                    if (not _series_is_finals(row["series"]))
                    or (
                        row[metric] is not None
                        and row[metric] <= threshold
                        and int(row["baseline_0e"]) >= floor
                    )
                ]
                policies.append(
                    _score_policy(
                        rows,
                        floored_hybrid,
                        f"nonfinals_or_{metric}<={threshold}_and_baseline_0e>={floor}",
                    )
                )

    for policy in policies:
        policy["complexity"] = _policy_complexity(str(policy["policy"]))
        policy["policy_tier"] = _policy_tier(str(policy["policy"]))

    raw_ranked = sorted(
        policies,
        key=lambda row: (
            row["precision"],
            row["coverage"],
            -row["accepted_error"],
        ),
        reverse=True,
    )

    recommended_ranked = _rank_recommended(policies)

    return {
        "truth_path": str(Path(truth_path).resolve()),
        "row_count": len(rows),
        "top_policies": raw_ranked[:40],
        "recommended_policies": recommended_ranked[:20],
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
