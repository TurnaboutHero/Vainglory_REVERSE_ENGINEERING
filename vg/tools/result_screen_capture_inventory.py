"""Inventory captured result-screen artifacts under memory_sessions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional


def _load_manifest(session_dir: Path) -> Optional[Dict[str, object]]:
    manifest = session_dir / "manifest.json"
    if not manifest.exists():
        return None
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def build_result_screen_capture_inventory(memory_sessions_root: str) -> Dict[str, object]:
    root = Path(memory_sessions_root)
    rows: List[Dict[str, object]] = []

    for session_dir in sorted(path.resolve() for path in root.iterdir() if path.is_dir()):
        manifest = _load_manifest(session_dir)
        replay_name = manifest.get("replay_name") if manifest else None

        result_dumps = sorted(session_dir.rglob("result_screen_full.dmp"))
        result_screens = sorted(
            [
                *session_dir.rglob("result_screen*.png"),
                *session_dir.rglob("result_screen*.jpg"),
                *session_dir.rglob("result_screen*.jpeg"),
            ]
        )

        if result_dumps:
            status = "captured_result_dump"
            blocking_reason = None
        elif result_screens:
            status = "captured_result_image_only"
            blocking_reason = "Result image exists but result dump is missing."
        else:
            status = "missing_result_capture"
            blocking_reason = "Session has no captured result-screen dump or image."

        rows.append(
            {
                "session_dir": str(session_dir),
                "replay_name": replay_name,
                "manifest_path": str((session_dir / "manifest.json").resolve()) if (session_dir / "manifest.json").exists() else None,
                "result_dump_path": str(result_dumps[0].resolve()) if result_dumps else None,
                "result_image_path": str(result_screens[0].resolve()) if result_screens else None,
                "has_manifest": manifest is not None,
                "has_replay_name": bool(replay_name),
                "has_result_dump": bool(result_dumps),
                "has_result_image": bool(result_screens),
                "status": status,
                "blocking_reason": blocking_reason,
            }
        )

    return {
        "memory_sessions_root": str(root.resolve()),
        "row_count": len(rows),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory captured result-screen artifacts under memory_sessions.")
    parser.add_argument("--memory-sessions-root", required=True, help="Memory sessions root")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args()

    report = build_result_screen_capture_inventory(args.memory_sessions_root)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"Result-screen capture inventory saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
