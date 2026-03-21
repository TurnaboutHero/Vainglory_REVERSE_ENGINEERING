"""Fixture-backed validation helpers for decoder_v2 foundations."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

from vg.analysis.decode_tournament import _resolve_truth_player_name, run_validation
from vg.core.vgr_mapping import BINARY_HERO_ID_MAP, normalize_hero_name

from .completeness import assess_completeness, extract_replay_signals
from .duration import estimate_duration_from_signals
from .minions import compare_minion_candidates_to_truth
from .models import PlayerBlockValidationSummary
from .registry import DECODER_FIELD_STATUSES, EVENT_HEADER_CLAIMS, OFFSET_CLAIMS
from .player_blocks import parse_player_blocks
from .truth_inventory import build_truth_inventory


def load_truth_matches(truth_path: str) -> List[Dict]:
    """Load tournament truth matches."""
    data = json.loads(Path(truth_path).read_text(encoding="utf-8"))
    return data.get("matches", [])


def validate_player_block_claims(truth_path: str) -> PlayerBlockValidationSummary:
    """Validate direct player block claims against tournament truth fixtures."""
    matches = load_truth_matches(truth_path)
    summary = PlayerBlockValidationSummary(matches_total=len(matches))
    team_counter = Counter()

    for match in matches:
        replay_file = Path(match["replay_file"])
        data = replay_file.read_bytes()
        records = parse_player_blocks(data)
        summary.extracted_records_per_match[match["replay_name"]] = len(records)
        summary.records_total += len(records)

        for record in records:
            if record.entity_id_le:
                summary.entity_nonzero_records += 1
            if record.team_byte is not None:
                team_counter[record.team_byte] += 1

            truth_name = _resolve_truth_player_name(record.name, match["players"])
            truth_player = match["players"].get(truth_name) if truth_name else None
            hero_name = BINARY_HERO_ID_MAP.get(record.hero_id_le)
            if truth_player and hero_name:
                summary.hero_total += 1
                if normalize_hero_name(hero_name) == normalize_hero_name(truth_player["hero_name"]):
                    summary.hero_matches += 1
                else:
                    summary.mismatches.append(
                        {
                            "match": match["replay_name"],
                            "player": record.name,
                            "truth_name": truth_name,
                            "hero_id_le": record.hero_id_le,
                            "decoded_hero": hero_name,
                            "truth_hero": truth_player["hero_name"],
                        }
                    )

    summary.team_bytes_seen = dict(team_counter)
    return summary


def build_foundation_report(truth_path: str) -> Dict[str, object]:
    """Build a combined registry + fixture-backed validation report."""
    player_block_summary = validate_player_block_claims(truth_path)
    decoder_summary = run_validation(truth_path, verbose=False)
    truth_matches = load_truth_matches(truth_path)
    completeness_rows = []
    for match in truth_matches:
        signals = extract_replay_signals(match["replay_file"])
        assessment = assess_completeness(signals)
        duration_estimate = estimate_duration_from_signals(signals)
        completeness_rows.append(
            {
                "replay_name": match["replay_name"],
                "truth_duration": match["match_info"].get("duration_seconds"),
                "truth_winner": match["match_info"].get("winner"),
                "fixture_directory": str(Path(match["replay_file"]).parent.name),
                "assessment": assessment.to_dict(),
                "duration_estimate": duration_estimate.to_dict(),
            }
        )

    minion_probes = []
    for index in (5, 8):
        if index < len(truth_matches):
            probe_match = truth_matches[index]
            minion_probes.append(
                {
                    "fixture_index": index + 1,
                    "fixture_directory": Path(probe_match["replay_file"]).parent.name,
                    "probe": compare_minion_candidates_to_truth(probe_match["replay_file"], truth_path),
                }
            )

    replay_base = Path(r"D:\Desktop\My Folder\Game\VG\vg replay")
    truth_inventory = (
        build_truth_inventory(str(replay_base), truth_path)
        if replay_base.exists()
        else None
    )

    return {
        "truth_path": str(Path(truth_path).resolve()),
        "offset_claims": [claim.to_dict() for claim in OFFSET_CLAIMS],
        "event_header_claims": [claim.to_dict() for claim in EVENT_HEADER_CLAIMS],
        "decoder_field_statuses": [item.to_dict() for item in DECODER_FIELD_STATUSES],
        "player_block_validation": player_block_summary.to_dict(),
        "current_decoder_validation": decoder_summary,
        "completeness_validation": completeness_rows,
        "minion_candidate_probes": minion_probes,
        "truth_inventory": truth_inventory,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build decoder_v2 foundation validation report.")
    parser.add_argument(
        "--truth",
        default="vg/output/tournament_truth.json",
        help="Path to tournament truth JSON",
    )
    parser.add_argument(
        "--output",
        help="Optional JSON output path",
    )
    args = parser.parse_args(argv)

    report = build_foundation_report(args.truth)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Foundation report saved to {output_path}")
    else:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
