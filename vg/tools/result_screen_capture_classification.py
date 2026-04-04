"""Classify result-screen capture sessions for follow-up processing."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

from .result_screen_capture_inventory import build_result_screen_capture_inventory


def build_result_screen_capture_classification(memory_sessions_root: str) -> Dict[str, object]:
    inventory = build_result_screen_capture_inventory(memory_sessions_root)
    rows: List[Dict[str, object]] = []

    for row in inventory["rows"]:
        if row["has_result_dump"] and row["has_replay_name"]:
            status = "ready_for_processing"
            blocking_reason = None
        elif row["has_result_dump"] and not row["has_replay_name"]:
            status = "needs_manifest_replay_name"
            blocking_reason = "Result dump exists but manifest replay_name is missing."
        elif row["has_result_image"] and not row["has_result_dump"]:
            status = "image_only_capture"
            blocking_reason = "Captured result image exists without a dump."
        else:
            status = "uncaptured"
            blocking_reason = "No result-screen capture exists."

        rows.append(
            {
                **row,
                "processing_status": status,
                "processing_blocking_reason": blocking_reason,
            }
        )

    return {
        "memory_sessions_root": inventory["memory_sessions_root"],
        "row_count": len(rows),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify result-screen capture sessions.")
    parser.add_argument("--memory-sessions-root", required=True, help="Memory sessions root")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args()

    report = build_result_screen_capture_classification(args.memory_sessions_root)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"Result-screen capture classification saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
