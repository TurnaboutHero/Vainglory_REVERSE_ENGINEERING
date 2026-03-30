"""Build report/apply/merge correction artifacts from one decoded replay and one result-screen dump."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict

from .result_screen_kda_correction_apply import build_result_screen_kda_correction_apply
from .result_screen_kda_correction_merge import build_result_screen_kda_correction_merge
from .result_screen_kda_correction_report import (
    _load_expected_players,
    build_result_screen_kda_correction_report,
)


def build_result_screen_kda_correction_bundle(
    decoded_payload: Dict[str, object],
    dump_path: str,
) -> Dict[str, object]:
    expected_players = _load_expected_players_from_payload(decoded_payload)
    report = build_result_screen_kda_correction_report(dump_path, expected_players)
    apply_report = build_result_screen_kda_correction_apply(dump_path, expected_players)
    merged = build_result_screen_kda_correction_merge(decoded_payload, apply_report)
    return {
        "report": report,
        "apply": apply_report,
        "merge": merged,
    }


def _load_expected_players_from_payload(decoded_payload: Dict[str, object]):
    safe_output = decoded_payload.get("safe_output")
    if isinstance(safe_output, dict) and isinstance(safe_output.get("players"), list):
        return safe_output["players"]
    if isinstance(decoded_payload.get("players"), list):
        return decoded_payload["players"]
    raise ValueError("decoded payload must contain safe_output.players or players")


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build result-screen KDA correction report/apply/merge artifacts.")
    parser.add_argument("--decoded", required=True, help="Decoder debug JSON or player-row JSON")
    parser.add_argument("--dump", required=True, help="Result-screen full dump path")
    parser.add_argument("--output-dir", required=True, help="Directory to write bundle artifacts into")
    args = parser.parse_args()

    decoded_payload = json.loads(Path(args.decoded).read_text(encoding="utf-8"))
    bundle = build_result_screen_kda_correction_bundle(decoded_payload, args.dump)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "result_screen_kda_correction_report.json", bundle["report"])
    _write_json(output_dir / "result_screen_kda_correction_apply.json", bundle["apply"])
    _write_json(output_dir / "result_screen_kda_correction_merge.json", bundle["merge"])
    print(f"Result-screen KDA correction bundle saved to {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
