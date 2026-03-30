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
from vg.tools.result_screen_kda_correction_inventory import build_result_screen_kda_correction_inventory


def _load_kda_correction_map(kda_correction_path: Optional[str]) -> Dict[str, Dict[str, object]]:
    if not kda_correction_path:
        return {}

    path = Path(kda_correction_path)
    payloads: List[Dict[str, object]] = []
    if path.is_dir():
        inventory = build_result_screen_kda_correction_inventory(str(path))
        candidate_files = [Path(entry["path"]) for entry in inventory["preferred_entries"]]
        for candidate in candidate_files:
            try:
                payload = json.loads(candidate.read_text(encoding="utf-8"))
            except Exception:
                continue
            payloads.append(payload)
    else:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        payloads.append(payload)

    corrections: Dict[str, Dict[str, object]] = {}
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        players = payload.get("players")
        replay_name = payload.get("replay_name")
        replay_file = payload.get("replay_file")
        if not isinstance(players, list):
            continue
        if replay_name:
            corrections[f"name:{replay_name}"] = payload
        if replay_file:
            corrections[f"file:{Path(replay_file).resolve()}"] = payload
    return corrections


def _extract_corrected_kda(correction_row: Dict[str, object]) -> Optional[tuple[int, int, int, Optional[str]]]:
    corrected_kda = correction_row.get("corrected_kda")
    if corrected_kda:
        kills, deaths, assists = [int(part) for part in str(corrected_kda).split("/")]
        return kills, deaths, assists, correction_row.get("kda_correction_status")

    if all(key in correction_row for key in ("kills", "deaths", "assists")):
        return (
            int(correction_row["kills"]),
            int(correction_row["deaths"]),
            int(correction_row["assists"]),
            correction_row.get("kda_correction_status"),
        )
    return None


def build_index_ready_export(
    base_path: str,
    minion_policy: str = MINION_POLICY_NONE,
    *,
    kda_correction_path: Optional[str] = None,
) -> Dict[str, object]:
    """Build an export containing only currently accepted fields."""
    batch = decode_replay_batch(base_path)
    kda_corrections = _load_kda_correction_map(kda_correction_path)
    matches = []
    minion_policy_summary = {
        "policy": minion_policy,
        "accepted_matches": 0,
        "withheld_matches": 0,
    }
    kda_correction_summary = {
        "path": str(Path(kda_correction_path).resolve()) if kda_correction_path else None,
        "corrected_matches": 0,
        "corrected_rows": 0,
    }
    for match in batch["matches"]:
        accepted = match["accepted_fields"]
        correction_payload = (
            kda_corrections.get(f"file:{Path(match['replay_file']).resolve()}")
            or kda_corrections.get(f"name:{match['replay_name']}")
        )
        correction_by_name = {
            row["name"]: row for row in correction_payload.get("players", [])
        } if correction_payload else {}
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
        match_corrected_rows = 0
        for player in match["players"]:
            row = {
                "name": player["name"],
                "team": player["team"],
                "entity_id": player["entity_id"],
                "hero_name": player["hero_name"],
            }
            if accepted.get("kills", {}).get("accepted_for_index"):
                correction_row = correction_by_name.get(player["name"])
                corrected = _extract_corrected_kda(correction_row) if correction_row else None
                if corrected:
                    kills, deaths, assists, correction_status = corrected
                    row["kills"] = kills
                    row["deaths"] = deaths
                    row["assists"] = assists
                    row["kda_correction_status"] = correction_status
                    match_corrected_rows += 1
                else:
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
        if match_corrected_rows:
            match_row["kda_correction"] = {
                "applied": True,
                "corrected_rows": match_corrected_rows,
            }
            kda_correction_summary["corrected_matches"] += 1
            kda_correction_summary["corrected_rows"] += match_corrected_rows
        matches.append(match_row)

    return {
        "schema_version": "decoder_v2.index_export.v2",
        "base_path": str(Path(base_path).resolve()),
        "minion_policy": minion_policy,
        "minion_policy_summary": minion_policy_summary,
        "kda_correction_summary": kda_correction_summary,
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
    parser.add_argument(
        "--kda-correction-path",
        help="Optional result-screen KDA correction JSON file or directory",
    )
    parser.add_argument("-o", "--output", help="Optional output path")
    args = parser.parse_args(argv)

    report = build_index_ready_export(
        args.base_path,
        minion_policy=args.minion_policy,
        kda_correction_path=args.kda_correction_path,
    )
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
