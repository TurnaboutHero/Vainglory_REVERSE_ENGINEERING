"""Generate truth stubs for replay directories not yet covered by truth."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

from .decode_match import decode_match
from .manifest import parse_replay_manifest
from .truth_inventory import build_truth_inventory


def find_replay_files(directory: str) -> List[Path]:
    """Find `.0.vgr` replay files directly under a replay directory."""
    path = Path(directory)
    return sorted(
        [item for item in path.iterdir() if item.is_file() and item.name.endswith(".0.vgr")],
        key=lambda item: item.name,
    )


def build_truth_stub_for_replay(replay_file: str, manifest_path: Optional[str] = None) -> Dict[str, object]:
    """Build a prefilled truth stub for a replay."""
    safe = decode_match(replay_file).to_dict()
    manifest = parse_replay_manifest(manifest_path).to_dict() if manifest_path else None

    players = {}
    for player in safe["players"]:
        players[player["name"]] = {
            "team": player["team"],
            "hero_name": player["hero_name"],
            "kills": None,
            "deaths": None,
            "assists": None,
            "gold": None,
            "minion_kills": None,
            "notes": "Populate from trusted source (result image, manual review, or validated capture).",
        }

    return {
        "replay_name": safe["replay_name"],
        "replay_file": safe["replay_file"],
        "manifest": manifest,
        "prefill_source": "decoder_v2.safe-json",
        "match_info": {
            "game_mode": safe["game_mode"],
            "map_name": safe["map_name"],
            "team_size": safe["team_size"],
            "winner": None,
            "duration_seconds": None,
            "score_left": None,
            "score_right": None,
            "completeness_status": safe["completeness_status"],
            "completeness_reason": safe["completeness_reason"],
        },
        "players": players,
        "accepted_fields": safe["accepted_fields"],
        "withheld_fields": safe["withheld_fields"],
    }


def build_truth_stub_report(base_path: str, truth_path: str) -> Dict[str, object]:
    """Build truth stubs for replay directories not yet covered by truth."""
    inventory = build_truth_inventory(base_path, truth_path)
    stubs = []

    for row in inventory["missing"]:
        directory = row["directory"]
        replay_files = find_replay_files(directory)
        manifest_candidates = sorted(Path(directory).glob("replayManifest-*.txt"))
        manifest_path = str(manifest_candidates[0]) if manifest_candidates else None

        for replay_file in replay_files:
            stubs.append(build_truth_stub_for_replay(str(replay_file), manifest_path))

    return {
        "schema_version": "decoder_v2.truth_stub_report.v1",
        "base_path": str(Path(base_path).resolve()),
        "truth_path": str(Path(truth_path).resolve()),
        "stub_count": len(stubs),
        "stubs": stubs,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Generate truth stubs for unlabeled replay directories.")
    parser.add_argument(
        "--base",
        default=r"D:\Desktop\My Folder\Game\VG\vg replay",
        help="Base replay directory",
    )
    parser.add_argument(
        "--truth",
        default="vg/output/tournament_truth.json",
        help="Truth JSON path",
    )
    parser.add_argument(
        "--output",
        help="Optional output path",
    )
    args = parser.parse_args(argv)

    report = build_truth_stub_report(args.base, args.truth)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Truth stubs saved to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
