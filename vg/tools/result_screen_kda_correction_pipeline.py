"""Run autobundle + inventory + optional corrected export over a memory-session tree."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Set

from vg.decoder_v2.index_export import MINION_POLICY_NONE, build_index_ready_export
from vg.decoder_v2.kda_mismatch_triage import build_kda_mismatch_triage
from vg.decoder_v2.kda_result_capture_backlog import build_kda_result_capture_backlog

from .result_screen_kda_correction_autobundle import build_result_screen_kda_correction_autobundle
from .result_screen_kda_correction_inventory import build_result_screen_kda_correction_inventory
from .result_screen_kda_correction_readiness import (
    build_result_screen_kda_correction_readiness,
)
from .result_screen_kda_validation import build_result_screen_kda_validation


def _discover_session_dirs(memory_sessions_root: Path) -> List[Path]:
    seen: Set[Path] = set()
    sessions: List[Path] = []
    for dump in sorted(memory_sessions_root.rglob("result_screen_full.dmp")):
        session_dir = dump.parent.parent if dump.parent.name == "dumps" else dump.parent
        session_dir = session_dir.resolve()
        if session_dir not in seen:
            seen.add(session_dir)
            sessions.append(session_dir)
    return sessions


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def build_result_screen_kda_correction_pipeline(
    memory_sessions_root: str,
    output_root: str,
    *,
    export_base_path: Optional[str] = None,
    minion_policy: str = MINION_POLICY_NONE,
    truth_path: str = "vg/output/tournament_truth.json",
) -> Dict[str, object]:
    root = Path(memory_sessions_root)
    output_root_path = Path(output_root)

    bundled_sessions = []
    failed_sessions = []
    session_dirs = _discover_session_dirs(root)
    for session_dir in session_dirs:
        try:
            bundle = build_result_screen_kda_correction_autobundle(str(session_dir), str(output_root_path))
            bundle_dir = session_dir / "autobundle_auto"
            bundle_dir.mkdir(parents=True, exist_ok=True)
            _write_json(bundle_dir / "result_screen_kda_correction_report.json", bundle["report"])
            _write_json(bundle_dir / "result_screen_kda_correction_apply.json", bundle["apply"])
            _write_json(bundle_dir / "result_screen_kda_correction_merge.json", bundle["merge"])
            _write_json(bundle_dir / "result_screen_kda_correction_meta.json", bundle["meta"])
            bundled_sessions.append(
                {
                    "session_dir": str(session_dir),
                    "bundle_dir": str(bundle_dir),
                    "replay_name": bundle["meta"]["replay_name"],
                }
            )
        except Exception as exc:
            failed_sessions.append(
                {
                    "session_dir": str(session_dir),
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    inventory = build_result_screen_kda_correction_inventory(str(root))
    readiness = build_result_screen_kda_correction_readiness(str(root), str(output_root_path))
    validation = build_result_screen_kda_validation(str(root), str(output_root_path), truth_path)
    validation_by_replay = {
        str(row["replay_name"]): row
        for row in validation["rows"]
        if row.get("replay_name")
    }
    for row in readiness["rows"]:
        replay_name = row.get("replay_name")
        validation_row = validation_by_replay.get(str(replay_name)) if replay_name else None
        if validation_row and validation_row.get("status") == "needs_review":
            row["status"] = "needs_review"
            row["blocking_reason"] = "Result-screen correction validation regressed against reference rows."
    mismatch_report = build_kda_mismatch_triage(
        truth_path,
        kill_buffer=20,
        death_buffer=3,
        complete_only=True,
    )
    backlog = build_kda_result_capture_backlog(readiness, mismatch_report)
    export_payload = None
    if export_base_path:
        export_payload = build_index_ready_export(
            export_base_path,
            minion_policy=minion_policy,
            kda_correction_path=str(root),
        )

    return {
        "memory_sessions_root": str(root.resolve()),
        "output_root": str(output_root_path.resolve()),
        "truth_path": str(Path(truth_path).resolve()),
        "discovered_session_count": len(session_dirs),
        "bundled_session_count": len(bundled_sessions),
        "failed_session_count": len(failed_sessions),
        "bundled_sessions": bundled_sessions,
        "failed_sessions": failed_sessions,
        "inventory": inventory,
        "readiness": readiness,
        "validation": validation,
        "backlog": backlog,
        "export": export_payload,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run result-screen KDA correction pipeline over a memory-session tree.")
    parser.add_argument("--memory-sessions-root", required=True, help="Root directory containing memory sessions")
    parser.add_argument("--output-root", default="vg/output", help="Output root containing decoded payloads")
    parser.add_argument("--export-base-path", help="Optional replay root for corrected export generation")
    parser.add_argument("--truth", default="vg/output/tournament_truth.json", help="Truth JSON path")
    parser.add_argument(
        "--minion-policy",
        default=MINION_POLICY_NONE,
        help="Minion policy forwarded to index export when export is requested",
    )
    parser.add_argument("--output", help="Optional pipeline report JSON path")
    parser.add_argument("--export-output", help="Optional corrected export JSON path")
    parser.add_argument(
        "--readiness-output",
        default="vg/output/memory_sessions/result_screen_kda_correction_readiness.json",
        help="Readiness output JSON path",
    )
    parser.add_argument(
        "--validation-output",
        default="vg/output/result_screen_kda_validation.json",
        help="Validation output JSON path",
    )
    parser.add_argument(
        "--backlog-output",
        default="vg/output/kda_result_capture_backlog.json",
        help="Capture backlog output JSON path",
    )
    args = parser.parse_args()

    report = build_result_screen_kda_correction_pipeline(
        args.memory_sessions_root,
        args.output_root,
        export_base_path=args.export_base_path,
        minion_policy=args.minion_policy,
        truth_path=args.truth,
    )

    if args.export_output and report["export"] is not None:
        _write_json(Path(args.export_output), report["export"])
        print(f"Corrected export saved to {args.export_output}")
        refreshed_readiness = build_result_screen_kda_correction_readiness(
            args.memory_sessions_root,
            args.output_root,
        )
        refreshed_backlog = build_kda_result_capture_backlog(
            refreshed_readiness,
            build_kda_mismatch_triage(
                args.truth,
                kill_buffer=20,
                death_buffer=3,
                complete_only=True,
            ),
        )
        report["readiness"] = refreshed_readiness
        report["backlog"] = refreshed_backlog

    if args.output:
        _write_json(Path(args.output), report)
        print(f"Result-screen KDA correction pipeline report saved to {args.output}")
    else:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    _write_json(Path(args.readiness_output), report["readiness"])
    print(f"Readiness report saved to {args.readiness_output}")
    _write_json(Path(args.validation_output), report["validation"])
    print(f"Validation report saved to {args.validation_output}")
    _write_json(Path(args.backlog_output), report["backlog"])
    print(f"Capture backlog saved to {args.backlog_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
