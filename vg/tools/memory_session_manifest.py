"""Create a session manifest for replay-state memory dump experiments."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List


DEFAULT_PHASES = [
    "menu_home",
    "replay_loaded_initial",
    "scoreboard_open",
    "scoreboard_closed",
    "result_screen",
]


def build_memory_session_manifest(
    session_root: str,
    replay_source_dir: str,
    replay_name: str,
    phases: List[str],
) -> Dict[str, object]:
    root = Path(session_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    dumps_dir = root / "dumps"
    dumps_dir.mkdir(exist_ok=True)
    screenshots_dir = root / "screenshots"
    screenshots_dir.mkdir(exist_ok=True)

    phase_rows = []
    for phase in phases:
        phase_rows.append(
            {
                "phase": phase,
                "screenshot_path": str((screenshots_dir / f"{phase}.png").resolve()),
                "dump_path": str((dumps_dir / f"{phase}.dmp").resolve()),
                "notes": "",
            }
        )

    return {
        "created_at": datetime.now().isoformat(),
        "session_root": str(root),
        "replay_source_dir": str(Path(replay_source_dir).resolve()),
        "replay_name": replay_name,
        "phases": phase_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a replay memory-dump session manifest.")
    parser.add_argument("--session-root", required=True, help="Session output root directory")
    parser.add_argument("--replay-source-dir", required=True, help="Replay source folder path")
    parser.add_argument("--replay-name", required=True, help="Replay name used by vgrplay")
    parser.add_argument(
        "--phases",
        nargs="*",
        default=DEFAULT_PHASES,
        help="Ordered capture phases",
    )
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args()

    manifest = build_memory_session_manifest(
        args.session_root,
        args.replay_source_dir,
        args.replay_name,
        list(args.phases),
    )
    payload = json.dumps(manifest, indent=2, ensure_ascii=False)
    output_path = Path(args.output) if args.output else Path(args.session_root) / "manifest.json"
    output_path.write_text(payload, encoding="utf-8")
    print(f"Memory session manifest saved to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
