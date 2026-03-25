"""Export only index-safe fields from decoder_v2 outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

from .batch_decode import decode_replay_batch
from .minion_policy import (
    MINION_POLICY_CHOICES,
    MINION_POLICY_NONE,
    evaluate_minion_policy,
    evaluate_player_minion_policy,
)


def build_index_ready_export(base_path: str, minion_policy: str = MINION_POLICY_NONE) -> Dict[str, object]:
    """Build an export containing only currently accepted fields."""
    batch = decode_replay_batch(base_path)
    matches = []
    minion_policy_summary = {
        "policy": minion_policy,
        "accepted_matches": 0,
        "withheld_matches": 0,
    }
    for match in batch["matches"]:
        accepted = match["accepted_fields"]
        minion_allowed, minion_reason = evaluate_minion_policy(
            minion_policy,
            match["replay_file"],
            match["completeness_status"],
        )
        player_minion_decisions = evaluate_player_minion_policy(
            minion_policy,
            match["replay_file"],
            match["completeness_status"],
        )
        accepted_player_minions = sum(1 for decision in player_minion_decisions.values() if decision.accepted)
        if accepted_player_minions:
            minion_policy_summary["accepted_matches"] += 1
        else:
            minion_policy_summary["withheld_matches"] += 1

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
            player_decision = player_minion_decisions.get(player["name"])
            if player_decision:
                row["minion_policy"] = player_decision.to_dict()
                if player_decision.accepted:
                    row["minion_kills"] = player_decision.baseline_0e
            players.append(row)

        match_row = {
            "replay_name": match["replay_name"],
            "replay_file": match["replay_file"],
            "game_mode": match["game_mode"],
            "map_name": match["map_name"],
            "team_size": match["team_size"],
            "completeness_status": match["completeness_status"],
            "minion_policy": {
                "policy": minion_policy,
                "accepted_match": minion_allowed,
                "accepted_player_count": accepted_player_minions,
                "reason": minion_reason,
            },
            "players": players,
        }
        if accepted.get("winner", {}).get("accepted_for_index"):
            match_row["winner"] = accepted["winner"]["value"]
        matches.append(match_row)

    return {
        "schema_version": "decoder_v2.index_export.v2",
        "base_path": str(Path(base_path).resolve()),
        "minion_policy": minion_policy,
        "minion_policy_summary": minion_policy_summary,
        "total_replays": batch["total_replays"],
        "completeness_summary": batch["completeness_summary"],
        "matches": matches,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Export index-safe fields from decoder_v2.")
    parser.add_argument("base_path", help="Replay root directory")
    parser.add_argument(
        "--minion-policy",
        choices=MINION_POLICY_CHOICES,
        default=MINION_POLICY_NONE,
        help="Optional conservative minion export policy",
    )
    parser.add_argument("-o", "--output", help="Optional output path")
    args = parser.parse_args(argv)

    report = build_index_ready_export(args.base_path, minion_policy=args.minion_policy)
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
