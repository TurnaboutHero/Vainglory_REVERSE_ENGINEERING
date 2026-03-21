"""Protocol claim registry for VGR decoder v2 foundations."""

from __future__ import annotations

from .models import ClaimStatus, DecoderFieldStatus, EventHeaderClaim, OffsetClaim, ValidationEvidence


PLAYER_BLOCK_EVIDENCE = (
    ValidationEvidence(
        source_type="fixture_validation",
        reference="vg/docs/DECODER_VALIDATION_2026-03-21.md",
        summary="11 tournament fixtures, 109/109 normalized/fuzzy hero matches from +0xA9, 110 player blocks with stable team bytes at +0xD5.",
    ),
)

DECODER_EVIDENCE = (
    ValidationEvidence(
        source_type="fixture_validation",
        reference="vg/output/decode_tournament_validation_v2.json",
        summary="Current decoder performance on 11 tournament truth fixtures and complete-only subset.",
    ),
)

OFFSET_CLAIMS = [
    OffsetClaim(
        claim_id="player_block.entity_id",
        structure="player_block",
        offset=0x0A5,
        value_type="uint16",
        endian="little",
        meaning="Player entity id used in event stream correlation.",
        status=ClaimStatus.CONFIRMED,
        evidence=PLAYER_BLOCK_EVIDENCE,
    ),
    OffsetClaim(
        claim_id="player_block.hero_id",
        structure="player_block",
        offset=0x0A9,
        value_type="uint16",
        endian="little",
        meaning="Hero selection id stored directly in player block.",
        status=ClaimStatus.CONFIRMED,
        evidence=PLAYER_BLOCK_EVIDENCE,
    ),
    OffsetClaim(
        claim_id="player_block.hero_hash",
        structure="player_block",
        offset=0x0AB,
        value_type="bytes[4]",
        endian="raw",
        meaning="Hero hash / fingerprint bytes following hero id.",
        status=ClaimStatus.STRONG,
        evidence=(
            ValidationEvidence(
                source_type="documentation",
                reference="vg/docs/HERO_DETECTION_RESULTS.md",
                summary="Documented as hero-stable fingerprint; not independently revalidated in this round.",
            ),
        ),
    ),
    OffsetClaim(
        claim_id="player_block.team_byte",
        structure="player_block",
        offset=0x0D5,
        value_type="uint8",
        endian="raw",
        meaning="Binary team grouping byte. Stable for grouping, not necessarily API left/right convention.",
        status=ClaimStatus.CONFIRMED,
        evidence=PLAYER_BLOCK_EVIDENCE,
    ),
]

EVENT_HEADER_CLAIMS = [
    EventHeaderClaim(
        claim_id="event.kill",
        header_hex="18 04 1C",
        structure="kill_event",
        entity_offset=5,
        entity_endian="big",
        timestamp_offset=-7,
        timestamp_endian="float32-be",
        meaning="Kill header used by KDADetector.",
        status=ClaimStatus.CONFIRMED,
        evidence=DECODER_EVIDENCE,
    ),
    EventHeaderClaim(
        claim_id="event.death",
        header_hex="08 04 31",
        structure="death_event",
        entity_offset=5,
        entity_endian="big",
        timestamp_offset=9,
        timestamp_endian="float32-be",
        meaning="Death header used by KDADetector and duration heuristics.",
        status=ClaimStatus.CONFIRMED,
        evidence=DECODER_EVIDENCE,
    ),
    EventHeaderClaim(
        claim_id="event.credit",
        header_hex="10 04 1D",
        structure="credit_event",
        entity_offset=5,
        entity_endian="big",
        timestamp_offset=7,
        timestamp_endian="float32-be",
        meaning="Credit / gold / assist-related event family.",
        status=ClaimStatus.STRONG,
        evidence=DECODER_EVIDENCE,
    ),
    EventHeaderClaim(
        claim_id="event.item_acquire",
        header_hex="10 04 3D",
        structure="item_acquire_event",
        entity_offset=5,
        entity_endian="big",
        timestamp_offset=17,
        timestamp_endian="float32-be",
        meaning="Item acquisition / item timeline event family.",
        status=ClaimStatus.STRONG,
        evidence=(
            ValidationEvidence(
                source_type="code_reference",
                reference="vg/core/unified_decoder.py",
                summary="Used by current item build estimation pipeline.",
            ),
        ),
    ),
]

DECODER_FIELD_STATUSES = [
    DecoderFieldStatus(
        field_name="hero",
        status=ClaimStatus.CONFIRMED,
        source_kind="direct_offset",
        rationale="Backed by direct player block offset +0xA9 and 11-fixture validation.",
    ),
    DecoderFieldStatus(
        field_name="team_grouping",
        status=ClaimStatus.CONFIRMED,
        source_kind="direct_offset",
        rationale="Backed by player block team byte grouping at +0xD5.",
    ),
    DecoderFieldStatus(
        field_name="winner_complete_fixture",
        status=ClaimStatus.STRONG,
        source_kind="derived",
        rationale="100% on complete tournament fixtures, but incomplete replay handling still breaks it.",
    ),
    DecoderFieldStatus(
        field_name="kills",
        status=ClaimStatus.STRONG,
        source_kind="derived",
        rationale="~99% on complete tournament fixtures.",
    ),
    DecoderFieldStatus(
        field_name="deaths",
        status=ClaimStatus.STRONG,
        source_kind="derived",
        rationale="~98% on complete tournament fixtures.",
    ),
    DecoderFieldStatus(
        field_name="assists",
        status=ClaimStatus.STRONG,
        source_kind="derived",
        rationale="~98% on complete tournament fixtures.",
    ),
    DecoderFieldStatus(
        field_name="minion_kills",
        status=ClaimStatus.PARTIAL,
        source_kind="derived",
        rationale="Only ~87% on complete tournament fixtures and very weak on match outliers.",
    ),
    DecoderFieldStatus(
        field_name="duration_seconds",
        status=ClaimStatus.PARTIAL,
        source_kind="derived",
        rationale="MAE ~17.4s on complete fixtures, exact match 0/11 overall.",
    ),
    DecoderFieldStatus(
        field_name="completeness_detection",
        status=ClaimStatus.PARTIAL,
        source_kind="guardrail",
        rationale="Current conservative gate correctly separates all 11 tournament fixtures, but broader replay coverage is still limited.",
    ),
]
