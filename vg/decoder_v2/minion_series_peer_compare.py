"""Compare target replay outlier players against same-series vs cross-series same-hero peers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

from .minion_hero_compare import build_minion_hero_compare


def _series_key(directory: str) -> str:
    path = Path(directory)
    return str(path.parent) if path.parent != path else str(path)


def build_minion_series_peer_compare(
    truth_path: str,
    target_replay_name: str,
) -> Dict[str, object]:
    """Compare same-hero peers split by same series vs other series."""
    compare = build_minion_hero_compare(
        truth_path=truth_path,
        target_replay_name=target_replay_name,
        top_pattern_limit=12,
    )
    matches = json.loads(Path(truth_path).read_text(encoding="utf-8")).get("matches", [])
    target_match = next(match for match in matches if match["replay_name"] == target_replay_name)
    target_series = _series_key(str(Path(target_match["replay_file"]).parent.resolve()))

    rows = []
    for row in compare["rows"]:
        same_series = []
        other_series = []
        for peer in row["same_hero_peers"]:
            peer_series = _series_key(peer["fixture_directory"])
            if peer_series == target_series:
                same_series.append(peer)
            else:
                other_series.append(peer)

        def _mean(pattern: str, peer_rows: List[Dict[str, object]]) -> Optional[float]:
            if not peer_rows:
                return None
            return sum(peer["pattern_counts"].get(pattern, 0) for peer in peer_rows) / len(peer_rows)

        pattern_rows = []
        for pattern in compare["selected_patterns"]:
            target_count = row["target_pattern_counts"].get(pattern, 0)
            same_series_mean = _mean(pattern, same_series)
            other_series_mean = _mean(pattern, other_series)
            pattern_rows.append(
                {
                    "pattern": pattern,
                    "target_count": target_count,
                    "same_series_peer_count": len(same_series),
                    "same_series_mean": same_series_mean,
                    "other_series_peer_count": len(other_series),
                    "other_series_mean": other_series_mean,
                    "excess_vs_same_series_mean": (
                        target_count - same_series_mean if same_series_mean is not None else None
                    ),
                    "excess_vs_other_series_mean": (
                        target_count - other_series_mean if other_series_mean is not None else None
                    ),
                }
            )
        pattern_rows.sort(
            key=lambda item: (
                item["excess_vs_same_series_mean"] if item["excess_vs_same_series_mean"] is not None else float("-inf"),
                item["target_count"],
            ),
            reverse=True,
        )

        rows.append(
            {
                "player_name": row["player_name"],
                "hero_name": row["hero_name"],
                "residual_vs_0e": row["residual_vs_0e"],
                "target_series": target_series,
                "same_series_peer_count": len(same_series),
                "other_series_peer_count": len(other_series),
                "pattern_rows": pattern_rows,
            }
        )

    return {
        "truth_path": str(Path(truth_path).resolve()),
        "target_replay_name": target_replay_name,
        "target_series": target_series,
        "selected_patterns": compare["selected_patterns"],
        "rows": rows,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Compare target outlier players against same-series vs cross-series same-hero peers.")
    parser.add_argument("--truth", default="vg/output/tournament_truth.json", help="Truth JSON path")
    parser.add_argument("--replay-name", required=True, help="Target replay_name from truth JSON")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(argv)

    report = build_minion_series_peer_compare(
        truth_path=args.truth,
        target_replay_name=args.replay_name,
    )
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Minion series peer compare saved to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
