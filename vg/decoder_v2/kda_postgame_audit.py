"""Audit KDA/team reliability and post-game tail behavior against truth fixtures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from vg.analysis.decode_tournament import _resolve_truth_player_name
from vg.core.kda_detector import KDADetector
from vg.core.unified_decoder import _le_to_be
from vg.core.vgr_parser import VGRParser

from .completeness import load_frames
from .validation import validate_player_block_claims

BufferConfig = Tuple[int, int]
DEFAULT_BUFFER_CONFIGS: Tuple[BufferConfig, ...] = (
    (0, 0),
    (3, 0),
    (3, 10),
    (5, 10),
)


def _load_truth_matches(truth_path: str) -> List[Dict[str, object]]:
    payload = json.loads(Path(truth_path).read_text(encoding="utf-8"))
    return payload.get("matches", [])


def _config_key(kill_buffer: int, death_buffer: int) -> str:
    return f"k{kill_buffer}_d{death_buffer}"


def _late_event_row(player_name: Optional[str], timestamp: float, duration: int, frame_idx: int) -> Dict[str, object]:
    delta = round(timestamp - duration, 3)
    return {
        "player_name": player_name,
        "timestamp": round(timestamp, 3),
        "delta_after_duration": delta,
        "frame_idx": frame_idx,
    }


def _summarize_config_rows(rows: Sequence[Dict[str, object]]) -> Dict[str, object]:
    kills_correct = sum(int(row["kills_correct"]) for row in rows)
    kills_total = sum(int(row["kills_total"]) for row in rows)
    deaths_correct = sum(int(row["deaths_correct"]) for row in rows)
    deaths_total = sum(int(row["deaths_total"]) for row in rows)
    assists_correct = sum(int(row["assists_correct"]) for row in rows)
    assists_total = sum(int(row["assists_total"]) for row in rows)

    combined_correct = kills_correct + deaths_correct + assists_correct
    combined_total = kills_total + deaths_total + assists_total

    def pct(correct: int, total: int) -> float:
        return round((correct / total) * 100, 4) if total else 0.0

    return {
        "kills": {
            "correct": kills_correct,
            "total": kills_total,
            "pct": pct(kills_correct, kills_total),
        },
        "deaths": {
            "correct": deaths_correct,
            "total": deaths_total,
            "pct": pct(deaths_correct, deaths_total),
        },
        "assists": {
            "correct": assists_correct,
            "total": assists_total,
            "pct": pct(assists_correct, assists_total),
        },
        "combined_kda": {
            "correct": combined_correct,
            "total": combined_total,
            "pct": pct(combined_correct, combined_total),
        },
    }


def _summarize_late_event_rows(match_rows: Sequence[Dict[str, object]]) -> Dict[str, int]:
    late_kills = [
        event
        for row in match_rows
        for event in row.get("late_kills", [])
    ]
    late_deaths = [
        event
        for row in match_rows
        for event in row.get("late_deaths", [])
    ]

    return {
        "kills_after_duration": len(late_kills),
        "kills_after_duration_plus_3": sum(int(event["delta_after_duration"] > 3.0) for event in late_kills),
        "kills_after_duration_plus_10": sum(int(event["delta_after_duration"] > 10.0) for event in late_kills),
        "deaths_after_duration": len(late_deaths),
        "deaths_after_duration_plus_3": sum(int(event["delta_after_duration"] > 3.0) for event in late_deaths),
        "deaths_after_duration_plus_10": sum(int(event["delta_after_duration"] > 10.0) for event in late_deaths),
    }


def _build_match_audit(match: Dict[str, object], buffer_configs: Sequence[BufferConfig]) -> Dict[str, object]:
    replay_file = str(match["replay_file"])
    duration = int(match["match_info"]["duration_seconds"])
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

    late_kills = [
        _late_event_row(
            player_map.get(event.killer_eid, {}).get("name"),
            event.timestamp,
            duration,
            event.frame_idx,
        )
        for event in detector.kill_events
        if event.timestamp is not None and event.timestamp > duration
    ]
    late_deaths = [
        _late_event_row(
            player_map.get(event.victim_eid, {}).get("name"),
            event.timestamp,
            duration,
            event.frame_idx,
        )
        for event in detector.death_events
        if event.timestamp > duration
    ]

    config_results: Dict[str, Dict[str, int]] = {}
    for kill_buffer, death_buffer in buffer_configs:
        results = detector.get_results(
            game_duration=duration,
            kill_buffer=kill_buffer,
            death_buffer=death_buffer,
            team_map=team_map,
        )

        kills_correct = kills_total = deaths_correct = deaths_total = assists_correct = assists_total = 0
        for entity_be, player in ordered_players:
            truth_name = _resolve_truth_player_name(player["name"], match["players"])
            if not truth_name:
                continue
            truth_player = match["players"][truth_name]

            if truth_player.get("kills") is not None:
                kills_total += 1
                kills_correct += int(results[entity_be].kills == truth_player["kills"])
            if truth_player.get("deaths") is not None:
                deaths_total += 1
                deaths_correct += int(results[entity_be].deaths == truth_player["deaths"])
            if truth_player.get("assists") is not None:
                assists_total += 1
                assists_correct += int(results[entity_be].assists == truth_player["assists"])

        config_results[_config_key(kill_buffer, death_buffer)] = {
            "kills_correct": kills_correct,
            "kills_total": kills_total,
            "deaths_correct": deaths_correct,
            "deaths_total": deaths_total,
            "assists_correct": assists_correct,
            "assists_total": assists_total,
        }

    fixture_directory = str(Path(replay_file).parent.name)
    return {
        "replay_name": match["replay_name"],
        "fixture_directory": fixture_directory,
        "replay_file": replay_file,
        "duration_truth": duration,
        "is_incomplete_fixture": "Incomplete" in fixture_directory,
        "matched_players": sum(int(values["kills_total"]) for values in config_results.values()) // len(config_results or [1]),
        "late_kills": late_kills,
        "late_deaths": late_deaths,
        "config_results": config_results,
    }


def build_kda_postgame_audit(
    truth_path: str,
    buffer_configs: Sequence[BufferConfig] = DEFAULT_BUFFER_CONFIGS,
) -> Dict[str, object]:
    matches = _load_truth_matches(truth_path)
    player_block_summary = validate_player_block_claims(truth_path).to_dict()
    match_rows = [_build_match_audit(match, buffer_configs) for match in matches]

    buffer_summary: Dict[str, Dict[str, object]] = {}
    for kill_buffer, death_buffer in buffer_configs:
        key = _config_key(kill_buffer, death_buffer)
        all_rows = [row["config_results"][key] for row in match_rows]
        complete_rows = [
            row["config_results"][key]
            for row in match_rows
            if not row["is_incomplete_fixture"]
        ]
        buffer_summary[key] = {
            "kill_buffer": kill_buffer,
            "death_buffer": death_buffer,
            "all_matches": _summarize_config_rows(all_rows),
            "complete_only": _summarize_config_rows(complete_rows),
        }

    return {
        "truth_path": str(Path(truth_path).resolve()),
        "team_grouping_validation": {
            "matches_total": player_block_summary["matches_total"],
            "records_total": player_block_summary["records_total"],
            "team_bytes_seen": player_block_summary["team_bytes_seen"],
            "entity_nonzero_records": player_block_summary["entity_nonzero_records"],
            "hero_matches": player_block_summary["hero_matches"],
            "hero_total": player_block_summary["hero_total"],
        },
        "late_event_summary": _summarize_late_event_rows(match_rows),
        "buffer_config_summary": buffer_summary,
        "match_rows": match_rows,
    }


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Audit decoder_v2 KDA/team reliability and post-game event tails.")
    parser.add_argument("--truth", default="vg/output/tournament_truth.json", help="Truth JSON path")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(list(argv) if argv is not None else None)

    report = build_kda_postgame_audit(args.truth)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload, encoding="utf-8")
        print(f"KDA post-game audit saved to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
