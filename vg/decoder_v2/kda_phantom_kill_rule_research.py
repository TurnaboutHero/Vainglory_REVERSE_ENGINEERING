"""Evaluate narrow late phantom-kill filters against truth fixtures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from vg.analysis.decode_tournament import _resolve_truth_player_name
from vg.core.kda_detector import KDADetector, KillEvent
from vg.core.unified_decoder import _le_to_be
from vg.core.vgr_parser import VGRParser

from .completeness import load_frames
from .kda_postgame_audit import _load_truth_matches


def _should_drop_phantom_kill(
    event: KillEvent,
    *,
    duration: int,
    threshold: int,
    victim_eid: Optional[int],
) -> bool:
    if event.timestamp is None:
        return False
    if victim_eid is not None:
        return False
    return event.timestamp > (duration + threshold)


def build_kda_phantom_kill_rule_research(
    truth_path: str,
    *,
    kill_buffer: int = 20,
    death_buffer: int = 3,
    late_none_thresholds: Sequence[int] = (8, 10, 12, 15),
    complete_only: bool = True,
) -> Dict[str, object]:
    thresholds = list(late_none_thresholds)
    matches = _load_truth_matches(truth_path)

    rows = []
    for threshold in thresholds:
        kill_correct = kill_total = 0
        combined_correct = combined_total = 0
        dropped_events = []

        for match in matches:
            replay_file = str(match["replay_file"])
            fixture_directory = str(Path(replay_file).parent.name)
            if complete_only and "Incomplete" in fixture_directory:
                continue

            duration = int(match["match_info"]["duration_seconds"])
            parsed = VGRParser(replay_file, auto_truth=False).parse()
            player_map: Dict[int, Dict[str, object]] = {}
            team_map: Dict[int, str] = {}
            ordered_players = []
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

            base_results = detector.get_results(
                game_duration=duration,
                kill_buffer=kill_buffer,
                death_buffer=death_buffer,
                team_map=team_map,
            )
            pairs = detector.get_kill_death_pairs(
                team_map,
                game_duration=duration,
                death_buffer=death_buffer,
            )

            pair_map = {
                (row["killer_eid"], row["kill_ts"]): row.get("victim_eid")
                for row in pairs
                if row.get("kill_ts") is not None
            }
            adjusted_kills = {eid: 0 for eid in player_map}
            max_kill_ts = duration + kill_buffer
            for event in detector.kill_events:
                if event.timestamp is not None and event.timestamp > max_kill_ts:
                    continue
                victim_eid = pair_map.get((event.killer_eid, event.timestamp))
                if _should_drop_phantom_kill(event, duration=duration, threshold=threshold, victim_eid=victim_eid):
                    dropped_events.append(
                        {
                            "threshold": threshold,
                            "replay_name": match["replay_name"],
                            "fixture_directory": fixture_directory,
                            "killer_name": player_map.get(event.killer_eid, {}).get("name"),
                            "timestamp": round(event.timestamp or 0.0, 3),
                            "delta_after_duration": round((event.timestamp or 0.0) - duration, 3),
                        }
                    )
                    continue
                adjusted_kills[event.killer_eid] += 1

            for entity_be, player in ordered_players:
                truth_name = _resolve_truth_player_name(player["name"], match["players"])
                if not truth_name:
                    continue
                truth_player = match["players"][truth_name]

                if truth_player.get("kills") is not None:
                    kill_total += 1
                    kill_correct += int(adjusted_kills[entity_be] == truth_player["kills"])
                    combined_total += 1
                    combined_correct += int(adjusted_kills[entity_be] == truth_player["kills"])
                if truth_player.get("deaths") is not None:
                    combined_total += 1
                    combined_correct += int(base_results[entity_be].deaths == truth_player["deaths"])
                if truth_player.get("assists") is not None:
                    combined_total += 1
                    combined_correct += int(base_results[entity_be].assists == truth_player["assists"])

        rows.append(
            {
                "late_none_threshold": threshold,
                "kill_correct": kill_correct,
                "kill_total": kill_total,
                "kill_pct": round((kill_correct / kill_total) * 100, 4) if kill_total else 0.0,
                "combined_correct": combined_correct,
                "combined_total": combined_total,
                "combined_pct": round((combined_correct / combined_total) * 100, 4) if combined_total else 0.0,
                "dropped_event_count": len(dropped_events),
                "dropped_events": dropped_events,
            }
        )

    return {
        "truth_path": str(Path(truth_path).resolve()),
        "config": {
            "kill_buffer": kill_buffer,
            "death_buffer": death_buffer,
            "complete_only": complete_only,
        },
        "rows": rows,
    }


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate narrow late phantom-kill filters.")
    parser.add_argument("--truth", default="vg/output/tournament_truth.json", help="Truth JSON path")
    parser.add_argument("--kill-buffer", type=int, default=20, help="Kill buffer seconds")
    parser.add_argument("--death-buffer", type=int, default=3, help="Death buffer seconds")
    parser.add_argument(
        "--late-none-threshold",
        action="append",
        type=int,
        required=True,
        help="Drop victim-none kills after duration + threshold seconds",
    )
    parser.add_argument("--all-fixtures", action="store_true", help="Include incomplete fixtures")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(list(argv) if argv is not None else None)

    report = build_kda_phantom_kill_rule_research(
        args.truth,
        kill_buffer=args.kill_buffer,
        death_buffer=args.death_buffer,
        late_none_thresholds=list(args.late_none_threshold),
        complete_only=not args.all_fixtures,
    )
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"KDA phantom kill rule research saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
