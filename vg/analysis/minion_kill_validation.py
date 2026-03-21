"""
Validate current minion kill detection accuracy and identify misses.
"""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path
from typing import Dict, Iterable, List

from vg.core.kda_detector import KDADetector
from vg.core.vgr_parser import VGRParser


def _le_to_be(entity_id: int) -> int:
    return struct.unpack(">H", struct.pack("<H", entity_id))[0]


def _iter_players(parsed: Dict) -> Iterable[Dict]:
    for team_label in ("left", "right"):
        for player in parsed.get("teams", {}).get(team_label, []):
            yield player


def _load_frames(replay_file: str) -> List[bytes]:
    replay_path = Path(replay_file)
    frame_dir = replay_path.parent
    replay_name = replay_path.stem.rsplit(".", 1)[0]
    frames = sorted(
        frame_dir.glob(f"{replay_name}.*.vgr"),
        key=lambda p: int(p.stem.split(".")[-1]),
    )
    return [frame.read_bytes() for frame in frames]


def validate_minion_kills(truth_path: Path, max_matches: int = 9) -> int:
    truth = json.loads(truth_path.read_text(encoding="utf-8"))

    print("Validating current minion kill detection (action byte 0x0E)")
    print("=" * 70)

    total_perfect = 0
    total_players = 0
    all_errors = []

    for match_idx, match in enumerate(truth["matches"][:max_matches]):
        if match_idx == 8:
            continue

        print(f"\nMatch {match_idx + 1}: {match['replay_name'][:40]}...")

        parser = VGRParser(match["replay_file"], auto_truth=False)
        parsed = parser.parse()

        entity_ids = {}
        for player in _iter_players(parsed):
            entity_id = player.get("entity_id")
            if entity_id:
                entity_ids[player["name"]] = _le_to_be(entity_id)

        detector = KDADetector(set(entity_ids.values()))
        for i, frame in enumerate(_load_frames(parsed["replay_file"])):
            detector.process_frame(i, frame)

        results = detector.get_results()

        match_errors = []
        for player_name, data in match["players"].items():
            truth_mk = data.get("minion_kills")
            if truth_mk is None:
                continue

            entity_id = entity_ids.get(player_name)
            if entity_id is None:
                continue

            detected_mk = results[entity_id].minion_kills
            total_players += 1
            diff = detected_mk - truth_mk

            if diff == 0:
                total_perfect += 1
                continue

            error = {
                "player": player_name,
                "hero": data["hero_name"],
                "truth": truth_mk,
                "detected": detected_mk,
                "diff": diff,
                "match": match_idx + 1,
            }
            match_errors.append(error)
            all_errors.append(error)

        if match_errors:
            print("  Errors in this match:")
            for err in match_errors:
                print(
                    f"    {err['player']:20s} ({err['hero']:12s}) "
                    f"Truth:{err['truth']:3d} Detected:{err['detected']:3d} Diff:{err['diff']:+3d}"
                )
        else:
            print("  All players perfect")

    print("\n" + "=" * 70)
    accuracy = 100 * total_perfect / total_players if total_players else 0.0
    print(f"Overall Accuracy: {total_perfect}/{total_players} ({accuracy:.1f}%)")
    print(f"Errors: {len(all_errors)}")

    if all_errors:
        print("\nAll errors summary:")
        for err in all_errors:
            print(
                f"  Match {err['match']}: {err['player']:20s} "
                f"({err['hero']:12s}) Diff:{err['diff']:+3d} (Truth:{err['truth']:3d})"
            )

    return 0


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate minion kill detection against truth data.")
    parser.add_argument(
        "--truth",
        default="vg/output/tournament_truth.json",
        help="Path to tournament truth JSON",
    )
    parser.add_argument(
        "--max-matches",
        type=int,
        default=9,
        help="Maximum number of matches to validate",
    )
    args = parser.parse_args(argv)
    return validate_minion_kills(Path(args.truth), max_matches=args.max_matches)


if __name__ == "__main__":
    raise SystemExit(main())
