"""Inventory result-screen KDA correction artifacts under a directory tree."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple


def _source_rank(path: Path) -> int:
    parent_name = path.parent.name
    if parent_name == "autobundle_auto":
        return 3
    if parent_name.startswith("autobundle"):
        return 2
    if parent_name == "bundle":
        return 1
    return 0


def _correction_priority(entry: Dict[str, object]) -> Tuple[int, int, int, int, str]:
    name = str(entry.get("name", ""))
    if name == "result_screen_kda_correction_merge.json":
        kind_rank = 3
    elif name == "target_replay_corrected_kda_rows.json":
        kind_rank = 2
    else:
        kind_rank = 1

    source_rank = _source_rank(Path(str(entry.get("path", ""))))
    corrected_rows = int(entry.get("corrected_rows") or 0)
    unresolved_rows = int(entry.get("unresolved_rows") or 0)
    return (kind_rank, source_rank, corrected_rows, -unresolved_rows, str(entry.get("path", "")))


def build_result_screen_kda_correction_inventory(root_path: str) -> Dict[str, object]:
    root = Path(root_path)
    entries: List[Dict[str, object]] = []
    for path in sorted(root.rglob("*.json")):
        payload = None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        if not isinstance(payload.get("players"), list):
            continue
        replay_name = payload.get("replay_name")
        replay_file = payload.get("replay_file")
        corrected_rows = payload.get("corrected_rows")
        unresolved_rows = payload.get("unresolved_rows")
        if (
            path.name not in {"result_screen_kda_correction_merge.json", "target_replay_corrected_kda_rows.json"}
            and corrected_rows is None
            and unresolved_rows is None
        ):
            continue
        entries.append(
            {
                "path": str(path.resolve()),
                "name": path.name,
                "replay_name": replay_name,
                "replay_file": replay_file,
                "corrected_rows": corrected_rows,
                "unresolved_rows": unresolved_rows,
            }
        )

    preferred_by_replay: Dict[str, Dict[str, object]] = {}
    for entry in entries:
        replay_key = str(entry.get("replay_name") or entry.get("replay_file") or "")
        if not replay_key:
            continue
        existing = preferred_by_replay.get(replay_key)
        if existing is None or _correction_priority(entry) > _correction_priority(existing):
            preferred_by_replay[replay_key] = entry

    return {
        "root_path": str(root.resolve()),
        "correction_file_count": len(entries),
        "entries": entries,
        "preferred_correction_count": len(preferred_by_replay),
        "preferred_entries": list(preferred_by_replay.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory result-screen KDA correction artifacts.")
    parser.add_argument("root_path", help="Root directory to scan recursively")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args()

    report = build_result_screen_kda_correction_inventory(args.root_path)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"Result-screen KDA correction inventory saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
