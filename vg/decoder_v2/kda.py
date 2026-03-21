"""Conservative KDA decoding scaffold for decoder_v2."""

from __future__ import annotations

from typing import Dict

from vg.core.kda_detector import KDADetector
from vg.core.vgr_parser import VGRParser
from vg.core.unified_decoder import _le_to_be

from .completeness import extract_replay_signals
from .duration import estimate_duration_from_signals
from .models import CompletenessStatus, KDAExtractionResult, KDAPlayerSummary


def decode_kda_from_replay(replay_file: str) -> KDAExtractionResult:
    """Decode K/D/A conservatively. Reject incomplete replays by default."""
    signals = extract_replay_signals(replay_file)
    duration_estimate = estimate_duration_from_signals(signals)
    assessment = duration_estimate.assessment

    if assessment.status != CompletenessStatus.COMPLETE_CONFIRMED:
        return KDAExtractionResult(
            accepted=False,
            reason="Replay completeness is not confirmed; K/D/A export is withheld.",
            assessment=assessment,
            duration_estimate=duration_estimate,
            players=(),
        )

    parser = VGRParser(replay_file, auto_truth=False)
    parsed = parser.parse()

    player_map: Dict[int, Dict[str, object]] = {}
    team_map: Dict[int, str] = {}
    ordered_players = []
    for team_label in ("left", "right"):
        for player in parsed["teams"][team_label]:
            entity_id = player.get("entity_id")
            if not entity_id:
                continue
            entity_be = _le_to_be(entity_id)
            player_map[entity_be] = player
            team_map[entity_be] = team_label
            ordered_players.append((entity_be, player))

    detector = KDADetector(set(player_map))
    from .completeness import load_frames

    for frame_idx, data in load_frames(replay_file):
        detector.process_frame(frame_idx, data)

    results = detector.get_results(
        game_duration=duration_estimate.estimate_seconds,
        team_map=team_map,
    )

    players = tuple(
        KDAPlayerSummary(
            player_name=player["name"],
            team=player.get("team", team_map[entity_be]),
            hero_name=player.get("hero_name", "Unknown"),
            kills=results[entity_be].kills,
            deaths=results[entity_be].deaths,
            assists=results[entity_be].assists,
            minion_kills=results[entity_be].minion_kills,
        )
        for entity_be, player in ordered_players
    )

    return KDAExtractionResult(
        accepted=True,
        reason="Replay completeness is confirmed; K/D/A exported.",
        assessment=assessment,
        duration_estimate=duration_estimate,
        players=players,
    )
