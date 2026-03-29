"""Sweep row-anchor distance thresholds on a result-screen dump."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .result_screen_row_anchor_report import build_result_screen_row_anchor_report


def build_result_screen_row_anchor_sweep(
    dump_path: str,
    expected_players: List[Dict[str, object]],
    *,
    distances: List[int],
) -> Dict[str, object]:
    rows = []
    for distance in distances:
        report = build_result_screen_row_anchor_report(dump_path, expected_players, max_distance=distance)
        kda_hits = sum(1 for row in report["rows"] if row["anchor"] and row["anchor"]["kda_distance"] is not None)
        gold_hits = sum(1 for row in report["rows"] if row["anchor"] and row["anchor"]["gold_distance"] is not None)
        both_hits = sum(
            1
            for row in report["rows"]
            if row["anchor"]
            and row["anchor"]["kda_distance"] is not None
            and row["anchor"]["gold_distance"] is not None
        )
        rows.append(
            {
                "distance": distance,
                "kda_hits": kda_hits,
                "gold_hits": gold_hits,
                "both_hits": both_hits,
            }
        )
    return {
        "dump_path": str(Path(dump_path).resolve()),
        "distances": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Sweep row-anchor distance thresholds on a result-screen dump.")
    parser.add_argument("--dump", required=True, help="Result-screen dump path")
    parser.add_argument("--expected", required=True, help="JSON file with expected player rows")
    parser.add_argument("--distance", action="append", type=int, required=True, help="Distance threshold (repeatable)")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args()

    expected = json.loads(Path(args.expected).read_text(encoding="utf-8"))
    report = build_result_screen_row_anchor_sweep(
        args.dump,
        expected,
        distances=list(args.distance),
    )
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"Result-screen row anchor sweep saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
