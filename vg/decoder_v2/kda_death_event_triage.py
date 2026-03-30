"""Inspect raw death-event timelines for player-level death mismatches."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from vg.core.kda_detector import KDADetector
from vg.core.unified_decoder import _le_to_be
from vg.core.vgr_parser import VGRParser

from .completeness import load_frames
from .kda_mismatch_triage import build_kda_mismatch_triage
from .kda_postgame_audit import _load_truth_matches


def build_kda_death_event_triage(
    truth_path: str,
    *,
    kill_buffer: int = 20,
    death_buffer: int = 8,
    complete_only: bool = True,
) -> Dict[str, object]:
    mismatch_report = build_kda_mismatch_triage(
        truth_path,
        kill_buffer=kill_buffer,
        death_buffer=death_buffer,
        complete_only=complete_only,
    )
    truth_by_replay = {str(match["replay_file"]): match for match in _load_truth_matches(truth_path)}
    death_rows = [row for row in mismatch_report["rows"] if row["diff"]["deaths"] != 0]

    replay_cache: Dict[str, Dict[str, object]] = {}
    triage_rows = []

    for mismatch in death_rows:
        replay_file = mismatch["replay_file"]
        if replay_file not in replay_cache:
            parsed = VGRParser(replay_file, auto_truth=False).parse()
            player_map: Dict[int, Dict[str, object]] = {}
            team_map: Dict[int, str] = {}
            for team_label in ("left", "right"):
                for player in parsed["teams"][team_label]:
                    entity_id = player.get("entity_id")
                    if not entity_id:
                        continue
                    entity_be = _le_to_be(entity_id)
                    player_map[entity_be] = player
                    team_map[entity_be] = team_label

            detector = KDADetector(set(player_map))
            for frame_idx, data in load_frames(replay_file):
                detector.process_frame(frame_idx, data)

            replay_cache[replay_file] = {
                "player_map": player_map,
                "detector": detector,
            }

        cached = replay_cache[replay_file]
        player_map = cached["player_map"]
        detector = cached["detector"]
        truth_match = truth_by_replay[replay_file]
        duration = int(truth_match["match_info"]["duration_seconds"])
        player_eid = mismatch["entity_id_be"]

        events = [
            {
                "timestamp": event.timestamp,
                "frame_idx": event.frame_idx,
                "file_offset": event.file_offset,
                "delta_after_duration": round(event.timestamp - duration, 3),
                "within_buffer": event.timestamp <= duration + death_buffer,
            }
            for event in detector.death_events
            if event.victim_eid == player_eid
        ]

        triage_rows.append(
            {
                **mismatch,
                "duration_truth": duration,
                "death_events": events,
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
    parser = argparse.ArgumentParser(description="Inspect raw death-event timelines for player death mismatches.")
    parser.add_argument("--truth", default="vg/output/tournament_truth.json", help="Truth JSON path")
    parser.add_argument("--kill-buffer", type=int, default=20, help="Kill buffer seconds")
    parser.add_argument("--death-buffer", type=int, default=8, help="Death buffer seconds")
    parser.add_argument("--all-fixtures", action="store_true", help="Include incomplete fixtures")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(list(argv) if argv is not None else None)

    report = build_kda_death_event_triage(
        args.truth,
        kill_buffer=args.kill_buffer,
        death_buffer=args.death_buffer,
        complete_only=not args.all_fixtures,
    )
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"KDA death event triage saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
