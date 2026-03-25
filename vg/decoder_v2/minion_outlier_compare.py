"""Compare one minion outlier replay against complete-fixture baselines."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .minion_research import _load_truth_matches
from .minion_window_research import DEFAULT_HEADER_HEXES, build_minion_window_report


def _counter_from_rows(rows: List[Dict[str, object]], key_name: str) -> Dict[str, int]:
    return {str(row[key_name]): int(row["count"]) for row in rows}


def _compare_rates(
    target_counts: Dict[str, int],
    baseline_counts: Dict[str, int],
    target_total: int,
    baseline_total: int,
    key_name: str,
) -> List[Dict[str, object]]:
    rows = []
    for key in set(target_counts) | set(baseline_counts):
        target_count = target_counts.get(key, 0)
        baseline_count = baseline_counts.get(key, 0)
        if target_count + baseline_count < 20:
            continue
        target_rate = (target_count / target_total) if target_total else 0.0
        baseline_rate = (baseline_count / baseline_total) if baseline_total else 0.0
        rows.append(
            {
                key_name: key,
                "target_count": target_count,
                "baseline_count": baseline_count,
                "target_per_target_event": target_rate,
                "baseline_per_target_event": baseline_rate,
                "delta_per_target_event": target_rate - baseline_rate,
                "rate_ratio": (target_rate / baseline_rate) if baseline_rate else None,
            }
        )
    rows.sort(
        key=lambda item: (
            item["delta_per_target_event"],
            item["target_count"] - item["baseline_count"],
        ),
        reverse=True,
    )
    return rows[:40]


def build_minion_outlier_compare(
    truth_path: str,
    target_replay_name: str,
    byte_window: int = 96,
    header_hexes: Iterable[str] = DEFAULT_HEADER_HEXES,
) -> Dict[str, object]:
    """Compare a target outlier replay against other complete fixtures."""
    matches = _load_truth_matches(truth_path)
    complete_matches = [match for match in matches if "Incomplete" not in Path(match["replay_file"]).parent.name]
    target_match = next(match for match in complete_matches if match["replay_name"] == target_replay_name)

    target_report = build_minion_window_report(
        replay_file=target_match["replay_file"],
        truth_path=truth_path,
        byte_window=byte_window,
        header_hexes=header_hexes,
    )

    baseline_positive_target_samples = 0
    baseline_nonpositive_target_samples = 0
    baseline_header_counts: Dict[str, int] = {}
    baseline_pattern_counts: Dict[str, int] = {}
    reference_matches = []

    for match in complete_matches:
        if match["replay_name"] == target_replay_name:
            continue
        report = build_minion_window_report(
            replay_file=match["replay_file"],
            truth_path=truth_path,
            byte_window=byte_window,
            header_hexes=header_hexes,
        )
        aggregate = report["aggregate"]
        baseline_positive_target_samples += aggregate["positive_target_samples"]
        baseline_nonpositive_target_samples += aggregate["nonpositive_target_samples"]

        for item in aggregate["positive_header_summary"]:
            key = str(item["header_hex"])
            baseline_header_counts[key] = baseline_header_counts.get(key, 0) + int(item["count"])
        for item in aggregate["nonpositive_header_summary"]:
            key = str(item["header_hex"])
            baseline_header_counts[key] = baseline_header_counts.get(key, 0) + int(item["count"])
        for item in aggregate["positive_credit_pattern_summary"]:
            key = str(item["pattern"])
            baseline_pattern_counts[key] = baseline_pattern_counts.get(key, 0) + int(item["count"])
        for item in aggregate["nonpositive_credit_pattern_summary"]:
            key = str(item["pattern"])
            baseline_pattern_counts[key] = baseline_pattern_counts.get(key, 0) + int(item["count"])

        reference_matches.append(
            {
                "fixture_directory": str(Path(match["replay_file"]).parent.resolve()),
                "replay_name": match["replay_name"],
                "positive_residual_players": aggregate["positive_residual_players"],
                "positive_target_samples": aggregate["positive_target_samples"],
                "nonpositive_target_samples": aggregate["nonpositive_target_samples"],
            }
        )

    target_aggregate = target_report["aggregate"]
    target_header_counts = _counter_from_rows(target_aggregate["positive_header_summary"], "header_hex")
    target_pattern_counts = _counter_from_rows(target_aggregate["positive_credit_pattern_summary"], "pattern")
    target_total = int(target_aggregate["positive_target_samples"]) or int(target_aggregate["nonpositive_target_samples"])
    baseline_total = baseline_positive_target_samples + baseline_nonpositive_target_samples

    return {
        "truth_path": str(Path(truth_path).resolve()),
        "target_replay_name": target_replay_name,
        "target_fixture_directory": str(Path(target_match["replay_file"]).parent.resolve()),
        "byte_window": byte_window,
        "target_positive_residual_players": target_aggregate["positive_residual_players"],
        "target_positive_target_samples": target_aggregate["positive_target_samples"],
        "reference_match_count": len(reference_matches),
        "reference_total_target_samples": baseline_total,
        "header_rate_deltas": _compare_rates(
            target_header_counts,
            baseline_header_counts,
            target_total,
            baseline_total,
            "header_hex",
        ),
        "credit_pattern_rate_deltas": _compare_rates(
            target_pattern_counts,
            baseline_pattern_counts,
            target_total,
            baseline_total,
            "pattern",
        ),
        "reference_matches": reference_matches,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Compare one minion outlier replay against complete-fixture baselines.")
    parser.add_argument("--truth", default="vg/output/tournament_truth.json", help="Truth JSON path")
    parser.add_argument("--replay-name", required=True, help="Target replay_name from truth JSON")
    parser.add_argument("--byte-window", type=int, default=96, help="Byte radius around each target event")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(argv)

    report = build_minion_outlier_compare(
        truth_path=args.truth,
        target_replay_name=args.replay_name,
        byte_window=args.byte_window,
    )
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Minion outlier compare saved to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
