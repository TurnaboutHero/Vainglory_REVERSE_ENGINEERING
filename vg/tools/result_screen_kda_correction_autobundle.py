"""Auto-build a result-screen KDA correction bundle from a memory-session directory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Optional, Tuple

from .result_screen_kda_correction_bundle import build_result_screen_kda_correction_bundle


def _find_result_dump(session_dir: Path) -> Path:
    candidates = sorted(session_dir.rglob("result_screen_full.dmp"))
    if not candidates:
        raise FileNotFoundError(f"No result_screen_full.dmp under {session_dir}")
    return candidates[0]


def _load_replay_name(session_dir: Path) -> Optional[str]:
    manifest = session_dir / "manifest.json"
    if manifest.exists():
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception:
            payload = None
        if isinstance(payload, dict):
            replay_name = payload.get("replay_name")
            if replay_name:
                return str(replay_name)

    merge_candidates = sorted(session_dir.rglob("result_screen_kda_correction_merge.json"))
    for candidate in merge_candidates:
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict) and payload.get("replay_name"):
            return str(payload["replay_name"])
    return None


def _decoded_candidate_priority(path: Path, payload: Dict[str, object]) -> Tuple[int, str]:
    if isinstance(payload.get("safe_output"), dict):
        return (3, str(path))
    if path.name == "result_screen_kda_correction_merge.json":
        return (1, str(path))
    return (2, str(path))


def _find_decoded_payload_path(output_root: Path, replay_name: str) -> Path:
    candidates = sorted(output_root.rglob("*.json"))
    matched: list[tuple[Tuple[int, str], Path]] = []
    for candidate in candidates:
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        safe_output = payload.get("safe_output")
        if isinstance(safe_output, dict) and safe_output.get("replay_name") == replay_name:
            matched.append((_decoded_candidate_priority(candidate, payload), candidate))
            continue
        if payload.get("replay_name") == replay_name and isinstance(payload.get("players"), list):
            matched.append((_decoded_candidate_priority(candidate, payload), candidate))
    if matched:
        matched.sort(key=lambda item: item[0], reverse=True)
        return matched[0][1]
    raise FileNotFoundError(f"No decoded payload found for replay_name={replay_name}")


def build_result_screen_kda_correction_autobundle(
    session_dir: str,
    output_root: str,
    *,
    replay_name: Optional[str] = None,
) -> Dict[str, object]:
    session_path = Path(session_dir)
    output_root_path = Path(output_root)
    resolved_replay_name = replay_name or _load_replay_name(session_path)
    if not resolved_replay_name:
        raise ValueError("Could not infer replay_name; pass --replay-name explicitly")

    dump_path = _find_result_dump(session_path)
    decoded_path = _find_decoded_payload_path(output_root_path, resolved_replay_name)
    decoded_payload = json.loads(decoded_path.read_text(encoding="utf-8"))
    bundle = build_result_screen_kda_correction_bundle(decoded_payload, str(dump_path))
    bundle["meta"] = {
        "session_dir": str(session_path.resolve()),
        "output_root": str(output_root_path.resolve()),
        "decoded_path": str(decoded_path.resolve()),
        "dump_path": str(dump_path.resolve()),
        "replay_name": resolved_replay_name,
    }
    return bundle


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-build a result-screen KDA correction bundle from a session dir.")
    parser.add_argument("--session-dir", required=True, help="Memory-session directory")
    parser.add_argument("--output-root", default="vg/output", help="Output root containing decoded debug payloads")
    parser.add_argument("--replay-name", help="Optional replay_name override")
    parser.add_argument("--output-dir", help="Optional bundle output directory (default: <session-dir>/bundle)")
    args = parser.parse_args()

    bundle = build_result_screen_kda_correction_autobundle(
        args.session_dir,
        args.output_root,
        replay_name=args.replay_name,
    )

    output_dir = Path(args.output_dir) if args.output_dir else Path(args.session_dir) / "bundle"
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "result_screen_kda_correction_report.json", bundle["report"])
    _write_json(output_dir / "result_screen_kda_correction_apply.json", bundle["apply"])
    _write_json(output_dir / "result_screen_kda_correction_merge.json", bundle["merge"])
    _write_json(output_dir / "result_screen_kda_correction_meta.json", bundle["meta"])
    print(f"Result-screen KDA autobundle saved to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
