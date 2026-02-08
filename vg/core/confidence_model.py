#!/usr/bin/env python3
"""
Confidence Model - Scoring system for hero matching reliability.

Provides confidence levels (HIGH, MEDIUM, LOW) for extracted data
to help users understand data reliability.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, Optional, List


class ConfidenceLevel(Enum):
    """Confidence level classifications."""
    HIGH = "high"      # >= 0.8 - Reliable match
    MEDIUM = "medium"  # 0.5 - 0.8 - Probable match
    LOW = "low"        # < 0.5 - Uncertain, needs review


@dataclass
class ConfidenceScore:
    """Confidence score with breakdown."""
    value: float           # 0.0 - 1.0
    level: ConfidenceLevel
    source: str            # "extracted", "inferred", "truth"
    factors: Dict[str, float]  # Breakdown of contributing factors

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": round(self.value, 4),
            "level": self.level.value,
            "source": self.source,
            "factors": {k: round(v, 4) for k, v in self.factors.items()}
        }


class ConfidenceScorer:
    """
    Calculate confidence scores for hero matching results.

    Factors:
    - event_count: How many events match the hero pattern
    - offset_order: Does first occurrence match player order
    - probe_match: Hero-probe offset correlation
    - uniqueness: Is this hero unique in the match
    """

    # Thresholds for confidence levels
    THRESHOLD_HIGH = 0.8
    THRESHOLD_MEDIUM = 0.5

    # Default weights
    DEFAULT_WEIGHTS = {
        "event_count": 0.4,
        "offset_order": 0.3,
        "probe_match": 0.2,
        "uniqueness": 0.1
    }

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        """
        Initialize scorer with optional custom weights.

        Args:
            weights: Custom weight dict (must sum to 1.0)
        """
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()

    def calculate_confidence(
        self,
        event_count: int,
        avg_event_count: float,
        offset_order_matches: bool,
        probe_match_rate: float,
        is_unique: bool
    ) -> ConfidenceScore:
        """
        Calculate overall confidence score.

        Args:
            event_count: Number of hero pattern occurrences
            avg_event_count: Average count across all candidates
            offset_order_matches: Does offset order match player position
            probe_match_rate: Ratio of probe offset matches (0-1)
            is_unique: Is this hero unique in the match

        Returns:
            ConfidenceScore with breakdown
        """
        factors = {}

        # Factor 1: Event count relative to average
        if avg_event_count > 0:
            count_ratio = event_count / avg_event_count
            factors["event_count"] = min(count_ratio, 1.5) / 1.5  # Cap at 1.0
        else:
            factors["event_count"] = 0.5

        # Factor 2: Offset order consistency
        factors["offset_order"] = 1.0 if offset_order_matches else 0.5

        # Factor 3: Probe match rate
        factors["probe_match"] = probe_match_rate

        # Factor 4: Uniqueness
        factors["uniqueness"] = 1.0 if is_unique else 0.7

        # Calculate weighted sum
        value = sum(
            factors[k] * self.weights[k]
            for k in self.weights.keys()
        )

        # Determine level
        if value >= self.THRESHOLD_HIGH:
            level = ConfidenceLevel.HIGH
        elif value >= self.THRESHOLD_MEDIUM:
            level = ConfidenceLevel.MEDIUM
        else:
            level = ConfidenceLevel.LOW

        return ConfidenceScore(
            value=value,
            level=level,
            source="extracted",
            factors=factors
        )

    def score_from_hero_candidate(
        self,
        candidate: Dict[str, Any],
        all_candidates: List[Dict[str, Any]],
        player_position: int
    ) -> ConfidenceScore:
        """
        Calculate confidence from HeroCandidate dict.

        Args:
            candidate: HeroCandidate as dict
            all_candidates: All candidates for uniqueness check
            player_position: Expected player position

        Returns:
            ConfidenceScore
        """
        # Calculate average event count
        counts = [c.get("event_count", 0) for c in all_candidates]
        avg_count = sum(counts) / len(counts) if counts else 1

        # Check offset order
        sorted_by_offset = sorted(all_candidates, key=lambda x: x.get("first_offset", 0))
        expected_position = next(
            (i for i, c in enumerate(sorted_by_offset)
             if c.get("hero_id") == candidate.get("hero_id")),
            -1
        )
        offset_matches = (expected_position == player_position)

        # Probe match rate (normalize to 0-1)
        probe_matches = candidate.get("probe_matches", 0)
        probe_rate = min(probe_matches / 100, 1.0) if probe_matches > 0 else 0.5

        # Check uniqueness
        hero_id = candidate.get("hero_id")
        same_hero_count = sum(1 for c in all_candidates if c.get("hero_id") == hero_id)
        is_unique = (same_hero_count == 1)

        return self.calculate_confidence(
            event_count=candidate.get("event_count", 0),
            avg_event_count=avg_count,
            offset_order_matches=offset_matches,
            probe_match_rate=probe_rate,
            is_unique=is_unique
        )

    @staticmethod
    def from_truth() -> ConfidenceScore:
        """Create a confidence score for truth/OCR data."""
        return ConfidenceScore(
            value=1.0,
            level=ConfidenceLevel.HIGH,
            source="truth",
            factors={"truth_data": 1.0}
        )

    @staticmethod
    def unknown() -> ConfidenceScore:
        """Create a confidence score for unknown/missing data."""
        return ConfidenceScore(
            value=0.0,
            level=ConfidenceLevel.LOW,
            source="unknown",
            factors={}
        )


def get_confidence_level(value: float) -> ConfidenceLevel:
    """Get confidence level from numeric value."""
    if value >= 0.8:
        return ConfidenceLevel.HIGH
    elif value >= 0.5:
        return ConfidenceLevel.MEDIUM
    else:
        return ConfidenceLevel.LOW
