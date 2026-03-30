"""Player-level KDA mismatch triage for truth-covered fixtures."""

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
from .kda_postgame_audit import _config_key, _load_truth_matches

BufferConfig = Tuple[int, int]


def build_kda_mismatch_triage(
    truth_path: str,
    *,
    kill_buffer: int = 3,
    death_buffer: int = 10,
    complete_only: bool = True,
) -> Dict[str, object]:
    matches = _load_truth_matches(truth_path)
    rows: List[Dict[str, object]] = []

    for match in matches:
        fixture_directory = str(Path(match["replay_file"]).parent.name)
        is_incomplete_fixture = "Incomplete" in fixture_directory
        if complete_only and is_incomplete_fixture:
            continue

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

        results = detector.get_results(
            game_duration=duration,
            kill_buffer=kill_buffer,
            death_buffer=death_buffer,
            team_map=team_map,
        )

        for entity_be, player in ordered_players:
            truth_name = _resolve_truth_player_name(player["name"], match["players"])
            if not truth_name:
                continue
            truth_player = match["players"][truth_name]

            predicted = results[entity_be]
            diffs = {
                "kills": predicted.kills - truth_player["kills"],
                "deaths": predicted.deaths - truth_player["deaths"],
                "assists": predicted.assists - truth_player["assists"],
            }
            if all(value == 0 for value in diffs.values()):
                continue

            rows.append(
                {
                    "replay_name": match["replay_name"],
                    "fixture_directory": fixture_directory,
                    "replay_file": replay_file,
                    "player_name": player["name"],
                    "team": team_map[entity_be],
                    "hero_name": player.get("hero_name"),
                    "entity_id_be": entity_be,
                    "kill_buffer": kill_buffer,
                    "death_buffer": death_buffer,
                    "truth": {
                        "kills": truth_player["kills"],
                        "deaths": truth_player["deaths"],
                        "assists": truth_player["assists"],
                    },
                    "predicted": {
                        "kills": predicted.kills,
                        "deaths": predicted.deaths,
                        "assists": predicted.assists,
                    },
                    "diff": diffs,
                }
            )

    by_metric = {
        "kills": sum(int(row["diff"]["kills"] != 0) for row in rows),
        "deaths": sum(int(row["diff"]["deaths"] != 0) for row in rows),
        "assists": sum(int(row["diff"]["assists"] != 0) for row in rows),
    }

    return {
        "truth_path": str(Path(truth_path).resolve()),
        "config": {
            "kill_buffer": kill_buffer,
            "death_buffer": death_buffer,
            "complete_only": complete_only,
        },
        "mismatch_count": len(rows),
        "by_metric": by_metric,
        "rows": rows,
    }


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Player-level KDA mismatch triage for truth-covered fixtures.")
    parser.add_argument("--truth", default="vg/output/tournament_truth.json", help="Truth JSON path")
    parser.add_argument("--kill-buffer", type=int, default=3, help="Kill buffer seconds")
    parser.add_argument("--death-buffer", type=int, default=10, help="Death buffer seconds")
    parser.add_argument("--all-fixtures", action="store_true", help="Include incomplete fixtures")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(list(argv) if argv is not None else None)

    report = build_kda_mismatch_triage(
        args.truth,
        kill_buffer=args.kill_buffer,
        death_buffer=args.death_buffer,
        complete_only=not args.all_fixtures,
    )
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"KDA mismatch triage saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
