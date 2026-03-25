"""Collapse minion outlier patterns into action families for same-hero comparison."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

from .minion_hero_compare import build_minion_hero_compare


def _pattern_action(pattern: str) -> str:
    return pattern.split("@", 1)[0]


def build_minion_pattern_family_compare(
    truth_path: str,
    target_replay_name: str,
    top_pattern_limit: int = 8,
) -> Dict[str, object]:
    """Compare target outlier players against same-hero peers by action family totals."""
    compare = build_minion_hero_compare(
        truth_path=truth_path,
        target_replay_name=target_replay_name,
        top_pattern_limit=top_pattern_limit,
    )

    family_names = sorted({_pattern_action(pattern) for pattern in compare["selected_patterns"]})
    rows = []
    for row in compare["rows"]:
        target_family_counts: Dict[str, int] = {family: 0 for family in family_names}
        for pattern, count in row["target_pattern_counts"].items():
            target_family_counts[_pattern_action(pattern)] += count

        peer_family_rows = []
        for peer in row["same_hero_peers"]:
            family_counts = {family: 0 for family in family_names}
            for pattern, count in peer["pattern_counts"].items():
                family_counts[_pattern_action(pattern)] += count
            peer_family_rows.append(family_counts)

        family_scores = []
        for family in family_names:
            peer_values = [peer[family] for peer in peer_family_rows]
            if peer_values:
                peer_mean = sum(peer_values) / len(peer_values)
                peer_max = max(peer_values)
                nonzero_peer_count = sum(1 for value in peer_values if value > 0)
                excess_vs_mean = target_family_counts[family] - peer_mean
                excess_vs_max = target_family_counts[family] - peer_max
            else:
                peer_mean = None
                peer_max = None
                nonzero_peer_count = 0
                excess_vs_mean = None
                excess_vs_max = None
            family_scores.append(
                {
                    "family": family,
                    "target_count": target_family_counts[family],
                    "peer_mean": peer_mean,
                    "peer_max": peer_max,
                    "nonzero_peer_count": nonzero_peer_count,
                    "peer_count": len(peer_values),
                    "excess_vs_mean": excess_vs_mean,
                    "excess_vs_max": excess_vs_max,
                }
            )
        family_scores.sort(
            key=lambda item: (
                item["excess_vs_mean"] if item["excess_vs_mean"] is not None else float("-inf"),
                item["target_count"],
            ),
            reverse=True,
        )
        rows.append(
            {
                "player_name": row["player_name"],
                "hero_name": row["hero_name"],
                "residual_vs_0e": row["residual_vs_0e"],
                "same_hero_peer_count": row["same_hero_peer_count"],
                "family_scores": family_scores,
            }
        )

    return {
        "truth_path": str(Path(truth_path).resolve()),
        "target_replay_name": target_replay_name,
        "selected_patterns": compare["selected_patterns"],
        "families": family_names,
        "rows": rows,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Compare minion outlier patterns by action family against same-hero peers.")
    parser.add_argument("--truth", default="vg/output/tournament_truth.json", help="Truth JSON path")
    parser.add_argument("--replay-name", required=True, help="Target replay_name from truth JSON")
    parser.add_argument("--top-pattern-limit", type=int, default=8, help="How many outlier patterns to include")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(argv)

    report = build_minion_pattern_family_compare(
        truth_path=args.truth,
        target_replay_name=args.replay_name,
        top_pattern_limit=args.top_pattern_limit,
    )
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Minion pattern family compare saved to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
