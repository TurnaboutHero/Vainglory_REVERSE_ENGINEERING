"""Assign expected result rows against candidate VA clusters."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

from .result_screen_cluster_candidates import build_result_screen_cluster_candidates


def build_result_screen_cluster_assignment_report(
    dump_path: str,
    expected_players: List[Dict[str, object]],
    *,
    max_gap: int = 2048,
) -> Dict[str, object]:
    candidates = build_result_screen_cluster_candidates(dump_path, expected_players, max_gap=max_gap)
    expected_by_name = {
        player["name"]: {
            "team": player["team"],
            "kda": f"{player['kills']}/{player['deaths']}/{player['assists']}",
            "gold": player.get("gold"),
        }
        for player in expected_players
    }

    assignments = []
    for candidate in candidates["candidates"]:
        rows = []
        name_set = set(candidate["names"])
        kda_set = set(candidate["kdas"])
        gold_set = set(candidate["golds"])
        for name in candidate["names"]:
            expected = expected_by_name[name]
            rows.append(
                {
                    "name": name,
                    "team": expected["team"],
                    "expected_kda": expected["kda"],
                    "expected_gold": expected["gold"],
                    "kda_present": expected["kda"] in kda_set,
                    "gold_present": expected["gold"] in gold_set if expected["gold"] else False,
                }
            )
        resolved_kda = sum(1 for row in rows if row["kda_present"])
        resolved_gold = sum(1 for row in rows if row["gold_present"])
        assignments.append(
            {
                "start_va": candidate["start_va"],
                "end_va": candidate["end_va"],
                "score": candidate["score"],
                "names": candidate["names"],
                "kdas": candidate["kdas"],
                "golds": candidate["golds"],
                "resolved_kda": resolved_kda,
                "resolved_gold": resolved_gold,
                "rows": rows,
            }
        )

    assignments.sort(key=lambda row: (row["resolved_kda"], row["resolved_gold"], row["score"]), reverse=True)
    return {
        "dump_path": str(Path(dump_path).resolve()),
        "max_gap": max_gap,
        "assignments": assignments[:20],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Assign expected result rows against candidate VA clusters.")
    parser.add_argument("--dump", required=True, help="Result-screen dump path")
    parser.add_argument("--expected", required=True, help="JSON file with expected player rows")
    parser.add_argument("--max-gap", type=int, default=2048, help="Maximum VA gap for clustering")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args()

    expected = json.loads(Path(args.expected).read_text(encoding="utf-8"))
    report = build_result_screen_cluster_assignment_report(args.dump, expected, max_gap=args.max_gap)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"Result-screen cluster assignment report saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
