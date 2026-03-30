"""Inspect raw assist-credit windows for player-level assist mismatches."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from vg.analysis.decode_tournament import _resolve_truth_player_name
from vg.core.kda_detector import KDADetector
from vg.core.unified_decoder import _le_to_be
from vg.core.vgr_parser import VGRParser

from .completeness import load_frames
from .kda_mismatch_triage import build_kda_mismatch_triage
from .kda_postgame_audit import _load_truth_matches


def build_kda_assist_credit_triage(
    truth_path: str,
    *,
    kill_buffer: int = 3,
    death_buffer: int = 10,
    complete_only: bool = True,
) -> Dict[str, object]:
    mismatch_report = build_kda_mismatch_triage(
        truth_path,
        kill_buffer=kill_buffer,
        death_buffer=death_buffer,
        complete_only=complete_only,
    )
    truth_by_replay = {
        str(match["replay_file"]): match
        for match in _load_truth_matches(truth_path)
    }
    assist_rows = [row for row in mismatch_report["rows"] if row["diff"]["assists"] != 0]

    replay_cache: Dict[str, Dict[str, object]] = {}
    triage_rows = []

    for mismatch in assist_rows:
        replay_file = mismatch["replay_file"]
        if replay_file not in replay_cache:
            parsed = VGRParser(replay_file, auto_truth=False).parse()
            player_map: Dict[int, Dict[str, object]] = {}
            team_map: Dict[int, str] = {}
            ordered_players: List[Tuple[int, Dict[str, object]]] = []
            for team_label in ("left", "right"):
                for player in parsed["teams"][team_label]:
                    entity_id = player.get("entity_id")
                    if not entity_id:
                        continue
                    entity_be = _le_to_be(entity_id)
                    player_map[entity_be] = player
                    team_map[entity_be] = team_label
                    ordered_players.append((entity_be, player))

            detector = KDADetector(set(player_map))
            for frame_idx, data in load_frames(replay_file):
                detector.process_frame(frame_idx, data)

            replay_cache[replay_file] = {
                "player_map": player_map,
                "team_map": team_map,
                "detector": detector,
            }

        cached = replay_cache[replay_file]
        player_map = cached["player_map"]
        team_map = cached["team_map"]
        detector = cached["detector"]

        player_name = mismatch["player_name"]
        player_eid = mismatch["entity_id_be"]
        player_team = team_map[player_eid]
        # Prefer fixture truth duration for post-game filtering; parser duration may be absent on some tournament files.
        truth_match = truth_by_replay[replay_file]
        duration = int(truth_match["match_info"]["duration_seconds"])
        max_ts = duration + kill_buffer

        kill_windows = []
        for kill_event in detector.kill_events:
            if kill_event.timestamp is not None and kill_event.timestamp > max_ts:
                continue
            killer_name = player_map.get(kill_event.killer_eid, {}).get("name")
            killer_team = team_map.get(kill_event.killer_eid)
            credits_by_eid: Dict[int, List[float]] = defaultdict(list)
            for credit in kill_event.credits:
                credits_by_eid[credit.eid].append(credit.value)

            if player_eid not in credits_by_eid:
                continue

            values = credits_by_eid[player_eid]
            has_flag = any(abs(value - 1.0) < 0.01 for value in values)
            counted_current = (
                player_eid != kill_event.killer_eid
                and killer_team == player_team
                and has_flag
                and len(values) >= 2
            )
            kill_windows.append(
                {
                    "killer_name": killer_name,
                    "killer_team": killer_team,
                    "timestamp": kill_event.timestamp,
                    "frame_idx": kill_event.frame_idx,
                    "file_offset": kill_event.file_offset,
                    "player_credit_values": values,
                    "credit_count": len(values),
                    "has_flag_1_0": has_flag,
                    "same_team_as_killer": killer_team == player_team,
                    "counted_current_rule": counted_current,
                }
            )

        triage_rows.append(
            {
                **mismatch,
                "kill_windows": kill_windows,
            }
        )

    return {
        "truth_path": str(Path(truth_path).resolve()),
        "config": {
            "kill_buffer": kill_buffer,
            "death_buffer": death_buffer,
            "complete_only": complete_only,
        },
        "rows": triage_rows,
    }


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect raw assist-credit windows for player assist mismatches.")
    parser.add_argument("--truth", default="vg/output/tournament_truth.json", help="Truth JSON path")
    parser.add_argument("--kill-buffer", type=int, default=3, help="Kill buffer seconds")
    parser.add_argument("--death-buffer", type=int, default=10, help="Death buffer seconds")
    parser.add_argument("--all-fixtures", action="store_true", help="Include incomplete fixtures")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(list(argv) if argv is not None else None)

    report = build_kda_assist_credit_triage(
        args.truth,
        kill_buffer=args.kill_buffer,
        death_buffer=args.death_buffer,
        complete_only=not args.all_fixtures,
    )
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"KDA assist credit triage saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
