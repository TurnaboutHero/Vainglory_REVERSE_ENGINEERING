"""Refresh the KDA truth pipeline and prepare the next capture session."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Optional

from vg.decoder_v2.minion_policy import MINION_POLICY_NONE

from .memory_session_manifest import build_memory_session_manifest
from .result_screen_kda_correction_pipeline import build_result_screen_kda_correction_pipeline


def _load_json(path: Path) -> Optional[Dict[str, object]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    return slug or "capture"


def _resolve_replay_file(replay_name: str, pipeline_report: Dict[str, object]) -> Optional[str]:
    backlog_rows = pipeline_report.get("backlog", {}).get("rows", [])
    for row in backlog_rows:
        if row.get("replay_name") == replay_name and row.get("replay_file"):
            return str(row["replay_file"])

    readiness_rows = pipeline_report.get("readiness", {}).get("rows", [])
    for row in readiness_rows:
        if row.get("replay_name") != replay_name:
            continue
        decoded_payload_path = row.get("decoded_payload_path")
        if not decoded_payload_path:
            continue
        payload = _load_json(Path(str(decoded_payload_path)))
        safe_output = payload.get("safe_output") if payload else None
        replay_file = safe_output.get("replay_file") if isinstance(safe_output, dict) else None
        if replay_file:
            return str(replay_file)
    return None


def _build_next_capture(
    pipeline_report: Dict[str, object],
    session_output_root: Optional[str],
) -> Optional[Dict[str, object]]:
    backlog_rows = pipeline_report.get("backlog", {}).get("rows", [])
    if not backlog_rows:
        return None

    row = dict(backlog_rows[0])
    replay_name = str(row["replay_name"])
    replay_file = row.get("replay_file") or _resolve_replay_file(replay_name, pipeline_report)
    replay_source_dir = str(Path(replay_file).resolve().parent) if replay_file else None

    result = {
        "replay_name": replay_name,
        "priority": row.get("priority"),
        "reason": row.get("reason", []),
        "replay_file": replay_file,
        "replay_source_dir": replay_source_dir,
        "session_root": None,
        "manifest_path": None,
        "manifest_created": False,
    }

    if session_output_root and replay_source_dir:
        session_root = Path(session_output_root) / f"capture_{_slugify(replay_name)}"
        manifest = build_memory_session_manifest(
            session_root=str(session_root),
            replay_source_dir=replay_source_dir,
            replay_name=replay_name,
            phases=["result_screen"],
        )
        manifest_path = session_root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        result["session_root"] = str(session_root.resolve())
        result["manifest_path"] = str(manifest_path.resolve())
        result["manifest_created"] = True

    return result


def build_kda_truth_loop_report(
    memory_sessions_root: str,
    output_root: str,
    *,
    truth_path: str,
    session_output_root: Optional[str] = None,
    export_base_path: Optional[str] = None,
    minion_policy: str = MINION_POLICY_NONE,
) -> Dict[str, object]:
    pipeline_report = build_result_screen_kda_correction_pipeline(
        memory_sessions_root,
        output_root,
        export_base_path=export_base_path,
        minion_policy=minion_policy,
        truth_path=truth_path,
    )
    next_capture = _build_next_capture(pipeline_report, session_output_root)

    return {
        "memory_sessions_root": str(Path(memory_sessions_root).resolve()),
        "output_root": str(Path(output_root).resolve()),
        "truth_path": str(Path(truth_path).resolve()),
        "backlog_row_count": pipeline_report.get("backlog", {}).get("row_count", 0),
        "bundled_session_count": pipeline_report.get("bundled_session_count", 0),
        "failed_session_count": pipeline_report.get("failed_session_count", 0),
        "next_capture": next_capture,
        "pipeline": pipeline_report,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh KDA truth loop state and prepare the next capture session.")
    parser.add_argument("--memory-sessions-root", required=True, help="Memory sessions root")
    parser.add_argument("--output-root", default="vg/output", help="Output root")
    parser.add_argument("--truth", default="vg/output/tournament_truth.json", help="Truth JSON path")
    parser.add_argument("--session-output-root", help="Optional root where the next capture manifest should be created")
    parser.add_argument("--export-base-path", help="Optional replay root for corrected export generation")
    parser.add_argument("--minion-policy", default=MINION_POLICY_NONE, help="Minion policy forwarded to the correction pipeline")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(argv)

    report = build_kda_truth_loop_report(
        args.memory_sessions_root,
        args.output_root,
        truth_path=args.truth,
        session_output_root=args.session_output_root,
        export_base_path=args.export_base_path,
        minion_policy=args.minion_policy,
    )
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"KDA truth loop report saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
