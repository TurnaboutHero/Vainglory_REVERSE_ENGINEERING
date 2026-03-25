"""Summarize same-series pattern deltas for target positive-residual players."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

from .minion_series_peer_compare import build_minion_series_peer_compare


def build_minion_same_series_delta(
    truth_path: str,
    target_replay_name: str,
) -> Dict[str, object]:
    """Build a compact same-series delta summary for positive-residual players."""
    compare = build_minion_series_peer_compare(
        truth_path=truth_path,
        target_replay_name=target_replay_name,
    )

    rows = []
    for player_row in compare["rows"]:
        if player_row["residual_vs_0e"] <= 0:
            continue
        ranked = []
        for item in player_row["pattern_rows"]:
            delta = item.get("excess_vs_same_series_mean")
            if delta is None:
                continue
            ranked.append(
                {
                    "pattern": item["pattern"],
                    "target_count": item["target_count"],
                    "same_series_mean": item["same_series_mean"],
                    "other_series_mean": item["other_series_mean"],
                    "excess_vs_same_series_mean": delta,
                    "excess_vs_other_series_mean": item["excess_vs_other_series_mean"],
                }
            )
        ranked.sort(key=lambda item: item["excess_vs_same_series_mean"], reverse=True)
        rows.append(
            {
                "player_name": player_row["player_name"],
                "hero_name": player_row["hero_name"],
                "residual_vs_0e": player_row["residual_vs_0e"],
                "same_series_peer_count": player_row["same_series_peer_count"],
                "other_series_peer_count": player_row["other_series_peer_count"],
                "top_same_series_deltas": ranked[:10],
            }
        )

    return {
        "truth_path": str(Path(truth_path).resolve()),
        "target_replay_name": target_replay_name,
        "rows": rows,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize same-series pattern deltas for target positive-residual players.")
    parser.add_argument("--truth", default="vg/output/tournament_truth.json", help="Truth JSON path")
    parser.add_argument("--replay-name", required=True, help="Target replay_name from truth JSON")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(argv)

    report = build_minion_same_series_delta(
        truth_path=args.truth,
        target_replay_name=args.replay_name,
    )
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Minion same-series delta saved to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
