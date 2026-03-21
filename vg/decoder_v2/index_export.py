"""Export only index-safe fields from decoder_v2 outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

from .batch_decode import decode_replay_batch


def build_index_ready_export(base_path: str) -> Dict[str, object]:
    """Build an export containing only currently accepted fields."""
    batch = decode_replay_batch(base_path)
    matches = []
    for match in batch["matches"]:
        accepted = match["accepted_fields"]
        players = []
        for player in match["players"]:
            row = {
                "name": player["name"],
                "team": player["team"],
                "entity_id": player["entity_id"],
                "hero_name": player["hero_name"],
            }
            if accepted.get("kills", {}).get("accepted_for_index"):
                row["kills"] = player["kills"]
                row["deaths"] = player["deaths"]
                row["assists"] = player["assists"]
            players.append(row)

        match_row = {
            "replay_name": match["replay_name"],
            "replay_file": match["replay_file"],
            "game_mode": match["game_mode"],
            "map_name": match["map_name"],
            "team_size": match["team_size"],
            "completeness_status": match["completeness_status"],
            "players": players,
        }
        if accepted.get("winner", {}).get("accepted_for_index"):
            match_row["winner"] = accepted["winner"]["value"]
        matches.append(match_row)

    return {
        "schema_version": "decoder_v2.index_export.v1",
        "base_path": str(Path(base_path).resolve()),
        "total_replays": batch["total_replays"],
        "completeness_summary": batch["completeness_summary"],
        "matches": matches,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Export index-safe fields from decoder_v2.")
    parser.add_argument("base_path", help="Replay root directory")
    parser.add_argument("-o", "--output", help="Optional output path")
    args = parser.parse_args(argv)

    report = build_index_ready_export(args.base_path)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Index-safe export saved to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
