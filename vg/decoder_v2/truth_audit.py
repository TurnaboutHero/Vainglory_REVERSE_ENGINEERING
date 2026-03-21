"""Audit truth quality by comparing OCR, current truth, and decoder_v2 output."""

from __future__ import annotations

import argparse
import difflib
import json
from pathlib import Path
from typing import Dict, List, Optional

from .decode_match import decode_match


def _load_matches(path: str) -> Dict[str, Dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {match["replay_name"]: match for match in data.get("matches", [])}


def _resolve_name(name: str, players: Dict[str, Dict]) -> Optional[str]:
    if name in players:
        return name
    lower_map = {key.lower(): key for key in players}
    if name.lower() in lower_map:
        return lower_map[name.lower()]
    prefix = name.split("_", 1)[0]
    candidates = [key for key in players if key.split("_", 1)[0] == prefix]
    if not candidates:
        return None
    matches = difflib.get_close_matches(name, candidates, n=1, cutoff=0.80)
    return matches[0] if matches else None


def audit_truth(
    truth_path: str,
    ocr_truth_path: str,
) -> Dict[str, object]:
    truth_matches = _load_matches(truth_path)
    ocr_matches = _load_matches(ocr_truth_path)
    replay_names = sorted(set(truth_matches) & set(ocr_matches))

    report_rows = []
    summary = {
        "score_mismatch_matches": 0,
        "duration_mismatch_matches": 0,
        "player_rows": 0,
        "mk_mismatches": 0,
        "kill_mismatches": 0,
        "death_mismatches": 0,
        "assist_mismatches": 0,
    }
    for replay_name in replay_names:
        truth_match = truth_matches[replay_name]
        ocr_match = ocr_matches[replay_name]
        safe = decode_match(truth_match["replay_file"]).to_dict()

        if (
            truth_match.get("match_info", {}).get("score_left") != ocr_match.get("match_info", {}).get("score_left")
            or truth_match.get("match_info", {}).get("score_right") != ocr_match.get("match_info", {}).get("score_right")
        ):
            summary["score_mismatch_matches"] += 1
        if (
            truth_match.get("match_info", {}).get("duration_seconds")
            != ocr_match.get("match_info", {}).get("duration_seconds")
        ):
            summary["duration_mismatch_matches"] += 1

        player_rows = []
        for player in safe["players"]:
            truth_name = _resolve_name(player["name"], truth_match["players"])
            ocr_name = _resolve_name(player["name"], ocr_match["players"])
            truth_player = truth_match["players"].get(truth_name) if truth_name else None
            ocr_player = ocr_match["players"].get(ocr_name) if ocr_name else None
            summary["player_rows"] += 1
            if (truth_player.get("minion_kills") if truth_player else None) != (ocr_player.get("minion_kills") if ocr_player else None):
                summary["mk_mismatches"] += 1
            if (truth_player.get("kills") if truth_player else None) != (ocr_player.get("kills") if ocr_player else None):
                summary["kill_mismatches"] += 1
            if (truth_player.get("deaths") if truth_player else None) != (ocr_player.get("deaths") if ocr_player else None):
                summary["death_mismatches"] += 1
            if (truth_player.get("assists") if truth_player else None) != (ocr_player.get("assists") if ocr_player else None):
                summary["assist_mismatches"] += 1

            player_rows.append(
                {
                    "decoder_name": player["name"],
                    "truth_name": truth_name,
                    "ocr_name": ocr_name,
                    "decoder_hero": player["hero_name"],
                    "truth_hero": truth_player.get("hero_name") if truth_player else None,
                    "ocr_hero": ocr_player.get("hero_name") if ocr_player else None,
                    "truth_minion_kills": truth_player.get("minion_kills") if truth_player else None,
                    "ocr_minion_kills": ocr_player.get("minion_kills") if ocr_player else None,
                    "truth_kills": truth_player.get("kills") if truth_player else None,
                    "ocr_kills": ocr_player.get("kills") if ocr_player else None,
                    "truth_deaths": truth_player.get("deaths") if truth_player else None,
                    "ocr_deaths": ocr_player.get("deaths") if ocr_player else None,
                    "truth_assists": truth_player.get("assists") if truth_player else None,
                    "ocr_assists": ocr_player.get("assists") if ocr_player else None,
                }
            )

        report_rows.append(
            {
                "replay_name": replay_name,
                "result_image": truth_match.get("result_image"),
                "truth_match_info": truth_match.get("match_info", {}),
                "ocr_match_info": ocr_match.get("match_info", {}),
                "safe_output_summary": {
                    "completeness_status": safe["completeness_status"],
                    "accepted_fields": list(safe["accepted_fields"].keys()),
                    "withheld_fields": list(safe["withheld_fields"].keys()),
                },
                "players": player_rows,
            }
        )

    return {
        "truth_path": str(Path(truth_path).resolve()),
        "ocr_truth_path": str(Path(ocr_truth_path).resolve()),
        "audited_matches": len(report_rows),
        "summary": summary,
        "matches": report_rows,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Audit truth quality against OCR output and decoder_v2 safe output.")
    parser.add_argument("--truth", default="vg/output/tournament_truth.json", help="Truth JSON path")
    parser.add_argument("--ocr", required=True, help="OCR-derived truth JSON path")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(argv)

    report = audit_truth(args.truth, args.ocr)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Truth audit saved to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
