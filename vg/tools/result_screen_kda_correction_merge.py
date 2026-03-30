"""Merge result-screen KDA correction output into decoder player rows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple


def _parse_kda(kda: str) -> Tuple[int, int, int]:
    kills, deaths, assists = kda.split("/")
    return int(kills), int(deaths), int(assists)


def _load_players(payload: Dict[str, object]) -> List[Dict[str, object]]:
    safe_output = payload.get("safe_output")
    if isinstance(safe_output, dict) and isinstance(safe_output.get("players"), list):
        return safe_output["players"]
    if isinstance(payload.get("players"), list):
        return payload["players"]
    raise ValueError("payload must contain players or safe_output.players")


def build_result_screen_kda_correction_merge(
    decoded_payload: Dict[str, object],
    correction_payload: Dict[str, object],
) -> Dict[str, object]:
    players = [dict(player) for player in _load_players(decoded_payload)]
    safe_output = decoded_payload.get("safe_output") if isinstance(decoded_payload, dict) else None
    replay_name = None
    replay_file = None
    if isinstance(safe_output, dict):
        replay_name = safe_output.get("replay_name")
        replay_file = safe_output.get("replay_file")
    elif isinstance(decoded_payload, dict):
        replay_name = decoded_payload.get("replay_name")
        replay_file = decoded_payload.get("replay_file")
    correction_by_name = {row["name"]: row for row in correction_payload["player_rows"]}

    corrected_rows = 0
    unresolved_rows = 0
    merged_players = []
    for player in players:
        row = correction_by_name.get(player["name"])
        merged = dict(player)
        if row and row.get("corrected_kda"):
            kills, deaths, assists = _parse_kda(row["corrected_kda"])
            merged["kills"] = kills
            merged["deaths"] = deaths
            merged["assists"] = assists
            merged["kda_correction_status"] = row["correction_status"]
            corrected_rows += 1
        else:
            merged["kda_correction_status"] = "unresolved"
            unresolved_rows += 1
        merged_players.append(merged)

    return {
        "replay_name": replay_name,
        "replay_file": replay_file,
        "corrected_rows": corrected_rows,
        "unresolved_rows": unresolved_rows,
        "total_rows": len(merged_players),
        "players": merged_players,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge result-screen KDA correction into decoder player rows.")
    parser.add_argument("--decoded", required=True, help="Decoder debug JSON or player rows JSON")
    parser.add_argument("--correction", required=True, help="Result-screen correction apply JSON")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args()

    decoded_payload = json.loads(Path(args.decoded).read_text(encoding="utf-8"))
    correction_payload = json.loads(Path(args.correction).read_text(encoding="utf-8"))
    report = build_result_screen_kda_correction_merge(decoded_payload, correction_payload)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"Result-screen KDA correction merge saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
