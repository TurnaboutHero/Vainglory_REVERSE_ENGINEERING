"""Choose best result-screen name anchors by nearby expected KDA and gold hits."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

from .minidump_string_locator import locate_strings_in_minidump


def _nearest_distance(vas: List[int], anchor_va: int, max_distance: int) -> Optional[int]:
    if not vas:
        return None
    distances = [abs(va - anchor_va) for va in vas if abs(va - anchor_va) <= max_distance]
    if not distances:
        return None
    return min(distances)


def build_result_screen_row_anchor_report(
    dump_path: str,
    expected_players: List[Dict[str, object]],
    *,
    max_distance: int = 4096,
) -> Dict[str, object]:
    values: List[str] = []
    for player in expected_players:
        values.append(str(player["name"]))
        values.append(f"{player['kills']}/{player['deaths']}/{player['assists']}")
        if player.get("gold"):
            values.append(str(player["gold"]))

    located = locate_strings_in_minidump(dump_path, values)
    hits_by_value = {
        row["value"]: [int(hit["virtual_address"]) for hit in row["hits"] if hit["virtual_address"] is not None]
        for row in located["strings"]
    }

    rows = []
    for player in expected_players:
        name = str(player["name"])
        kda = f"{player['kills']}/{player['deaths']}/{player['assists']}"
        gold = str(player["gold"]) if player.get("gold") else None
        best = None
        for anchor_va in hits_by_value.get(name, []):
            kda_distance = _nearest_distance(hits_by_value.get(kda, []), anchor_va, max_distance)
            gold_distance = _nearest_distance(hits_by_value.get(gold, []), anchor_va, max_distance) if gold else None
            score = 0
            if kda_distance is not None:
                score += 1000 - kda_distance
            if gold_distance is not None:
                score += 1000 - gold_distance
            if best is None or score > best["score"]:
                best = {
                    "anchor_va": anchor_va,
                    "score": score,
                    "kda_distance": kda_distance,
                    "gold_distance": gold_distance,
                }
        rows.append(
            {
                "name": name,
                "team": player["team"],
                "hero_name": player.get("hero_name"),
                "expected_kda": kda,
                "expected_gold": gold,
                "anchor": best,
            }
        )
    return {
        "dump_path": str(Path(dump_path).resolve()),
        "max_distance": max_distance,
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Choose best result-screen name anchors by nearby KDA/gold.")
    parser.add_argument("--dump", required=True, help="Result-screen dump path")
    parser.add_argument("--expected", required=True, help="JSON file with expected player rows")
    parser.add_argument("--max-distance", type=int, default=4096, help="Maximum VA distance to consider nearby")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args()

    expected = json.loads(Path(args.expected).read_text(encoding="utf-8"))
    report = build_result_screen_row_anchor_report(args.dump, expected, max_distance=args.max_distance)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"Result-screen row anchor report saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
