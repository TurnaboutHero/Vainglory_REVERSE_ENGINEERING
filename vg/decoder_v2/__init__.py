"""Foundations for a protocol-driven VGR decoder v2."""

from .models import (
    ClaimStatus,
    CompletenessAssessment,
    CompletenessStatus,
    DecoderFieldStatus,
    DurationEstimate,
    EventHeaderClaim,
    MinionCandidateSummary,
    OffsetClaim,
    PlayerBlockRecord,
    ReplaySignalSummary,
    ValidationEvidence,
)
from .completeness import assess_completeness, extract_replay_signals, load_frames
from .duration import estimate_duration, estimate_duration_from_signals
from .manifest import parse_replay_manifest
from .minions import collect_minion_candidates, compare_minion_candidates_to_truth
from .kda import decode_kda_from_replay
from .credit_events import collect_credit_events_by_entity, iter_credit_events
from .player_events import collect_player_events_by_entity, iter_player_events
from .player_blocks import iter_player_blocks, parse_player_blocks
from .registry import DECODER_FIELD_STATUSES, EVENT_HEADER_CLAIMS, OFFSET_CLAIMS
from .winner import decode_winner_from_replay

__all__ = [
    "ClaimStatus",
    "CompletenessAssessment",
    "CompletenessStatus",
    "DecoderFieldStatus",
    "DurationEstimate",
    "EventHeaderClaim",
    "MinionCandidateSummary",
    "OffsetClaim",
    "PlayerBlockRecord",
    "ReplaySignalSummary",
    "ValidationEvidence",
    "assess_completeness",
    "extract_replay_signals",
    "load_frames",
    "estimate_duration",
    "estimate_duration_from_signals",
    "parse_replay_manifest",
    "iter_credit_events",
    "collect_credit_events_by_entity",
    "collect_minion_candidates",
    "compare_minion_candidates_to_truth",
    "decode_kda_from_replay",
    "decode_winner_from_replay",
    "iter_player_events",
    "collect_player_events_by_entity",
    "iter_player_blocks",
    "parse_player_blocks",
    "DECODER_FIELD_STATUSES",
    "EVENT_HEADER_CLAIMS",
    "OFFSET_CLAIMS",
]
