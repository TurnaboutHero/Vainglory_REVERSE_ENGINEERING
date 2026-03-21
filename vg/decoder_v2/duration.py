"""Conservative duration estimation for decoder_v2."""

from __future__ import annotations

from .completeness import assess_completeness, extract_replay_signals
from .models import CompletenessStatus, DurationEstimate, ReplaySignalSummary


def estimate_duration_from_signals(signals: ReplaySignalSummary) -> DurationEstimate:
    """Estimate replay duration conservatively from extracted signals."""
    assessment = assess_completeness(signals)

    if assessment.status == CompletenessStatus.INCOMPLETE_CONFIRMED:
        return DurationEstimate(
            estimate_seconds=None,
            source="unknown",
            assessment=assessment,
        )

    if (
        signals.crystal_ts is not None
        and signals.max_player_death_ts is not None
        and abs(signals.crystal_ts - signals.max_player_death_ts) <= 30
    ):
        return DurationEstimate(
            estimate_seconds=int(signals.crystal_ts),
            source="crystal",
            assessment=assessment,
        )

    if signals.max_player_death_ts is not None:
        return DurationEstimate(
            estimate_seconds=int(signals.max_player_death_ts),
            source="max_death",
            assessment=assessment,
        )

    return DurationEstimate(
        estimate_seconds=None,
        source="unknown",
        assessment=assessment,
    )


def estimate_duration(replay_file: str) -> DurationEstimate:
    """Convenience entrypoint to estimate duration directly from a replay path."""
    return estimate_duration_from_signals(extract_replay_signals(replay_file))
