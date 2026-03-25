"""Cross-validate minion policy families to detect overfit candidate rules."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .minion_policy_candidates import _policy_complexity
from .minion_ratio_profile import build_minion_ratio_profile

PolicySpec = Tuple[str, Optional[str], Optional[float], Optional[int]]
FIXED_POLICY_SPECS: Tuple[PolicySpec, ...] = (
    ("accept_nonfinals_only", None, None, None),
    ("nonfinals_or_metric", "mixed_ratio", 0.13513513513513514, None),
)


def _is_finals(series: str) -> bool:
    return "Law Enforcers (Finals)" in series


def _policy_name(spec: PolicySpec) -> str:
    family, metric, threshold, floor = spec
    if family == "accept_nonfinals_only":
        return "accept_nonfinals_only"
    if family == "nonfinals_or_metric":
        return f"nonfinals_or_{metric}<={threshold}"
    if family == "nonfinals_or_metric_and_floor":
        return f"nonfinals_or_{metric}<={threshold}_and_baseline_0e>={floor}"
    raise ValueError(f"Unknown policy family: {family}")


def _accept_row(row: Dict[str, object], spec: PolicySpec) -> bool:
    family, metric, threshold, floor = spec
    finals = _is_finals(str(row["series"]))
    if family == "accept_nonfinals_only":
        return not finals
    if family == "nonfinals_or_metric":
        return (not finals) or float(row[str(metric)]) <= float(threshold)
    if family == "nonfinals_or_metric_and_floor":
        return (not finals) or (
            float(row[str(metric)]) <= float(threshold)
            and int(row["baseline_0e"]) >= int(floor)
        )
    raise ValueError(f"Unknown policy family: {family}")


def _score_policy(rows: Sequence[Dict[str, object]], spec: PolicySpec) -> Dict[str, object]:
    accepted = [row for row in rows if _accept_row(row, spec)]
    exact = sum(int(row["residual_vs_0e"] == 0) for row in accepted)
    errors = len(accepted) - exact
    precision = exact / len(accepted) if accepted else 0.0
    coverage = len(accepted) / len(rows) if rows else 0.0
    finals_accepted = [row for row in accepted if _is_finals(str(row["series"]))]
    finals_exact = sum(int(row["residual_vs_0e"] == 0) for row in finals_accepted)
    return {
        "policy": _policy_name(spec),
        "family": spec[0],
        "metric": spec[1],
        "threshold": spec[2],
        "baseline_floor": spec[3],
        "accepted_rows": len(accepted),
        "accepted_exact": exact,
        "accepted_error": errors,
        "precision": precision,
        "coverage": coverage,
        "accepted_finals_rows": len(finals_accepted),
        "accepted_finals_exact": finals_exact,
        "accepted_finals_error": len(finals_accepted) - finals_exact,
        "complexity": _policy_complexity(_policy_name(spec)),
    }


def _iter_policy_specs(rows: Sequence[Dict[str, object]]) -> Iterable[PolicySpec]:
    if not rows:
        return []
    metrics = ["mixed_ratio", "solo_ratio"]
    thresholds_by_metric = {
        metric: sorted({float(row[metric]) for row in rows if row.get(metric) is not None})
        for metric in metrics
    }
    floors = sorted({int(row["baseline_0e"]) for row in rows if row.get("baseline_0e") is not None})

    specs: List[PolicySpec] = [("accept_nonfinals_only", None, None, None)]
    for metric in metrics:
        for threshold in thresholds_by_metric[metric]:
            specs.append(("nonfinals_or_metric", metric, threshold, None))
            for floor in floors:
                specs.append(("nonfinals_or_metric_and_floor", metric, threshold, floor))
    return specs


def _pick_best_training_policy(rows: Sequence[Dict[str, object]]) -> Dict[str, object]:
    best: Optional[Dict[str, object]] = None
    for spec in _iter_policy_specs(rows):
        score = _score_policy(rows, spec)
        if best is None:
            best = score
            continue
        candidate_key = (
            float(score["precision"]),
            float(score["coverage"]),
            -int(score["accepted_error"]),
        )
        best_key = (
            float(best["precision"]),
            float(best["coverage"]),
            -int(best["accepted_error"]),
        )
        if candidate_key > best_key:
            best = score
    return best or _score_policy([], ("accept_nonfinals_only", None, None, None))


def _cross_validate_group(rows: Sequence[Dict[str, object]], group_key: str) -> List[Dict[str, object]]:
    groups = sorted({str(row[group_key]) for row in rows})
    results = []
    for held_group in groups:
        train_rows = [row for row in rows if str(row[group_key]) != held_group]
        test_rows = [row for row in rows if str(row[group_key]) == held_group]
        best_train = _pick_best_training_policy(train_rows)
        test_score = _score_policy(
            test_rows,
            (
                str(best_train["family"]),
                best_train["metric"],
                best_train["threshold"],
                best_train["baseline_floor"],
            ),
        )
        results.append(
            {
                "held_group": held_group,
                "train_policy": best_train,
                "test_score": test_score,
            }
        )
    return results


def _summarize_cv(results: Sequence[Dict[str, object]]) -> Dict[str, object]:
    if not results:
        return {
            "folds": 0,
            "mean_test_precision": 0.0,
            "mean_test_coverage": 0.0,
            "failed_folds": 0,
        }
    mean_precision = sum(float(row["test_score"]["precision"]) for row in results) / len(results)
    mean_coverage = sum(float(row["test_score"]["coverage"]) for row in results) / len(results)
    failed_folds = sum(int(float(row["test_score"]["precision"]) < 1.0) for row in results)
    return {
        "folds": len(results),
        "mean_test_precision": mean_precision,
        "mean_test_coverage": mean_coverage,
        "failed_folds": failed_folds,
    }


def build_minion_policy_cross_validation(truth_path: str) -> Dict[str, object]:
    profile = build_minion_ratio_profile(truth_path)
    rows = profile["rows"]
    loso = _cross_validate_group(rows, "series")
    loro = _cross_validate_group(rows, "replay_name")
    fixed_reference = [_score_policy(rows, spec) for spec in FIXED_POLICY_SPECS]
    return {
        "truth_path": str(Path(truth_path).resolve()),
        "row_count": len(rows),
        "series_count": len({str(row["series"]) for row in rows}),
        "replay_count": len({str(row["replay_name"]) for row in rows}),
        "fixed_policy_reference": fixed_reference,
        "leave_one_series_out": {
            "summary": _summarize_cv(loso),
            "folds": loso,
        },
        "leave_one_replay_out": {
            "summary": _summarize_cv(loro),
            "folds": loro,
        },
    }


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Cross-validate minion policy families for overfit detection.")
    parser.add_argument("--truth", default="vg/output/tournament_truth.json", help="Truth JSON path")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(list(argv) if argv is not None else None)

    report = build_minion_policy_cross_validation(args.truth)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Minion policy cross-validation saved to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
