"""Prioritize next truth-expansion work from local replay inventory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

from .truth_inventory import build_truth_inventory


def _collection_key(directory: str, base_path: str) -> str:
    base = Path(base_path).resolve()
    path = Path(directory).resolve()
    try:
        relative = path.relative_to(base)
    except ValueError:
        return path.parent.name or path.name
    return str(relative.parent) if relative.parent != Path(".") else relative.name


def build_truth_source_priority_from_inventory(
    inventory: Dict[str, object],
) -> Dict[str, object]:
    """Summarize the next best truth-expansion moves from an inventory payload."""
    base_path = str(inventory["base_path"])
    covered = inventory["covered"]
    missing = inventory["missing"]

    collections: Dict[str, Dict[str, object]] = {}
    for row in covered + missing:
        key = _collection_key(str(row["directory"]), base_path)
        collection = collections.setdefault(
            key,
            {
                "collection": key,
                "total_directories": 0,
                "covered_directories": 0,
                "missing_directories": 0,
                "missing_with_result_image": 0,
                "missing_manifest_only": 0,
                "missing_raw_only": 0,
            },
        )
        collection["total_directories"] += 1
        if row.get("covered_by_truth"):
            collection["covered_directories"] += 1
        else:
            collection["missing_directories"] += 1
            if row.get("has_result_image"):
                collection["missing_with_result_image"] += 1
            elif row.get("has_manifest"):
                collection["missing_manifest_only"] += 1
            else:
                collection["missing_raw_only"] += 1

    collection_rows = sorted(
        collections.values(),
        key=lambda item: (
            item["missing_with_result_image"],
            item["missing_manifest_only"],
            item["missing_directories"],
        ),
        reverse=True,
    )

    immediately_labelable = [row for row in missing if row["has_result_image"]]
    manifest_only = [row for row in missing if row["has_manifest"] and not row["has_result_image"]]
    raw_only = [row for row in missing if not row["has_manifest"] and not row["has_result_image"]]

    recommended_actions = []
    if immediately_labelable:
        recommended_actions.append(
            {
                "priority": 1,
                "action": "label_from_existing_result_images",
                "reason": "There are uncovered replay directories that already contain result images.",
                "count": len(immediately_labelable),
            }
        )
    if manifest_only:
        recommended_actions.append(
            {
                "priority": 2 if immediately_labelable else 1,
                "action": "capture_or_recover_result_images_for_manifest_only_dirs",
                "reason": "Manifest-only directories can be linked to replay sessions but still lack score/player truth sources.",
                "count": len(manifest_only),
            }
        )
    if raw_only:
        recommended_actions.append(
            {
                "priority": 3 if immediately_labelable or manifest_only else 1,
                "action": "recover_bundle_metadata_for_raw_only_dirs",
                "reason": "These directories lack both result images and manifests, so replay linkage itself is weak.",
                "count": len(raw_only),
            }
        )

    if not immediately_labelable:
        recommended_actions.append(
            {
                "priority": 1,
                "action": "do_not_scale_ocr_yet",
                "reason": "There is no uncovered result-image backlog, so OCR expansion alone will not materially increase truth coverage.",
                "count": 0,
            }
        )

    return {
        "base_path": base_path,
        "truth_path": str(inventory["truth_path"]),
        "summary": {
            "total_replay_directories": inventory["total_replay_directories"],
            "covered_directories": inventory["covered_directories"],
            "missing_directories": inventory["missing_directories"],
            "coverage_pct": inventory["coverage_pct"],
            "immediately_labelable": len(immediately_labelable),
            "manifest_only": len(manifest_only),
            "raw_only": len(raw_only),
        },
        "recommended_actions": recommended_actions,
        "top_collections": collection_rows[:20],
    }


def build_truth_source_priority(base_path: str, truth_path: str) -> Dict[str, object]:
    """Build a priority report for truth-source expansion."""
    inventory = build_truth_inventory(base_path, truth_path)
    return build_truth_source_priority_from_inventory(inventory)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Prioritize next truth-expansion work from replay inventory.")
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
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(argv)

    report = build_truth_source_priority(args.base, args.truth)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Truth source priority saved to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
