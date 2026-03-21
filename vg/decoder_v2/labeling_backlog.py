"""Build a concrete truth-labeling backlog from local replay inventory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

from .truth_inventory import build_truth_inventory


def build_labeling_backlog(base_path: str, truth_path: str) -> Dict[str, object]:
    """Prioritize local replay directories for future truth creation."""
    inventory = build_truth_inventory(base_path, truth_path)
    covered = inventory["covered"]
    missing = inventory["missing"]

    immediately_labelable = [row for row in missing if row["has_result_image"]]
    manifest_only = [row for row in missing if row["has_manifest"] and not row["has_result_image"]]
    raw_only = [row for row in missing if not row["has_manifest"] and not row["has_result_image"]]

    return {
        "summary": {
            "total_replay_directories": inventory["total_replay_directories"],
            "covered_directories": inventory["covered_directories"],
            "missing_directories": inventory["missing_directories"],
            "coverage_pct": inventory["coverage_pct"],
            "immediately_labelable": len(immediately_labelable),
            "manifest_only": len(manifest_only),
            "raw_only": len(raw_only),
        },
        "immediately_labelable": immediately_labelable,
        "manifest_only": manifest_only,
        "raw_only": raw_only,
        "covered": covered,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build a truth-labeling backlog for local replay directories.")
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
        help="Optional output JSON path",
    )
    args = parser.parse_args(argv)

    report = build_labeling_backlog(args.base, args.truth)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"Labeling backlog saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
