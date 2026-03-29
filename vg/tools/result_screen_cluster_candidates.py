"""Score virtual-address clusters for result-screen row reconstruction."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .result_screen_va_cluster_report import build_result_screen_va_cluster_report


def build_result_screen_cluster_candidates(
    dump_path: str,
    expected_players: List[Dict[str, object]],
    *,
    max_gap: int = 2048,
) -> Dict[str, object]:
    values: List[str] = []
    name_to_expected = {}
    expected_golds = set()
    for player in expected_players:
        name = str(player["name"])
        kda = f"{player['kills']}/{player['deaths']}/{player['assists']}"
        values.extend([name, kda])
        name_to_expected[name] = {
            "team": player["team"],
            "hero_name": player.get("hero_name"),
            "kda": kda,
            "gold": player.get("gold"),
        }
        if player.get("gold"):
            gold_value = str(player["gold"])
            values.append(gold_value)
            expected_golds.add(gold_value)

    report = build_result_screen_va_cluster_report(dump_path, values, max_gap=max_gap)
    candidates = []
    for cluster in report["clusters"]:
        names = [value for value in cluster["distinct_values"] if value in name_to_expected]
        kdas = [value for value in cluster["distinct_values"] if "/" in value]
        golds = [value for value in cluster["distinct_values"] if value in expected_golds]
        teams = sorted({name_to_expected[name]["team"] for name in names})
        score = len(names) * 10 + len(kdas) * 6 + len(golds) * 4 - cluster["span"] / 256
        candidates.append(
            {
                "start_va": cluster["start_va"],
                "end_va": cluster["end_va"],
                "span": cluster["span"],
                "names": names,
                "kdas": kdas,
                "golds": golds,
                "teams": teams,
                "item_count": cluster["item_count"],
                "score": score,
                "items": cluster["items"],
            }
        )
    candidates.sort(key=lambda row: (row["score"], len(row["names"]), len(row["kdas"]), len(row["golds"])), reverse=True)
    return {
        "dump_path": str(Path(dump_path).resolve()),
        "max_gap": max_gap,
        "candidate_count": len(candidates),
        "candidates": candidates[:30],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Score result-screen VA clusters for row reconstruction.")
    parser.add_argument("--dump", required=True, help="Result-screen dump path")
    parser.add_argument("--expected", required=True, help="JSON file with expected player rows")
    parser.add_argument("--max-gap", type=int, default=2048, help="Maximum VA gap for clustering")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args()

    expected = json.loads(Path(args.expected).read_text(encoding="utf-8"))
    report = build_result_screen_cluster_candidates(args.dump, expected, max_gap=args.max_gap)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"Result-screen cluster candidates saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
