"""Apply result-screen KDA correction statuses to expected player rows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

from .result_screen_kda_correction_report import (
    _load_expected_players,
    build_result_screen_kda_correction_report,
)


def build_result_screen_kda_correction_apply(
    dump_path: str, expected_players: List[Dict[str, object]]
) -> Dict[str, object]:
    report = build_result_screen_kda_correction_report(dump_path, expected_players)
    group_by_kda = {row["kda"]: row for row in report["groups"]}

    applied_rows = []
    applicable_rows = 0
    for player in expected_players:
        kda = f"{player['kills']}/{player['deaths']}/{player['assists']}"
        group = group_by_kda[kda]
        if group["name_bound_count"] > 0 and player["name"] in group["name_bound_rows"]:
            correction_status = "name_bound_unique"
            corrected_kda = kda
        elif group["group_confirmable"] and group["expected_count"] > 1:
            correction_status = "group_confirmed_duplicate"
            corrected_kda = kda
        elif group["group_confirmable"]:
            correction_status = "group_confirmed"
            corrected_kda = kda
        else:
            correction_status = "unresolved"
            corrected_kda = None

        if corrected_kda is not None:
            applicable_rows += 1

        applied_rows.append(
            {
                "name": player["name"],
                "team": player["team"],
                "hero_name": player.get("hero_name"),
                "parser_kda": kda,
                "corrected_kda": corrected_kda,
                "correction_status": correction_status,
            }
        )

    return {
        "dump_path": str(Path(dump_path).resolve()),
        "applicable_rows": applicable_rows,
        "total_rows": len(expected_players),
        "player_rows": applied_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply result-screen KDA correction statuses to player rows.")
    parser.add_argument("--dump", required=True, help="Result-screen dump path")
    parser.add_argument("--expected", required=True, help="Player rows JSON or decoder debug JSON")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args()

    expected_players = _load_expected_players(args.expected)
    report = build_result_screen_kda_correction_apply(args.dump, expected_players)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"Result-screen KDA correction apply report saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
