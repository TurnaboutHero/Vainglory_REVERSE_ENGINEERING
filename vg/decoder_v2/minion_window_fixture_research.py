"""Aggregate same-frame minion window research across complete fixtures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .minion_research import _load_truth_matches
from .minion_window_research import DEFAULT_HEADER_HEXES, build_minion_window_report


def _differential_items(rows: List[Dict[str, object]], label_name: str) -> Dict[str, Dict[str, object]]:
    return {
        str(row[label_name]): row
        for row in rows
    }


def build_minion_window_fixture_report(
    truth_path: str,
    byte_window: int = 96,
    header_hexes: Iterable[str] = DEFAULT_HEADER_HEXES,
) -> Dict[str, object]:
    """Build a cross-fixture report for minion same-frame window signals."""
    matches = _load_truth_matches(truth_path)
    complete_matches = [match for match in matches if "Incomplete" not in Path(match["replay_file"]).parent.name]

    global_positive_target_samples = 0
    global_nonpositive_target_samples = 0
    positive_header_counts: Dict[str, int] = {}
    nonpositive_header_counts: Dict[str, int] = {}
    positive_pattern_counts: Dict[str, int] = {}
    nonpositive_pattern_counts: Dict[str, int] = {}
    per_match = []

    for match in complete_matches:
        report = build_minion_window_report(
            replay_file=match["replay_file"],
            truth_path=truth_path,
            byte_window=byte_window,
            header_hexes=header_hexes,
        )
        aggregate = report["aggregate"]
        global_positive_target_samples += aggregate["positive_target_samples"]
        global_nonpositive_target_samples += aggregate["nonpositive_target_samples"]

        for item in aggregate["positive_header_summary"]:
            key = str(item["header_hex"])
            positive_header_counts[key] = positive_header_counts.get(key, 0) + int(item["count"])
        for item in aggregate["nonpositive_header_summary"]:
            key = str(item["header_hex"])
            nonpositive_header_counts[key] = nonpositive_header_counts.get(key, 0) + int(item["count"])
        for item in aggregate["positive_credit_pattern_summary"]:
            key = str(item["pattern"])
            positive_pattern_counts[key] = positive_pattern_counts.get(key, 0) + int(item["count"])
        for item in aggregate["nonpositive_credit_pattern_summary"]:
            key = str(item["pattern"])
            nonpositive_pattern_counts[key] = nonpositive_pattern_counts.get(key, 0) + int(item["count"])

        per_match.append(
            {
                "fixture_directory_name": Path(match["replay_file"]).parent.name,
                "fixture_directory": str(Path(match["replay_file"]).parent.resolve()),
                "replay_name": match["replay_name"],
                "positive_residual_players": aggregate["positive_residual_players"],
                "nonpositive_or_unknown_players": aggregate["nonpositive_or_unknown_players"],
                "positive_target_samples": aggregate["positive_target_samples"],
                "nonpositive_target_samples": aggregate["nonpositive_target_samples"],
                "top_enriched_headers": aggregate["positive_enriched_headers"][:8],
                "top_enriched_credit_patterns": aggregate["positive_enriched_credit_patterns"][:8],
            }
        )

    def _summarize(
        positive_counts: Dict[str, int],
        nonpositive_counts: Dict[str, int],
        positive_total: int,
        nonpositive_total: int,
        label_name: str,
    ) -> List[Dict[str, object]]:
        rows = []
        for key in set(positive_counts) | set(nonpositive_counts):
            positive_count = positive_counts.get(key, 0)
            nonpositive_count = nonpositive_counts.get(key, 0)
            if positive_count + nonpositive_count < 20:
                continue
            positive_rate = (positive_count / positive_total) if positive_total else 0.0
            nonpositive_rate = (nonpositive_count / nonpositive_total) if nonpositive_total else 0.0
            rows.append(
                {
                    label_name: key,
                    "positive_count": positive_count,
                    "nonpositive_count": nonpositive_count,
                    "positive_per_target_event": positive_rate,
                    "nonpositive_per_target_event": nonpositive_rate,
                    "delta_per_target_event": positive_rate - nonpositive_rate,
                    "rate_ratio": (positive_rate / nonpositive_rate) if nonpositive_rate else None,
                }
            )
        rows.sort(
            key=lambda item: (
                item["delta_per_target_event"],
                item["positive_count"] - item["nonpositive_count"],
            ),
            reverse=True,
        )
        return rows[:30]

    return {
        "truth_path": str(Path(truth_path).resolve()),
        "complete_fixture_matches": len(complete_matches),
        "byte_window": byte_window,
        "global_positive_target_samples": global_positive_target_samples,
        "global_nonpositive_target_samples": global_nonpositive_target_samples,
        "global_enriched_headers": _summarize(
            positive_header_counts,
            nonpositive_header_counts,
            global_positive_target_samples,
            global_nonpositive_target_samples,
            "header_hex",
        ),
        "global_enriched_credit_patterns": _summarize(
            positive_pattern_counts,
            nonpositive_pattern_counts,
            global_positive_target_samples,
            global_nonpositive_target_samples,
            "pattern",
        ),
        "per_match": per_match,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Aggregate minion same-frame window research across complete fixtures.")
    parser.add_argument("--truth", default="vg/output/tournament_truth.json", help="Truth JSON path")
    parser.add_argument("--byte-window", type=int, default=96, help="Byte radius around each target event")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(argv)

    report = build_minion_window_fixture_report(
        truth_path=args.truth,
        byte_window=args.byte_window,
    )
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Minion window fixture report saved to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
