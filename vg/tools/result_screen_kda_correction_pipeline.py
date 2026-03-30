"""Run autobundle + inventory + optional corrected export over a memory-session tree."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Set

from vg.decoder_v2.index_export import MINION_POLICY_NONE, build_index_ready_export

from .result_screen_kda_correction_autobundle import build_result_screen_kda_correction_autobundle
from .result_screen_kda_correction_inventory import build_result_screen_kda_correction_inventory


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
) -> Dict[str, object]:
    root = Path(memory_sessions_root)
    output_root_path = Path(output_root)

    bundled_sessions = []
    failed_sessions = []
    for session_dir in _discover_session_dirs(root):
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
        "discovered_session_count": len(_discover_session_dirs(root)),
        "bundled_session_count": len(bundled_sessions),
        "failed_session_count": len(failed_sessions),
        "bundled_sessions": bundled_sessions,
        "failed_sessions": failed_sessions,
        "inventory": inventory,
        "export": export_payload,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run result-screen KDA correction pipeline over a memory-session tree.")
    parser.add_argument("--memory-sessions-root", required=True, help="Root directory containing memory sessions")
    parser.add_argument("--output-root", default="vg/output", help="Output root containing decoded payloads")
    parser.add_argument("--export-base-path", help="Optional replay root for corrected export generation")
    parser.add_argument(
        "--minion-policy",
        default=MINION_POLICY_NONE,
        help="Minion policy forwarded to index export when export is requested",
    )
    parser.add_argument("--output", help="Optional pipeline report JSON path")
    parser.add_argument("--export-output", help="Optional corrected export JSON path")
    args = parser.parse_args()

    report = build_result_screen_kda_correction_pipeline(
        args.memory_sessions_root,
        args.output_root,
        export_base_path=args.export_base_path,
        minion_policy=args.minion_policy,
    )
    if args.output:
        _write_json(Path(args.output), report)
        print(f"Result-screen KDA correction pipeline report saved to {args.output}")
    else:
        print(json.dumps(report, indent=2, ensure_ascii=False))

    if args.export_output and report["export"] is not None:
        _write_json(Path(args.export_output), report["export"])
        print(f"Corrected export saved to {args.export_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
