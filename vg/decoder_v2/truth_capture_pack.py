"""Build a focused truth-capture pack from the labeling queue and prefixed truth stubs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .truth_labeling_queue import build_truth_labeling_queue
from .truth_stubs import build_truth_stub_report


def _capture_track(queue_row: Dict[str, object]) -> str:
    completeness = str(queue_row["completeness_status"])
    game_mode = str(queue_row["game_mode"])
    team_size = int(queue_row["team_size"])

    if completeness != "complete_confirmed":
        return "resolve_completeness_first"
    if team_size == 5 and game_mode == "GameMode_5v5_Ranked":
        return "validate_5v5_ranked_minion_and_kda_policy"
    if team_size == 5:
        return "expand_complete_5v5_generalization"
    if team_size == 3:
        return "expand_3v3_generalization"
    return "general_truth_capture"


def _capture_reason(queue_row: Dict[str, object]) -> str:
    completeness = str(queue_row["completeness_status"])
    game_mode = str(queue_row["game_mode"])
    if completeness != "complete_confirmed":
        return "Replay is not yet confidently complete, so truth capture mainly helps resolve completeness and unsupported-tail behavior."
    if game_mode == "GameMode_5v5_Ranked":
        return "Highest-value unlabeled fixture type: complete-confirmed 5v5 ranked replay with winner/KDA already accepted, so new truth directly stress-tests minion and index policy."
    if game_mode == "GameMode_5v5_Casual":
        return "Complete-confirmed 5v5 replay with accepted winner/KDA; adds non-tournament generalization for safe decoder fields."
    return "Useful unlabeled replay that can widen truth coverage outside the current tournament validation set."


def _capture_requirements(queue_row: Dict[str, object]) -> List[str]:
    requirements = [
        "final winner",
        "final team score",
        "per-player K/D/A",
        "per-player gold or bounty field if visible",
        "per-player minion kills or bounty field if visible",
    ]
    if str(queue_row["completeness_status"]) != "complete_confirmed":
        requirements.append("full-length replay completeness confirmation")
    return requirements


def build_truth_capture_pack(base_path: str, truth_path: str, limit: int = 20) -> Dict[str, object]:
    queue = build_truth_labeling_queue(base_path, truth_path)
    stubs = build_truth_stub_report(base_path, truth_path)
    stub_by_replay_file = {
        str(stub["replay_file"]): stub
        for stub in stubs["stubs"]
    }

    items = []
    for queue_row in queue["rows"][:limit]:
        replay_file = str(queue_row["replay_file"])
        stub = stub_by_replay_file.get(replay_file)
        if not stub:
            continue
        items.append(
            {
                "score": queue_row["score"],
                "capture_track": _capture_track(queue_row),
                "capture_reason": _capture_reason(queue_row),
                "capture_requirements": _capture_requirements(queue_row),
                "queue_entry": queue_row,
                "truth_stub": stub,
            }
        )

    return {
        "schema_version": "decoder_v2.truth_capture_pack.v1",
        "base_path": str(Path(base_path).resolve()),
        "truth_path": str(Path(truth_path).resolve()),
        "requested_limit": limit,
        "generated_items": len(items),
        "items": items,
    }


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build a focused truth-capture pack from the top labeling queue items.")
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
    parser.add_argument("--limit", type=int, default=20, help="Maximum number of top queue items to include")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(list(argv) if argv is not None else None)

    report = build_truth_capture_pack(args.base, args.truth, limit=args.limit)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Truth capture pack saved to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
