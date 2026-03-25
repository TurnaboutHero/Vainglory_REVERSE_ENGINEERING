"""Rank unlabeled replay stubs by expected truth-capture value."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .truth_stubs import build_truth_stub_report


def _score_stub(stub: Dict[str, object]) -> Dict[str, object]:
    match_info = stub["match_info"]
    accepted_fields = stub.get("accepted_fields", {})

    score = 0
    tags: List[str] = []

    completeness = match_info["completeness_status"]
    if completeness == "complete_confirmed":
        score += 40
        tags.append("complete_confirmed")
    elif completeness == "completeness_unknown":
        score += 10
        tags.append("completeness_unknown")

    if match_info["team_size"] == 5:
        score += 15
        tags.append("5v5")
    elif match_info["team_size"] == 3:
        score += 5
        tags.append("3v3")

    game_mode = str(match_info["game_mode"])
    if game_mode == "GameMode_5v5_Ranked":
        score += 20
        tags.append("5v5_ranked")
    elif game_mode == "GameMode_HF_Ranked":
        score += 10
        tags.append("3v3_ranked")
    elif game_mode == "GameMode_5v5_Casual":
        score += 5
        tags.append("5v5_casual")

    if "winner" in accepted_fields:
        score += 10
        tags.append("winner_accepted")
    if "kills" in accepted_fields:
        score += 10
        tags.append("kda_accepted")

    if stub.get("manifest"):
        score += 5
        tags.append("manifest_linked")

    return {
        "score": score,
        "tags": tags,
    }


def build_truth_labeling_queue(base_path: str, truth_path: str) -> Dict[str, object]:
    stub_report = build_truth_stub_report(base_path, truth_path)
    rows = []
    for stub in stub_report["stubs"]:
        scored = _score_stub(stub)
        rows.append(
            {
                "score": scored["score"],
                "priority_tags": scored["tags"],
                "replay_name": stub["replay_name"],
                "replay_file": stub["replay_file"],
                "fixture_directory": str(Path(stub["replay_file"]).parent),
                "game_mode": stub["match_info"]["game_mode"],
                "team_size": stub["match_info"]["team_size"],
                "completeness_status": stub["match_info"]["completeness_status"],
                "manifest_linked": stub.get("manifest") is not None,
                "accepted_fields": sorted(stub.get("accepted_fields", {}).keys()),
            }
        )

    rows.sort(
        key=lambda row: (
            int(row["score"]),
            int(row["team_size"]),
            row["game_mode"] == "GameMode_5v5_Ranked",
            row["completeness_status"] == "complete_confirmed",
        ),
        reverse=True,
    )

    return {
        "schema_version": "decoder_v2.truth_labeling_queue.v1",
        "base_path": str(Path(base_path).resolve()),
        "truth_path": str(Path(truth_path).resolve()),
        "queue_size": len(rows),
        "top_candidates": rows[:20],
        "rows": rows,
    }


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Rank unlabeled replays for manual/automated truth capture.")
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
    args = parser.parse_args(list(argv) if argv is not None else None)

    report = build_truth_labeling_queue(args.base, args.truth)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Truth labeling queue saved to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
