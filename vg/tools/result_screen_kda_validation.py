"""Validate captured result-screen KDA corrections against truth or correction reference."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from vg.analysis.decode_tournament import _resolve_truth_player_name
from vg.decoder_v2.kda_postgame_audit import _load_truth_matches

from .result_screen_kda_correction_inventory import build_result_screen_kda_correction_inventory
from .result_screen_kda_correction_readiness import _discover_decoded_payloads


def _player_kda(player: Dict[str, object]) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    return player.get("kills"), player.get("deaths"), player.get("assists")


def build_result_screen_kda_validation(
    memory_sessions_root: str,
    output_root: str,
    truth_path: str,
) -> Dict[str, object]:
    root = Path(memory_sessions_root)
    output_root_path = Path(output_root)
    inventory = build_result_screen_kda_correction_inventory(str(root))
    decoded_payloads = _discover_decoded_payloads(output_root_path)
    truth_matches = {
        str(match["replay_name"]): match for match in _load_truth_matches(truth_path)
    }

    rows = []
    for entry in inventory["preferred_entries"]:
        replay_name = str(entry["replay_name"])
        decoded_path = decoded_payloads.get(replay_name)
        if not decoded_path:
            rows.append(
                {
                    "replay_name": replay_name,
                    "status": "missing_decoded_payload",
                }
            )
            continue

        decoded_payload = json.loads(Path(decoded_path).read_text(encoding="utf-8"))
        correction_payload = json.loads(Path(entry["path"]).read_text(encoding="utf-8"))
        decoded_players = decoded_payload["safe_output"]["players"]
        corrected_players = {player["name"]: player for player in correction_payload["players"]}

        truth_match = truth_matches.get(replay_name)
        reference_source = "truth" if truth_match else "result_screen"
        baseline_correct_rows = 0
        corrected_correct_rows = 0
        rows_improved = 0
        rows_regressed = 0
        rows_unchanged = 0
        total_rows = 0

        for player in decoded_players:
            total_rows += 1
            name = player["name"]
            baseline_kda = _player_kda(player)
            corrected_kda = _player_kda(corrected_players[name]) if name in corrected_players else baseline_kda
            if truth_match:
                truth_name = _resolve_truth_player_name(name, truth_match["players"])
                truth_player = truth_match["players"][truth_name] if truth_name else {}
                reference_kda = (
                    truth_player.get("kills"),
                    truth_player.get("deaths"),
                    truth_player.get("assists"),
                )
            else:
                reference_kda = corrected_kda

            baseline_correct = baseline_kda == reference_kda
            corrected_correct = corrected_kda == reference_kda
            baseline_correct_rows += int(baseline_correct)
            corrected_correct_rows += int(corrected_correct)
            if not baseline_correct and corrected_correct:
                rows_improved += 1
            elif baseline_correct and not corrected_correct:
                rows_regressed += 1
            else:
                rows_unchanged += 1

        rows.append(
            {
                "replay_name": replay_name,
                "reference_source": reference_source,
                "baseline_correct_rows": baseline_correct_rows,
                "corrected_correct_rows": corrected_correct_rows,
                "rows_improved": rows_improved,
                "rows_unchanged": rows_unchanged,
                "rows_regressed": rows_regressed,
                "total_rows": total_rows,
                "status": "needs_review" if rows_regressed else "validated_non_regression",
            }
        )

    return {
        "memory_sessions_root": str(root.resolve()),
        "output_root": str(output_root_path.resolve()),
        "truth_path": str(Path(truth_path).resolve()),
        "row_count": len(rows),
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate result-screen KDA correction artifacts.")
    parser.add_argument("--memory-sessions-root", required=True, help="Memory sessions root")
    parser.add_argument("--output-root", default="vg/output", help="Output root")
    parser.add_argument("--truth", default="vg/output/tournament_truth.json", help="Truth JSON path")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args()

    report = build_result_screen_kda_validation(
        args.memory_sessions_root,
        args.output_root,
        args.truth,
    )
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"Result-screen KDA validation saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
