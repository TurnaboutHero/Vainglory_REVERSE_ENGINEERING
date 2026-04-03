"""Build prioritized replay capture backlog for result-screen KDA correction."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

from .kda_mismatch_triage import build_kda_mismatch_triage


def build_kda_result_capture_backlog(
    readiness_report: Dict[str, object],
    mismatch_report: Dict[str, object],
) -> Dict[str, object]:
    readiness_by_replay = {
        str(row["replay_name"]): row for row in readiness_report["rows"] if row.get("replay_name")
    }
    grouped: Dict[str, Dict[str, object]] = {}
    for row in mismatch_report["rows"]:
        replay_name = str(row["replay_name"])
        item = grouped.setdefault(
            replay_name,
            {
                "replay_name": replay_name,
                "fixture_directory": row["fixture_directory"],
                "replay_file": row.get("replay_file"),
                "reason": [],
                "priority": 1,
                "has_result_dump": False,
                "has_bundle": False,
                "has_corrected_export": False,
            },
        )
        metrics = [metric for metric, diff in row["diff"].items() if diff != 0]
        item["reason"].append(f"truth_residual:{row['player_name']}:{'/'.join(metrics)}")

    for replay_name, readiness in readiness_by_replay.items():
        item = grouped.get(replay_name)
        if item:
            item["has_result_dump"] = readiness["has_result_dump"]
            item["has_bundle"] = readiness["has_bundle"]
            item["has_corrected_export"] = readiness["has_corrected_export"]
            continue

        if readiness["status"] == "missing_result_dump" and readiness.get("decoded_payload_path"):
            grouped[replay_name] = {
                "replay_name": replay_name,
                "fixture_directory": None,
                "reason": ["decoded_payload_available_no_result_dump"],
                "priority": 3,
                "has_result_dump": False,
                "has_bundle": readiness["has_bundle"],
                "has_corrected_export": readiness["has_corrected_export"],
            }

    rows = []
    for replay_name, item in grouped.items():
        if item["has_corrected_export"]:
            continue
        reasons = item["reason"]
        fixture_directory = item["fixture_directory"]
        replay_file = str(item.get("replay_file") or "")
        if any("truth_residual" in reason for reason in reasons):
            priority = 1
        elif "(Finals)" in replay_file:
            priority = 2
        elif "decoded_payload_available_no_result_dump" in reasons:
            priority = 3
        else:
            priority = 4
        rows.append(
            {
                **item,
                "reason": reasons,
                "priority": priority,
            }
        )

    rows.sort(key=lambda row: (row["priority"], row["replay_name"]))
    return {
        "row_count": len(rows),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build KDA result capture backlog.")
    parser.add_argument("--readiness", required=True, help="Readiness report JSON path")
    parser.add_argument("--mismatch", required=True, help="KDA mismatch triage JSON path")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args()

    readiness_report = json.loads(Path(args.readiness).read_text(encoding="utf-8"))
    mismatch_report = json.loads(Path(args.mismatch).read_text(encoding="utf-8"))
    report = build_kda_result_capture_backlog(readiness_report, mismatch_report)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"KDA result capture backlog saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
