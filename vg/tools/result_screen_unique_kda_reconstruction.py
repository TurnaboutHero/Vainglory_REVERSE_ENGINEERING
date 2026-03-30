"""Reconstruct player KDA rows from unique KDA values present in result-screen dump."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Dict, List

from .minidump_string_locator import locate_strings_in_minidump


def build_result_screen_unique_kda_reconstruction(dump_path: str, expected_players: List[Dict[str, object]]) -> Dict[str, object]:
    expected_kdas = [f"{player['kills']}/{player['deaths']}/{player['assists']}" for player in expected_players]
    counts = Counter(expected_kdas)
    unique_kdas = {value for value, count in counts.items() if count == 1}
    located = locate_strings_in_minidump(dump_path, list(unique_kdas))
    present = {row["value"] for row in located["strings"] if row["hit_count"] > 0}

    rows = []
    for player in expected_players:
        kda = f"{player['kills']}/{player['deaths']}/{player['assists']}"
        rows.append(
            {
                "name": player["name"],
                "team": player["team"],
                "hero_name": player.get("hero_name"),
                "kda": kda,
                "kda_is_unique": kda in unique_kdas,
                "kda_present_in_dump": kda in present,
                "auto_reconstructable": kda in unique_kdas and kda in present,
            }
        )

    auto_count = sum(int(row["auto_reconstructable"]) for row in rows)
    return {
        "dump_path": str(Path(dump_path).resolve()),
        "player_rows": rows,
        "auto_reconstructable_rows": auto_count,
        "total_rows": len(rows),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconstruct player rows from unique KDA values in result-screen dump.")
    parser.add_argument("--dump", required=True, help="Result-screen dump path")
    parser.add_argument("--expected", required=True, help="JSON file with expected player rows")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args()

    expected = json.loads(Path(args.expected).read_text(encoding="utf-8"))
    report = build_result_screen_unique_kda_reconstruction(args.dump, expected)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"Result-screen unique KDA reconstruction saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
