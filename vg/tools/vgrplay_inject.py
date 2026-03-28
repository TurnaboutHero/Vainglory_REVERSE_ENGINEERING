"""Inject a source replay into the live temp replay slot using vgrplay."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


DEFAULT_VGRPLAY = (
    r"D:\Desktop\My Folder\Game\VG\vg replay\vaingloryreplay-master\windows_amd64\vgrplay.exe"
)


def find_live_temp_replay(temp_dir: str) -> Dict[str, object]:
    files = sorted(
        Path(temp_dir).glob("*.vgr"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    if not files:
        raise FileNotFoundError(f"No .vgr files found under temp dir: {temp_dir}")
    latest = files[0]
    oname = latest.stem.rsplit(".", 1)[0]
    return {
        "latest_file": str(latest.resolve()),
        "oname": oname,
        "latest_mtime": latest.stat().st_mtime,
    }


def inject_replay_with_vgrplay(
    source_dir: str,
    replay_name: str,
    temp_dir: str,
    vgrplay_path: str = DEFAULT_VGRPLAY,
) -> Dict[str, object]:
    live = find_live_temp_replay(temp_dir)
    before_files = {
        path.name: path.stat().st_mtime
        for path in Path(temp_dir).glob(f"{live['oname']}.*.vgr")
    }

    cmd = [
        vgrplay_path,
        "-source",
        source_dir,
        "-sname",
        replay_name,
        "-overwrite",
        temp_dir,
        "-oname",
        str(live["oname"]),
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True)

    after_files = {
        path.name: path.stat().st_mtime
        for path in Path(temp_dir).glob(f"{live['oname']}.*.vgr")
    }
    changed = sorted(
        name for name, mtime in after_files.items()
        if name not in before_files or before_files[name] != mtime
    )

    return {
        "captured_at": datetime.now().isoformat(),
        "command": cmd,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "source_dir": str(Path(source_dir).resolve()),
        "replay_name": replay_name,
        "temp_dir": str(Path(temp_dir).resolve()),
        "live_replay": live,
        "changed_files": changed,
        "changed_count": len(changed),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inject a replay into the current temp replay slot via vgrplay.")
    parser.add_argument("--source-dir", required=True, help="Replay source directory")
    parser.add_argument("--replay-name", required=True, help="Replay name used by vgrplay -sname")
    parser.add_argument("--temp-dir", default=str(Path.home() / "AppData" / "Local" / "Temp"), help="Temp replay directory")
    parser.add_argument("--vgrplay", default=DEFAULT_VGRPLAY, help="Path to vgrplay.exe")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args()

    report = inject_replay_with_vgrplay(
        source_dir=args.source_dir,
        replay_name=args.replay_name,
        temp_dir=args.temp_dir,
        vgrplay_path=args.vgrplay,
    )
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"vgrplay injection report saved to {args.output}")
    else:
        print(payload)
    return 0 if report["returncode"] == 0 else report["returncode"]


if __name__ == "__main__":
    raise SystemExit(main())
