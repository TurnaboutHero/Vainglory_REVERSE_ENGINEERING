"""Conservative winner decoding scaffold for decoder_v2."""

from __future__ import annotations

from .kda import decode_kda_from_replay
from .models import WinnerExtractionResult


def decode_winner_from_replay(replay_file: str) -> WinnerExtractionResult:
    """Decode winner conservatively from gated K/D/A output."""
    kda_result = decode_kda_from_replay(replay_file)
    if not kda_result.accepted:
        return WinnerExtractionResult(
            accepted=False,
            reason="Replay completeness is not confirmed; winner export is withheld.",
            assessment=kda_result.assessment,
            duration_estimate=kda_result.duration_estimate,
            winner=None,
            left_kills=None,
            right_kills=None,
        )

    left_kills = sum(player.kills for player in kda_result.players if player.team == "left")
    right_kills = sum(player.kills for player in kda_result.players if player.team == "right")
    winner = None
    if left_kills > right_kills:
        winner = "left"
    elif right_kills > left_kills:
        winner = "right"

    return WinnerExtractionResult(
        accepted=winner is not None,
        reason="Winner derived from K/D kill asymmetry on a completeness-confirmed replay." if winner else "Winner tie or unavailable.",
        assessment=kda_result.assessment,
        duration_estimate=kda_result.duration_estimate,
        winner=winner,
        left_kills=left_kills,
        right_kills=right_kills,
    )
