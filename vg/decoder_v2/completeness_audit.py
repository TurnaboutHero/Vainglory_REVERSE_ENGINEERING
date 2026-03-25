"""Audit replay completeness decisions across a broader replay pool."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

from .batch_decode import find_replays
from .completeness import assess_completeness, extract_replay_signals


def _build_review_flags(signals: object, status: str) -> List[str]:
    flags = []
    crystal_ts = signals.crystal_ts
    max_death_ts = signals.max_player_death_ts
    max_death_header_ts = signals.max_death_header_ts

    if crystal_ts is None:
        flags.append("no_crystal_signal")
    if max_death_ts is None:
        flags.append("no_player_death_tail")
    if max_death_header_ts is None:
        flags.append("no_generic_death_tail")
    if (
        crystal_ts is not None
        and max_death_ts is not None
        and abs(crystal_ts - max_death_ts) > 60
    ):
        flags.append("crystal_player_death_gap_gt_60s")
    if (
        max_death_ts is not None
        and max_death_header_ts is not None
        and abs(max_death_header_ts - max_death_ts) > 60
    ):
        flags.append("generic_player_death_gap_gt_60s")
    if status == "complete_confirmed" and crystal_ts is None:
        flags.append("complete_without_crystal")
    if status == "completeness_unknown" and signals.frame_count >= 120:
        flags.append("unknown_long_replay")
    return flags


def _classify_review_bucket(row: Dict[str, object]) -> str:
    flags = set(row["review_flags"])
    frame_count = int(row["frame_count"])
    if frame_count < 20 or "no_player_death_tail" in flags:
        return "unsupported_tiny_replay"
    if "no_crystal_signal" in flags and "generic_player_death_gap_gt_60s" in flags and "unknown_long_replay" in flags:
        return "no_crystal_long_tail_gap"
    if "crystal_player_death_gap_gt_60s" in flags and "generic_player_death_gap_gt_60s" in flags and "unknown_long_replay" in flags:
        return "conflicting_long_tail_signals"
    if "crystal_player_death_gap_gt_60s" in flags and frame_count < 100:
        return "short_replay_crystal_lag"
    if "no_crystal_signal" in flags and row["status"] == "complete_confirmed":
        return "accepted_without_crystal"
    if row["status"] == "completeness_unknown":
        return "other_unknown"
    return "review_ok"


def build_completeness_audit(base_path: str) -> Dict[str, object]:
    """Audit completeness decisions for every replay under a base path."""
    replays = find_replays(base_path)
    rows = []
    status_counter: Dict[str, int] = {}

    for replay in replays:
        signals = extract_replay_signals(str(replay))
        assessment = assess_completeness(signals)
        flags = _build_review_flags(signals, assessment.status.value)
        status_counter[assessment.status.value] = status_counter.get(assessment.status.value, 0) + 1
        rows.append(
            {
                "replay_name": signals.replay_name,
                "replay_file": signals.replay_file,
                "status": assessment.status.value,
                "reason": assessment.reason,
                "frame_count": signals.frame_count,
                "max_frame_index": signals.max_frame_index,
                "crystal_ts": signals.crystal_ts,
                "max_kill_ts": signals.max_kill_ts,
                "max_player_death_ts": signals.max_player_death_ts,
                "max_death_header_ts": signals.max_death_header_ts,
                "max_item_ts": signals.max_item_ts,
                "review_flags": flags,
            }
        )

    review_bucket_counter: Dict[str, int] = {}
    for row in rows:
        row["review_bucket"] = _classify_review_bucket(row)
        review_bucket_counter[row["review_bucket"]] = review_bucket_counter.get(row["review_bucket"], 0) + 1

    review_queue = sorted(
        [row for row in rows if row["review_flags"]],
        key=lambda row: (len(row["review_flags"]), row["frame_count"]),
        reverse=True,
    )

    return {
        "base_path": str(Path(base_path).resolve()),
        "total_replays": len(replays),
        "status_summary": status_counter,
        "review_bucket_summary": review_bucket_counter,
        "review_queue_size": len(review_queue),
        "review_queue": review_queue[:50],
        "rows": rows,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Audit replay completeness decisions across a replay pool.")
    parser.add_argument(
        "--base",
        default=r"D:\Desktop\My Folder\Game\VG\vg replay",
        help="Base replay directory",
    )
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(argv)

    report = build_completeness_audit(args.base)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Completeness audit saved to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
