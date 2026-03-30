"""Summarize result-screen KDA correction coverage from a final-state minidump."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Dict, List

from .minidump_string_locator import locate_strings_in_minidump
from .result_screen_unique_kda_reconstruction import build_result_screen_unique_kda_reconstruction


def _load_expected_players(expected_path: str) -> List[Dict[str, object]]:
    payload = json.loads(Path(expected_path).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        safe_output = payload.get("safe_output")
        if isinstance(safe_output, dict) and isinstance(safe_output.get("players"), list):
            return safe_output["players"]
        if isinstance(payload.get("players"), list):
            return payload["players"]
    raise ValueError("expected payload must be a player list or contain safe_output.players")


def build_result_screen_kda_correction_report(
    dump_path: str, expected_players: List[Dict[str, object]]
) -> Dict[str, object]:
    unique_report = build_result_screen_unique_kda_reconstruction(dump_path, expected_players)

    expected_kdas = [f"{p['kills']}/{p['deaths']}/{p['assists']}" for p in expected_players]
    expected_counts = Counter(expected_kdas)
    located = locate_strings_in_minidump(dump_path, list(expected_counts))
    hit_counts = {row["value"]: row["hit_count"] for row in located["strings"]}

    unique_lookup = {row["name"]: row for row in unique_report["player_rows"]}
    groups = []
    group_confirmable_rows = 0
    duplicate_group_rows = 0
    unresolved_name_bound_rows = []

    for kda, expected_count in sorted(expected_counts.items(), key=lambda item: (item[1], item[0])):
        names = [p["name"] for p in expected_players if f"{p['kills']}/{p['deaths']}/{p['assists']}" == kda]
        present = hit_counts.get(kda, 0) > 0
        name_bound_rows = [name for name in names if unique_lookup[name]["auto_reconstructable"]]
        if present:
            group_confirmable_rows += len(names)
        if len(names) > 1:
            duplicate_group_rows += len(names)
            if present:
                unresolved_name_bound_rows.extend(
                    name for name in names if not unique_lookup[name]["auto_reconstructable"]
                )
        groups.append(
            {
                "kda": kda,
                "expected_count": expected_count,
                "dump_hit_count": hit_counts.get(kda, 0),
                "names": names,
                "group_confirmable": present,
                "name_bound_rows": name_bound_rows,
                "name_bound_count": len(name_bound_rows),
            }
        )

    return {
        "dump_path": str(Path(dump_path).resolve()),
        "total_rows": len(expected_players),
        "name_bound_reconstructable_rows": unique_report["auto_reconstructable_rows"],
        "group_confirmable_rows": group_confirmable_rows,
        "duplicate_group_rows": duplicate_group_rows,
        "unresolved_name_bound_rows": unresolved_name_bound_rows,
        "groups": groups,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize result-screen KDA correction coverage from a minidump.")
    parser.add_argument("--dump", required=True, help="Result-screen dump path")
    parser.add_argument("--expected", required=True, help="Player rows JSON or decoder debug JSON")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args()

    expected_players = _load_expected_players(args.expected)
    report = build_result_screen_kda_correction_report(args.dump, expected_players)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"Result-screen KDA correction report saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
