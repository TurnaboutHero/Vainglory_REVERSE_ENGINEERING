"""Build a full-corpus result-screen capture queue from local replays."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .memory_session_manifest import build_memory_session_manifest
from .result_screen_capture_inventory import build_result_screen_capture_inventory


def _slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    return slug or "capture"


def _discover_replays(replay_root: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for replay_file in sorted(replay_root.rglob("*.0.vgr")):
        if replay_file.name.startswith("._"):
            continue
        if "__MACOSX" in replay_file.parts:
            continue
        replay_name = replay_file.stem[:-2] if replay_file.stem.endswith(".0") else replay_file.stem
        rows.append(
            {
                "replay_name": replay_name,
                "replay_file": str(replay_file.resolve()),
                "replay_source_dir": str(replay_file.parent.resolve()),
            }
        )
    return rows


def _inventory_by_replay_name(memory_sessions_root: str) -> Dict[str, List[Dict[str, object]]]:
    root = Path(memory_sessions_root)
    if not root.exists():
        return {}
    inventory = build_result_screen_capture_inventory(memory_sessions_root)
    grouped: Dict[str, List[Dict[str, object]]] = {}
    for row in inventory["rows"]:
        replay_name = row.get("replay_name")
        if not replay_name:
            continue
        grouped.setdefault(str(replay_name), []).append(row)
    return grouped


def _best_status(rows: List[Dict[str, object]]) -> Tuple[str, Optional[str]]:
    if any(row.get("has_result_dump") for row in rows):
        return "captured", None
    if any(row.get("has_manifest") for row in rows):
        return "session_prepared", "Session exists but result capture is still missing."
    return "missing_session", "No capture session exists yet."


def build_result_screen_capture_queue(
    replay_root: str,
    memory_sessions_root: str,
    *,
    create_missing_sessions: bool = False,
    session_output_root: Optional[str] = None,
) -> Dict[str, object]:
    replay_root_path = Path(replay_root)
    inventory_by_name = _inventory_by_replay_name(memory_sessions_root)
    replay_rows = _discover_replays(replay_root_path)
    rows: List[Dict[str, object]] = []

    for replay in replay_rows:
        replay_name = replay["replay_name"]
        existing_rows = inventory_by_name.get(replay_name, [])
        status, blocking_reason = _best_status(existing_rows) if existing_rows else ("missing_session", "No capture session exists yet.")

        session_root = None
        manifest_path = None
        manifest_created = False
        if create_missing_sessions and status == "missing_session":
            output_root = Path(session_output_root or memory_sessions_root)
            session_root_path = output_root / f"capture_{_slugify(replay_name)}"
            manifest = build_memory_session_manifest(
                session_root=str(session_root_path),
                replay_source_dir=replay["replay_source_dir"],
                replay_name=replay_name,
                phases=["result_screen"],
            )
            manifest_path_obj = session_root_path / "manifest.json"
            manifest_path_obj.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
            session_root = str(session_root_path.resolve())
            manifest_path = str(manifest_path_obj.resolve())
            manifest_created = True
            status = "session_prepared"
            blocking_reason = "Session created; result capture still missing."

        rows.append(
            {
                **replay,
                "status": status,
                "blocking_reason": blocking_reason,
                "existing_sessions": [row["session_dir"] for row in existing_rows],
                "session_root": session_root,
                "manifest_path": manifest_path,
                "manifest_created": manifest_created,
            }
        )

    rows.sort(key=lambda row: (row["status"] != "missing_session", row["status"] != "session_prepared", row["replay_name"]))
    return {
        "replay_root": str(replay_root_path.resolve()),
        "memory_sessions_root": str(Path(memory_sessions_root).resolve()),
        "row_count": len(rows),
        "captured_count": sum(1 for row in rows if row["status"] == "captured"),
        "session_prepared_count": sum(1 for row in rows if row["status"] == "session_prepared"),
        "missing_session_count": sum(1 for row in rows if row["status"] == "missing_session"),
        "rows": rows,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build a full-corpus result-screen capture queue.")
    parser.add_argument("--replay-root", required=True, help="Root directory containing replay files")
    parser.add_argument("--memory-sessions-root", required=True, help="Existing memory sessions root")
    parser.add_argument("--create-missing-sessions", action="store_true", help="Create session manifests for missing replays")
    parser.add_argument("--session-output-root", help="Optional root to place newly created session manifests")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(argv)

    report = build_result_screen_capture_queue(
        args.replay_root,
        args.memory_sessions_root,
        create_missing_sessions=args.create_missing_sessions,
        session_output_root=args.session_output_root,
    )
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"Result-screen capture queue saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
