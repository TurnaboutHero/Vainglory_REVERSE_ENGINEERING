"""Profile 0x02 subfamily behavior by tournament series / replay family."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

from .minion_outlier_risk_report import build_minion_outlier_risk_report


def _series_key(directory: str) -> str:
    path = Path(directory)
    return str(path.parent) if path.parent != path else str(path)


def build_minion_series_profile(truth_path: str) -> Dict[str, object]:
    """Profile solo/mixed 0x02 subfamily excess by replay series."""
    risk = build_minion_outlier_risk_report(truth_path)
    series_rows: Dict[str, Dict[str, object]] = defaultdict(lambda: {
        "series": "",
        "player_rows": 0,
        "positive_residual_rows": 0,
        "zero_residual_rows": 0,
        "solo_subfamily_total_sum": 0,
        "mixed_subfamily_total_sum": 0,
        "solo_excess_sum": 0.0,
        "mixed_excess_sum": 0.0,
    })

    all_rows = risk["all_rows"]

    for row in all_rows:
        key = _series_key(row["fixture_directory"])
        series = series_rows[key]
        series["series"] = key
        series["player_rows"] += 1
        if row["residual_vs_0e"] > 0:
            series["positive_residual_rows"] += 1
        elif row["residual_vs_0e"] == 0:
            series["zero_residual_rows"] += 1
        series["solo_subfamily_total_sum"] += row["solo_subfamily_total"]
        series["mixed_subfamily_total_sum"] += row["mixed_subfamily_total"]
        if row["solo_excess_vs_peer_mean"] is not None:
            series["solo_excess_sum"] += row["solo_excess_vs_peer_mean"]
        if row["mixed_excess_vs_peer_mean"] is not None:
            series["mixed_excess_sum"] += row["mixed_excess_vs_peer_mean"]

    rows = []
    for series in series_rows.values():
        player_rows = series["player_rows"] or 1
        rows.append(
            {
                "series": series["series"],
                "player_rows": series["player_rows"],
                "positive_residual_rows": series["positive_residual_rows"],
                "zero_residual_rows": series["zero_residual_rows"],
                "mean_solo_subfamily_total": series["solo_subfamily_total_sum"] / player_rows,
                "mean_mixed_subfamily_total": series["mixed_subfamily_total_sum"] / player_rows,
                "mean_solo_excess_vs_peer_mean": series["solo_excess_sum"] / player_rows,
                "mean_mixed_excess_vs_peer_mean": series["mixed_excess_sum"] / player_rows,
            }
        )
    rows.sort(
        key=lambda item: (
            item["mean_solo_excess_vs_peer_mean"],
            item["positive_residual_rows"],
            item["player_rows"],
        ),
        reverse=True,
    )

    return {
        "truth_path": str(Path(truth_path).resolve()),
        "rows": rows,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Profile 0x02 subfamily behavior by replay series.")
    parser.add_argument("--truth", default="vg/output/tournament_truth.json", help="Truth JSON path")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(argv)

    report = build_minion_series_profile(args.truth)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Minion series profile saved to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
