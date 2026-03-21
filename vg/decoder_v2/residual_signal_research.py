"""Research sparse residual signals beyond the 0x0E minion baseline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .minion_research import (
    _load_player_action_counters,
    _load_player_credit_counters,
    _load_truth_matches,
)


def _pearson(xs: Iterable[float], ys: Iterable[float]) -> float:
    x_list = list(xs)
    y_list = list(ys)
    if not x_list or len(x_list) != len(y_list):
        return 0.0
    mean_x = sum(x_list) / len(x_list)
    mean_y = sum(y_list) / len(y_list)
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_list, y_list)) / len(x_list)
    var_x = sum((x - mean_x) ** 2 for x in x_list) / len(x_list)
    var_y = sum((y - mean_y) ** 2 for y in y_list) / len(y_list)
    if var_x <= 0 or var_y <= 0:
        return 0.0
    return cov / ((var_x ** 0.5) * (var_y ** 0.5))


def summarize_residual_candidate(
    residual_rows: List[Dict[str, object]],
    counts_by_row: List[int],
) -> Dict[str, object]:
    """Summarize how well a sparse feature explains positive residuals."""
    if len(residual_rows) != len(counts_by_row):
        raise ValueError("Row/count length mismatch")

    residuals = [int(row["residual_vs_0e"]) for row in residual_rows]
    positive_mask = [residual > 0 for residual in residuals]
    positive_total = sum(1 for value in positive_mask if value)
    support_total = sum(1 for count in counts_by_row if count > 0)
    support_positive = sum(1 for count, is_positive in zip(counts_by_row, positive_mask) if count > 0 and is_positive)
    support_zero_or_negative = sum(
        1 for count, is_positive in zip(counts_by_row, positive_mask) if count > 0 and not is_positive
    )
    precision_positive = (support_positive / support_total) if support_total else 0.0
    recall_positive = (support_positive / positive_total) if positive_total else 0.0
    f1_positive = 0.0
    if precision_positive and recall_positive:
        f1_positive = 2 * precision_positive * recall_positive / (precision_positive + recall_positive)

    positive_residuals = [residual for residual in residuals if residual > 0]
    positive_counts = [count for count, residual in zip(counts_by_row, residuals) if residual > 0]
    zero_or_negative_counts = [count for count, residual in zip(counts_by_row, residuals) if residual <= 0]
    exact_match_positive = sum(
        1 for count, residual in zip(counts_by_row, residuals) if residual > 0 and count == residual
    )
    mae_to_residual = (
        sum(abs(count - residual) for count, residual in zip(counts_by_row, residuals)) / len(counts_by_row)
        if counts_by_row
        else 0.0
    )

    summary = {
        "rows": len(counts_by_row),
        "positive_residual_rows": positive_total,
        "support_rows": support_total,
        "support_positive_rows": support_positive,
        "support_zero_or_negative_rows": support_zero_or_negative,
        "precision_positive": precision_positive,
        "recall_positive": recall_positive,
        "f1_positive": f1_positive,
        "mean_count_positive": (sum(positive_counts) / len(positive_counts)) if positive_counts else 0.0,
        "mean_count_zero_or_negative": (
            sum(zero_or_negative_counts) / len(zero_or_negative_counts)
        ) if zero_or_negative_counts else 0.0,
        "max_count_zero_or_negative": max(zero_or_negative_counts) if zero_or_negative_counts else 0,
        "exact_match_positive_rows": exact_match_positive,
        "exact_match_positive_rate": (exact_match_positive / positive_total) if positive_total else 0.0,
        "mae_to_residual": mae_to_residual,
        "corr_to_residual": _pearson(counts_by_row, residuals),
        "positive_residual_values": positive_residuals,
        "positive_feature_counts": positive_counts,
    }
    return summary


def _collect_residual_rows(truth_path: str) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    matches = _load_truth_matches(truth_path)
    complete_matches = [match for match in matches if "Incomplete" not in Path(match["replay_file"]).parent.name]
    for match in complete_matches:
        credit_counters = _load_player_credit_counters(match["replay_file"])
        action_counters = _load_player_action_counters(match["replay_file"])
        for player_name, player_truth in match["players"].items():
            if player_name not in credit_counters:
                continue
            truth_mk = player_truth.get("minion_kills")
            if truth_mk is None:
                continue
            baseline_0e = credit_counters[player_name][(0x0E, 1.0)]
            rows.append(
                {
                    "fixture_directory": Path(match["replay_file"]).parent.name,
                    "replay_name": match["replay_name"],
                    "player_name": player_name,
                    "truth_minion_kills": truth_mk,
                    "baseline_0e": baseline_0e,
                    "residual_vs_0e": truth_mk - baseline_0e,
                    "credit_counter": credit_counters[player_name],
                    "action_counter": action_counters.get(player_name, {}),
                }
            )
    return rows


def build_residual_signal_report(truth_path: str) -> Dict[str, object]:
    residual_rows = _collect_residual_rows(truth_path)
    credit_candidates = []
    action_candidates = []

    candidate_keys = set()
    action_keys = set()
    for row in residual_rows:
        candidate_keys.update(row["credit_counter"].keys())
        action_keys.update(row["action_counter"].keys())

    for action, value in sorted(candidate_keys):
        counts = [row["credit_counter"].get((action, value), 0) for row in residual_rows]
        summary = summarize_residual_candidate(residual_rows, counts)
        if summary["support_rows"] < 5 or summary["support_positive_rows"] < 2:
            continue
        credit_candidates.append(
            {
                "action": action,
                "value": value,
                **summary,
            }
        )

    for action in sorted(action_keys):
        counts = [row["action_counter"].get(action, 0) for row in residual_rows]
        summary = summarize_residual_candidate(residual_rows, counts)
        if summary["support_rows"] < 8 or summary["support_positive_rows"] < 2:
            continue
        action_candidates.append(
            {
                "action": action,
                **summary,
            }
        )

    def _rank_key(item: Dict[str, object]) -> Tuple[float, float, float, float, float]:
        return (
            float(item["f1_positive"]),
            float(item["exact_match_positive_rate"]),
            float(item["precision_positive"]),
            float(item["recall_positive"]),
            -float(item["mae_to_residual"]),
        )

    credit_candidates.sort(key=_rank_key, reverse=True)
    action_candidates.sort(key=_rank_key, reverse=True)

    positive_rows = [row for row in residual_rows if row["residual_vs_0e"] > 0]
    positive_case_details = []
    for row in positive_rows:
        credit_matches = []
        for item in credit_candidates[:30]:
            count = row["credit_counter"].get((item["action"], item["value"]), 0)
            if count <= 0:
                continue
            credit_matches.append(
                {
                    "action": item["action"],
                    "value": item["value"],
                    "count": count,
                    "matches_residual_exactly": count == row["residual_vs_0e"],
                }
            )
        action_matches = []
        for item in action_candidates[:30]:
            count = row["action_counter"].get(item["action"], 0)
            if count <= 0:
                continue
            action_matches.append(
                {
                    "action": item["action"],
                    "count": count,
                    "matches_residual_exactly": count == row["residual_vs_0e"],
                }
            )
        positive_case_details.append(
            {
                "fixture_directory": row["fixture_directory"],
                "replay_name": row["replay_name"],
                "player_name": row["player_name"],
                "truth_minion_kills": row["truth_minion_kills"],
                "baseline_0e": row["baseline_0e"],
                "residual_vs_0e": row["residual_vs_0e"],
                "top_credit_candidate_hits": credit_matches[:12],
                "top_action_candidate_hits": action_matches[:12],
            }
        )

    return {
        "truth_path": str(Path(truth_path).resolve()),
        "rows": len(residual_rows),
        "positive_residual_rows": len(positive_rows),
        "positive_residual_distribution": sorted(
            [int(row["residual_vs_0e"]) for row in positive_rows]
        ),
        "top_credit_candidates": credit_candidates[:60],
        "top_action_candidates": action_candidates[:60],
        "positive_case_details": positive_case_details,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Research sparse residual signals beyond the 0x0E minion baseline.")
    parser.add_argument("--truth", default="vg/output/tournament_truth.json", help="Truth JSON path")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(argv)

    report = build_residual_signal_report(args.truth)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Residual signal report saved to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
