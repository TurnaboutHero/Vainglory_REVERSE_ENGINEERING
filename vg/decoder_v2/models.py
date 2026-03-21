"""Data models for decoder_v2 protocol claims and evidence."""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class ClaimStatus(str, Enum):
    CONFIRMED = "confirmed"
    STRONG = "strong"
    PARTIAL = "partial"
    DISPUTED = "disputed"
    UNKNOWN = "unknown"


class CompletenessStatus(str, Enum):
    COMPLETE_CONFIRMED = "complete_confirmed"
    INCOMPLETE_CONFIRMED = "incomplete_confirmed"
    COMPLETENESS_UNKNOWN = "completeness_unknown"


@dataclass(frozen=True)
class ValidationEvidence:
    """Evidence reference supporting a registry claim."""

    source_type: str
    reference: str
    summary: str

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class OffsetClaim:
    """Claim about a fixed byte offset inside a known structure."""

    claim_id: str
    structure: str
    offset: int
    value_type: str
    endian: str
    meaning: str
    status: ClaimStatus
    evidence: Tuple[ValidationEvidence, ...] = ()
    notes: str = ""

    def to_dict(self) -> Dict[str, object]:
        result = asdict(self)
        result["status"] = self.status.value
        result["evidence"] = [item.to_dict() for item in self.evidence]
        return result


@dataclass(frozen=True)
class EventHeaderClaim:
    """Claim about an event header and its payload structure."""

    claim_id: str
    header_hex: str
    structure: str
    entity_offset: Optional[int]
    entity_endian: Optional[str]
    timestamp_offset: Optional[int]
    timestamp_endian: Optional[str]
    meaning: str
    status: ClaimStatus
    evidence: Tuple[ValidationEvidence, ...] = ()
    notes: str = ""

    def to_dict(self) -> Dict[str, object]:
        result = asdict(self)
        result["status"] = self.status.value
        result["evidence"] = [item.to_dict() for item in self.evidence]
        return result


@dataclass(frozen=True)
class DecoderFieldStatus:
    """Production-readiness status for a decoded field."""

    field_name: str
    status: ClaimStatus
    source_kind: str
    rationale: str

    def to_dict(self) -> Dict[str, str]:
        result = asdict(self)
        result["status"] = self.status.value
        return result


@dataclass(frozen=True)
class PlayerBlockRecord:
    """Direct byte-level extraction from a player block marker."""

    name: str
    marker_offset: int
    marker_hex: str
    entity_id_le: Optional[int]
    hero_id_le: Optional[int]
    hero_hash_hex: Optional[str]
    team_byte: Optional[int]

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass
class PlayerBlockValidationSummary:
    """Fixture-backed summary for player block validation."""

    matches_total: int = 0
    records_total: int = 0
    hero_matches: int = 0
    hero_total: int = 0
    team_bytes_seen: Dict[int, int] = field(default_factory=dict)
    entity_nonzero_records: int = 0
    extracted_records_per_match: Dict[str, int] = field(default_factory=dict)
    mismatches: List[Dict[str, object]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ReplaySignalSummary:
    """Low-level timing and completeness signals extracted from a replay."""

    replay_name: str
    replay_file: str
    frame_count: int
    max_frame_index: int
    crystal_ts: Optional[float]
    max_kill_ts: Optional[float]
    max_player_death_ts: Optional[float]
    max_death_header_ts: Optional[float]
    max_item_ts: Optional[float]

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CreditEventRecord:
    """Raw credit-event record from `[10 04 1D]` family."""

    frame_idx: int
    entity_id_be: int
    action: int
    value: Optional[float]
    file_offset: int
    raw_record_hex: str
    padding_ok: bool
    value_is_finite: bool

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PlayerEventRecord:
    """Raw player-scoped event record from the LE event stream."""

    frame_idx: int
    entity_id_le: int
    action: int
    payload_hex: str

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CompletenessAssessment:
    """Conservative replay completeness classification."""

    status: CompletenessStatus
    reason: str
    signals: ReplaySignalSummary

    def to_dict(self) -> Dict[str, object]:
        result = asdict(self)
        result["status"] = self.status.value
        result["signals"] = self.signals.to_dict()
        return result


@dataclass(frozen=True)
class DurationEstimate:
    """Conservative duration estimate with explicit source."""

    estimate_seconds: Optional[int]
    source: str
    assessment: CompletenessAssessment

    def to_dict(self) -> Dict[str, object]:
        result = asdict(self)
        result["assessment"] = self.assessment.to_dict()
        return result


@dataclass(frozen=True)
class MinionCandidateSummary:
    """Per-player minion-related candidate counts from credit events."""

    player_name: str
    player_eid_be: int
    action_0e_value_1: int
    action_0f_value_1: int
    action_0d_total: int
    last_0e_frame: Optional[int] = None
    last_0f_frame: Optional[int] = None
    last_0d_frame: Optional[int] = None

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class KDAPlayerSummary:
    """Per-player v2 K/D/A summary."""

    player_name: str
    team: str
    hero_name: str
    kills: int
    deaths: int
    assists: int
    minion_kills: int

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class KDAExtractionResult:
    """Conservative KDA extraction output."""

    accepted: bool
    reason: str
    assessment: CompletenessAssessment
    duration_estimate: DurationEstimate
    players: Tuple[KDAPlayerSummary, ...] = ()

    def to_dict(self) -> Dict[str, object]:
        result = asdict(self)
        result["assessment"] = self.assessment.to_dict()
        result["duration_estimate"] = self.duration_estimate.to_dict()
        result["players"] = [player.to_dict() for player in self.players]
        return result


@dataclass(frozen=True)
class WinnerExtractionResult:
    """Conservative winner extraction output."""

    accepted: bool
    reason: str
    assessment: CompletenessAssessment
    duration_estimate: DurationEstimate
    winner: Optional[str]
    left_kills: Optional[int]
    right_kills: Optional[int]

    def to_dict(self) -> Dict[str, object]:
        result = asdict(self)
        result["assessment"] = self.assessment.to_dict()
        result["duration_estimate"] = self.duration_estimate.to_dict()
        return result


@dataclass(frozen=True)
class AcceptedPlayerFields:
    """Fields safe enough to export for a player today."""

    name: str
    team: str
    entity_id: Optional[int]
    hero_name: str
    kills: Optional[int] = None
    deaths: Optional[int] = None
    assists: Optional[int] = None

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class FieldDecision:
    """Product-level decision for a decoded field."""

    value: object
    claim_status: str
    accepted_for_index: bool
    claim_id: str
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class DecoderV2MatchOutput:
    """Conservative v2 output separating accepted vs withheld fields."""

    schema_version: str
    replay_name: str
    replay_file: str
    game_mode: str
    map_name: str
    team_size: int
    completeness_status: str
    completeness_reason: str
    accepted_fields: Dict[str, FieldDecision]
    withheld_fields: Dict[str, FieldDecision]
    players: Tuple[AcceptedPlayerFields, ...]

    def to_dict(self) -> Dict[str, object]:
        result = asdict(self)
        result["accepted_fields"] = {
            key: value.to_dict() for key, value in self.accepted_fields.items()
        }
        result["withheld_fields"] = {
            key: value.to_dict() for key, value in self.withheld_fields.items()
        }
        result["players"] = [player.to_dict() for player in self.players]
        return result
