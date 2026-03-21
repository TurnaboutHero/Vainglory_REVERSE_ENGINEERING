"""Truth coverage inventory for local replay collections."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional


def load_truth_directories(truth_path: str) -> Dict[str, Dict[str, object]]:
    """Load replay directories covered by truth data."""
    data = json.loads(Path(truth_path).read_text(encoding="utf-8"))
    matches = data.get("matches", [])
    return {
        str(Path(match["replay_file"]).parent.resolve()): {
            "replay_name": match["replay_name"],
            "is_incomplete_fixture": "Incomplete" in Path(match["replay_file"]).parent.name,
        }
        for match in matches
    }


def scan_replay_directories(base_path: str) -> List[Dict[str, object]]:
    """Find all replay directories under a base path."""
    base = Path(base_path)
    rows = []
    for directory in base.rglob("*"):
        if not directory.is_dir() or "__MACOSX" in directory.parts:
            continue
        try:
            files = list(directory.iterdir())
        except PermissionError:
            continue
        replay_files = [f for f in files if f.is_file() and f.name.endswith(".0.vgr")]
        if not replay_files:
            continue
        rows.append(
            {
                "directory": str(directory.resolve()),
                "replay_file_count": len(replay_files),
                "has_result_image": any(
                    f.is_file()
                    and f.name.lower().startswith("result")
                    and f.suffix.lower() in {".png", ".jpg", ".jpeg"}
                    for f in files
                ),
                "has_manifest": any(f.is_file() and f.name.startswith("replayManifest-") for f in files),
            }
        )
    return sorted(rows, key=lambda item: item["directory"])


def build_truth_inventory(base_path: str, truth_path: str) -> Dict[str, object]:
    """Build a truth coverage inventory for all local replay directories."""
    rows = scan_replay_directories(base_path)
    truth_dirs = load_truth_directories(truth_path)

    covered = []
    missing = []
    for row in rows:
        truth_entry = truth_dirs.get(row["directory"])
        merged = dict(row)
        merged["covered_by_truth"] = truth_entry is not None
        if truth_entry:
            merged.update(truth_entry)
            covered.append(merged)
        else:
            missing.append(merged)

    summary = {
        "base_path": str(Path(base_path).resolve()),
        "truth_path": str(Path(truth_path).resolve()),
        "total_replay_directories": len(rows),
        "covered_directories": len(covered),
        "missing_directories": len(missing),
        "coverage_pct": (len(covered) / len(rows) * 100) if rows else 0.0,
        "directories_with_result_images": sum(1 for row in rows if row["has_result_image"]),
        "directories_with_manifest": sum(1 for row in rows if row["has_manifest"]),
        "covered": covered,
        "missing": missing,
    }
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Inventory local truth coverage across replay directories.")
    parser.add_argument(
        "--base",
        default=r"D:\Desktop\My Folder\Game\VG\vg replay",
        help="Base replay directory to inventory",
    )
    parser.add_argument(
        "--truth",
        default="vg/output/tournament_truth.json",
        help="Truth JSON path",
    )
    parser.add_argument(
        "--output",
        help="Optional output JSON path",
    )
    args = parser.parse_args(argv)

    report = build_truth_inventory(args.base, args.truth)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Truth inventory saved to {output_path}")
    else:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
