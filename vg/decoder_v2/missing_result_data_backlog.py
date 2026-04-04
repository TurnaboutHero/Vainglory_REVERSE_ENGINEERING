"""Prioritize replay directories that still lack captured result data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

from .decode_match import decode_match
from .truth_inventory import build_truth_inventory
from .truth_stubs import find_replay_files
from .manifest import parse_replay_manifest
from vg.tools.result_screen_capture_classification import build_result_screen_capture_classification


def _replay_name_from_file(replay_file: Path) -> str:
    stem = replay_file.stem
    return stem.rsplit(".", 1)[0]


def _discover_corrected_exports(output_root: Path) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for candidate in sorted(output_root.rglob("*.json")):
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict) or payload.get("schema_version") != "decoder_v2.index_export.v2":
            continue
        matches = payload.get("matches")
        if not isinstance(matches, list):
            continue
        for match in matches:
            if not isinstance(match, dict):
                continue
            replay_name = match.get("replay_name")
            correction = match.get("kda_correction")
            if replay_name and isinstance(correction, dict) and correction.get("applied"):
                out[str(replay_name)] = str(candidate.resolve())
    return out


def build_missing_result_data_backlog(
    base_path: str,
    truth_path: str,
    *,
    memory_sessions_root: str = "vg/output/memory_sessions",
    output_root: str = "vg/output",
) -> Dict[str, object]:
    inventory = build_truth_inventory(base_path, truth_path)
    capture_classification = build_result_screen_capture_classification(memory_sessions_root)
    capture_by_replay = {
        str(row["replay_name"]): row
        for row in capture_classification["rows"]
        if row.get("replay_name")
    }
    corrected_exports = _discover_corrected_exports(Path(output_root))

    rows: List[Dict[str, object]] = []
    for directory_row in inventory["missing"]:
        replay_files = find_replay_files(directory_row["directory"])
        if not replay_files:
            continue
        replay_file = replay_files[0]
        replay_name = _replay_name_from_file(replay_file)
        capture_row = capture_by_replay.get(replay_name, {})
        corrected_export_path = corrected_exports.get(replay_name)
        if corrected_export_path:
            continue

        manifest_candidates = sorted(Path(directory_row["directory"]).glob("replayManifest-*.txt"))
        manifest = parse_replay_manifest(str(manifest_candidates[0])).to_dict() if manifest_candidates else None
        safe = decode_match(str(replay_file)).to_dict()

        if directory_row["has_manifest"]:
            source_type = "manifest_only"
            priority = 1
        else:
            source_type = "raw_only"
            priority = 2

        if safe["completeness_status"] == "complete_confirmed":
            priority -= 0
        else:
            priority += 1

        rows.append(
            {
                "replay_name": replay_name,
                "replay_file": str(replay_file.resolve()),
                "directory": directory_row["directory"],
                "source_type": source_type,
                "priority": priority,
                "has_manifest": directory_row["has_manifest"],
                "has_result_image": directory_row["has_result_image"],
                "has_result_dump": bool(capture_row.get("has_result_dump")),
                "has_capture_image": bool(capture_row.get("has_result_image")),
                "has_corrected_export": False,
                "capture_status": capture_row.get("processing_status"),
                "decoded_game_mode": safe["game_mode"],
                "decoded_team_size": safe["team_size"],
                "decoded_completeness_status": safe["completeness_status"],
                "decoded_winner_available": bool(safe["accepted_fields"].get("winner", {}).get("accepted_for_index")),
                "manifest": manifest,
            }
        )

    rows.sort(
        key=lambda row: (
            row["priority"],
            0 if row["decoded_completeness_status"] == "complete_confirmed" else 1,
            0 if row["decoded_team_size"] == 5 else 1,
            row["replay_name"],
        )
    )
    return {
        "base_path": str(Path(base_path).resolve()),
        "truth_path": str(Path(truth_path).resolve()),
        "memory_sessions_root": str(Path(memory_sessions_root).resolve()),
        "output_root": str(Path(output_root).resolve()),
        "row_count": len(rows),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build backlog of replay directories still missing result data.")
    parser.add_argument("--base", default=r"D:\Desktop\My Folder\Game\VG\vg replay", help="Base replay directory")
    parser.add_argument("--truth", default="vg/output/tournament_truth.json", help="Truth JSON path")
    parser.add_argument("--memory-sessions-root", default="vg/output/memory_sessions", help="Memory sessions root")
    parser.add_argument("--output-root", default="vg/output", help="Output root")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args()

    report = build_missing_result_data_backlog(
        args.base,
        args.truth,
        memory_sessions_root=args.memory_sessions_root,
        output_root=args.output_root,
    )
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"Missing result data backlog saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
