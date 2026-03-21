"""Conservative match export for decoder_v2."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

from vg.core.vgr_parser import VGRParser

from .kda import decode_kda_from_replay
from .minions import collect_minion_candidates
from .models import AcceptedPlayerFields, DecoderV2MatchOutput, FieldDecision
from .winner import decode_winner_from_replay


def decode_match(replay_file: str) -> DecoderV2MatchOutput:
    """Decode a replay conservatively, only exporting accepted fields."""
    parser = VGRParser(replay_file, auto_truth=False)
    parsed = parser.parse()
    match_info = parsed["match_info"]

    winner_result = decode_winner_from_replay(replay_file)
    kda_result = decode_kda_from_replay(replay_file)
    assessment = winner_result.assessment

    players: List[AcceptedPlayerFields] = []
    if kda_result.accepted:
        kda_by_name = {player.player_name: player for player in kda_result.players}
    else:
        kda_by_name = {}

    for team_label in ("left", "right"):
        for player in parsed["teams"][team_label]:
            accepted = AcceptedPlayerFields(
                name=player["name"],
                team=player.get("team", team_label),
                entity_id=player.get("entity_id"),
                hero_name=player.get("hero_name", "Unknown"),
                kills=kda_by_name.get(player["name"]).kills if player["name"] in kda_by_name else None,
                deaths=kda_by_name.get(player["name"]).deaths if player["name"] in kda_by_name else None,
                assists=kda_by_name.get(player["name"]).assists if player["name"] in kda_by_name else None,
            )
            players.append(accepted)

    accepted_fields: Dict[str, FieldDecision] = {
        "hero": FieldDecision(
            value="accepted",
            claim_status="confirmed",
            accepted_for_index=True,
            claim_id="player_block.hero_id",
        ),
        "team_grouping": FieldDecision(
            value="accepted",
            claim_status="confirmed",
            accepted_for_index=True,
            claim_id="player_block.team_byte",
        ),
        "entity_id": FieldDecision(
            value="accepted",
            claim_status="confirmed",
            accepted_for_index=True,
            claim_id="player_block.entity_id",
        ),
    }
    withheld_fields: Dict[str, FieldDecision] = {
        "minion_kills": FieldDecision(
            value=None,
            claim_status="partial",
            accepted_for_index=False,
            claim_id="minion_kills.complete_match",
            reason="Withheld: field is still partial in decoder_v2.",
        ),
        "duration_seconds": FieldDecision(
            value=winner_result.duration_estimate.estimate_seconds,
            claim_status="partial",
            accepted_for_index=False,
            claim_id="duration.approximate",
            reason="Withheld: duration is still approximate in decoder_v2.",
        ),
    }

    if winner_result.accepted and winner_result.winner is not None:
        accepted_fields["winner"] = FieldDecision(
            value=winner_result.winner,
            claim_status="strong",
            accepted_for_index=True,
            claim_id="winner.complete_match",
        )
    else:
        withheld_fields["winner"] = FieldDecision(
            value=winner_result.winner,
            claim_status="strong",
            accepted_for_index=False,
            claim_id="winner.complete_match",
            reason=winner_result.reason,
        )

    if kda_result.accepted:
        accepted_fields["kills"] = FieldDecision(
            value="accepted",
            claim_status="strong",
            accepted_for_index=True,
            claim_id="kills.complete_match",
        )
        accepted_fields["deaths"] = FieldDecision(
            value="accepted",
            claim_status="strong",
            accepted_for_index=True,
            claim_id="deaths.complete_match",
        )
        accepted_fields["assists"] = FieldDecision(
            value="accepted",
            claim_status="strong",
            accepted_for_index=True,
            claim_id="assists.complete_match",
        )
    else:
        withheld_fields["kills"] = FieldDecision(
            value=None,
            claim_status="strong",
            accepted_for_index=False,
            claim_id="kills.complete_match",
            reason=kda_result.reason,
        )
        withheld_fields["deaths"] = FieldDecision(
            value=None,
            claim_status="strong",
            accepted_for_index=False,
            claim_id="deaths.complete_match",
            reason=kda_result.reason,
        )
        withheld_fields["assists"] = FieldDecision(
            value=None,
            claim_status="strong",
            accepted_for_index=False,
            claim_id="assists.complete_match",
            reason=kda_result.reason,
        )

    return DecoderV2MatchOutput(
        schema_version="decoder_v2.match.v1",
        replay_name=parsed["replay_name"],
        replay_file=parsed["replay_file"],
        game_mode=match_info["mode"],
        map_name=match_info["map_name"],
        team_size=match_info["team_size"],
        completeness_status=assessment.status.value,
        completeness_reason=assessment.reason,
        accepted_fields=accepted_fields,
        withheld_fields=withheld_fields,
        players=tuple(players),
    )


def decode_match_debug(replay_file: str) -> Dict[str, object]:
    """Decode a replay with research/debug details included."""
    safe_output = decode_match(replay_file)
    winner_result = decode_winner_from_replay(replay_file)
    kda_result = decode_kda_from_replay(replay_file)
    minion_candidates = collect_minion_candidates(replay_file)

    return {
        "schema_version": "decoder_v2.debug_match.v1",
        "safe_output": safe_output.to_dict(),
        "completeness": winner_result.assessment.to_dict(),
        "duration": winner_result.duration_estimate.to_dict(),
        "winner_debug": winner_result.to_dict(),
        "kda_debug": kda_result.to_dict(),
        "minion_candidates": [item.to_dict() for item in minion_candidates],
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Decode one replay conservatively with decoder_v2.")
    parser.add_argument("replay_file", help="Path to .0.vgr replay file")
    parser.add_argument(
        "--format",
        choices=("safe-json", "debug-json"),
        default="safe-json",
        help="Output format",
    )
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(argv)

    if args.format == "debug-json":
        payload_obj = decode_match_debug(args.replay_file)
    else:
        payload_obj = decode_match(args.replay_file).to_dict()

    payload = json.dumps(payload_obj, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"decoder_v2 output saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
