"""Build per-replay readiness status for result-screen KDA correction."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .result_screen_kda_correction_inventory import build_result_screen_kda_correction_inventory


def discover_session_dirs(memory_sessions_root: Path) -> List[Path]:
    return sorted(
        path.resolve()
        for path in memory_sessions_root.iterdir()
        if path.is_dir()
    )


def _load_json(path: Path) -> Optional[Dict[str, object]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _load_manifest_replay_name(session_dir: Path) -> Optional[str]:
    manifest_path = session_dir / "manifest.json"
    payload = _load_json(manifest_path) if manifest_path.exists() else None
    replay_name = payload.get("replay_name") if payload else None
    return str(replay_name) if replay_name else None


def _discover_result_dump(session_dir: Path) -> Optional[str]:
    candidates = sorted(session_dir.rglob("result_screen_full.dmp"))
    return str(candidates[0].resolve()) if candidates else None


def _discover_bundle(session_dir: Path) -> Optional[str]:
    candidates = sorted(session_dir.rglob("result_screen_kda_correction_merge.json"))
    return str(candidates[0].resolve()) if candidates else None


def _discover_decoded_payloads(output_root: Path) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for candidate in sorted(output_root.rglob("*.json")):
        payload = _load_json(candidate)
        if not payload:
            continue
        safe_output = payload.get("safe_output")
        if not isinstance(safe_output, dict):
            continue
        replay_name = safe_output.get("replay_name")
        if replay_name and replay_name not in mapping:
            mapping[str(replay_name)] = str(candidate.resolve())
    return mapping


def _discover_corrected_exports(output_root: Path) -> Dict[str, str]:
    preferred: Dict[str, str] = {}

    def score(path: Path) -> tuple[int, str]:
        name = path.name
        if "pipeline" in name:
            return (3, str(path))
        if "auto" in name:
            return (2, str(path))
        return (1, str(path))

    for candidate in sorted(output_root.rglob("*.json")):
        payload = _load_json(candidate)
        if not payload or payload.get("schema_version") != "decoder_v2.index_export.v2":
            continue
        matches = payload.get("matches")
        if not isinstance(matches, list):
            continue
        for match in matches:
            if not isinstance(match, dict):
                continue
            replay_name = match.get("replay_name")
            correction = match.get("kda_correction")
            if not replay_name or not isinstance(correction, dict) or not correction.get("applied"):
                continue
            key = str(replay_name)
            existing = preferred.get(key)
            if existing is None or score(candidate) > score(Path(existing)):
                preferred[key] = str(candidate.resolve())
    return preferred


def _status_rank(status: str) -> int:
    order = {
        "already_corrected_exported": 6,
        "ready_for_corrected_export": 5,
        "ready_for_inventory": 4,
        "ready_for_autobundle": 3,
        "missing_decoded_payload": 2,
        "missing_result_dump": 1,
        "missing_manifest_replay_name": 0,
    }
    return order.get(status, -1)


def build_result_screen_kda_correction_readiness(
    memory_sessions_root: str,
    output_root: str,
) -> Dict[str, object]:
    root = Path(memory_sessions_root)
    output_root_path = Path(output_root)
    inventory = build_result_screen_kda_correction_inventory(str(root))
    preferred_corrections = {
        str(entry["replay_name"]): str(entry["path"])
        for entry in inventory["preferred_entries"]
        if entry.get("replay_name")
    }
    decoded_payloads = _discover_decoded_payloads(output_root_path)
    corrected_exports = _discover_corrected_exports(output_root_path)

    rows: List[Dict[str, object]] = []
    seen_replays = set()

    for session_dir in discover_session_dirs(root):
        replay_name = _load_manifest_replay_name(session_dir)
        result_dump_path = _discover_result_dump(session_dir)
        bundle_path = _discover_bundle(session_dir)
        decoded_payload_path = decoded_payloads.get(replay_name) if replay_name else None
        preferred_correction_path = preferred_corrections.get(replay_name) if replay_name else None
        corrected_export_path = corrected_exports.get(replay_name) if replay_name else None

        if replay_name and corrected_export_path:
            status = "already_corrected_exported"
            blocking_reason = None
        elif replay_name and preferred_correction_path:
            status = "ready_for_corrected_export"
            blocking_reason = None
        elif replay_name and bundle_path:
            status = "ready_for_inventory"
            blocking_reason = None
        elif not result_dump_path:
            status = "missing_result_dump"
            blocking_reason = "Session has no result_screen_full.dmp."
        elif not replay_name:
            status = "missing_manifest_replay_name"
            blocking_reason = "Session manifest is missing replay_name."
        elif not decoded_payload_path:
            status = "missing_decoded_payload"
            blocking_reason = "No decoded debug payload found for replay_name."
        elif not bundle_path:
            status = "ready_for_autobundle"
            blocking_reason = None
        else:
            status = "ready_for_inventory"
            blocking_reason = None

        row = (
            {
                "replay_name": replay_name,
                "session_dir": str(session_dir),
                "result_dump_path": result_dump_path,
                "decoded_payload_path": decoded_payload_path,
                "preferred_correction_path": preferred_correction_path,
                "corrected_export_path": corrected_export_path,
                "has_result_dump": bool(result_dump_path),
                "has_bundle": bool(bundle_path),
                "has_corrected_export": bool(corrected_export_path),
                "status": status,
                "blocking_reason": blocking_reason,
            }
        )
        rows.append(row)
        if replay_name:
            seen_replays.add(replay_name)

    for replay_name, decoded_payload_path in sorted(decoded_payloads.items()):
        if replay_name in seen_replays:
            continue
        corrected_export_path = corrected_exports.get(replay_name)
        rows.append(
            {
                "replay_name": replay_name,
                "session_dir": None,
                "result_dump_path": None,
                "decoded_payload_path": decoded_payload_path,
                "preferred_correction_path": preferred_corrections.get(replay_name),
                "corrected_export_path": corrected_export_path,
                "has_result_dump": False,
                "has_bundle": False,
                "has_corrected_export": bool(corrected_export_path),
                "status": "already_corrected_exported" if corrected_export_path else "missing_result_dump",
                "blocking_reason": None if corrected_export_path else "Decoded payload exists but no result-screen dump is available.",
            }
        )

    grouped_rows: Dict[str, Dict[str, object]] = {}
    replay_rows: List[Dict[str, object]] = []
    nameless_rows: List[Dict[str, object]] = []
    for row in rows:
        replay_name = row.get("replay_name")
        if not replay_name:
            nameless_rows.append(row)
            continue
        replay_key = str(replay_name)
        existing = grouped_rows.get(replay_key)
        if existing is None or _status_rank(str(row["status"])) > _status_rank(str(existing["status"])):
            grouped_rows[replay_key] = row
    replay_rows.extend(grouped_rows.values())
    replay_rows.sort(key=lambda row: str(row["replay_name"]))
    nameless_rows.sort(key=lambda row: str(row["session_dir"]))
    final_rows = replay_rows + nameless_rows

    return {
        "memory_sessions_root": str(root.resolve()),
        "output_root": str(output_root_path.resolve()),
        "row_count": len(final_rows),
        "rows": final_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build result-screen KDA correction readiness report.")
    parser.add_argument("--memory-sessions-root", required=True, help="Memory sessions root")
    parser.add_argument("--output-root", default="vg/output", help="Output root")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args()

    report = build_result_screen_kda_correction_readiness(
        args.memory_sessions_root,
        args.output_root,
    )
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"Result-screen KDA correction readiness saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
