#!/usr/bin/env python3
"""
Hero Matcher - Hero matching for Vainglory replays.

IMPORTANT: Hero IDs cannot be reliably extracted from replay binary data.
This module provides a framework for hero matching that primarily relies on
external truth data (OCR/manual input) rather than binary pattern detection.

The binary detection methods are preserved for research purposes but should
not be used in production - they have 0% accuracy in real-world testing.
"""

from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple

# Import asset hero map
try:
    from vgr_mapping import ASSET_HERO_ID_MAP, normalize_hero_name
except ImportError:
    from .vgr_mapping import ASSET_HERO_ID_MAP, normalize_hero_name


@dataclass
class HeroCandidate:
    """Detected/assigned hero candidate."""
    hero_id: Optional[int] = None
    hero_name: str = "Unknown"
    event_count: int = 0
    first_offset: int = 0
    probe_matches: int = 0
    confidence: float = 0.0
    source: str = "unknown"  # "truth", "extracted", "unknown"

    def to_dict(self) -> Dict:
        return asdict(self)


class HeroMatcher:
    """
    Hero matching for replay data.

    NOTE: Binary-based hero detection has been proven unreliable (0% accuracy).
    This class now primarily serves as a framework for truth-based hero assignment.

    For reliable hero data, use extract_with_truth() in ReplayExtractor
    which merges truth data from OCR/manual sources.
    """

    # These thresholds are preserved for research but binary detection is disabled by default
    EVENT_COUNT_THRESHOLD = 15
    PROBE_OFFSETS = [6, 23, 70]

    # Signal weights (for research only)
    WEIGHT_EVENT_COUNT = 0.4
    WEIGHT_OFFSET_ORDER = 0.3
    WEIGHT_PROBE_MATCH = 0.3

    def __init__(self, data: bytes = b"", team_size: int = 3):
        """
        Initialize matcher.

        Args:
            data: Raw bytes from replay (optional, not used in production)
            team_size: Expected players per team (3 or 5)
        """
        self.data = data
        self.team_size = team_size
        self.expected_heroes = team_size * 2
        self.hero_map = self._build_int_hero_map()

    def _build_int_hero_map(self) -> Dict[int, str]:
        """Convert ASSET_HERO_ID_MAP string keys to integers."""
        result = {}
        for key, name in ASSET_HERO_ID_MAP.items():
            try:
                int_key = int(key)
                result[int_key] = name
            except (ValueError, TypeError):
                continue
        return result

    def detect_heroes(self) -> List[HeroCandidate]:
        """
        Attempt to detect heroes from binary data.

        WARNING: This method has 0% accuracy in real-world testing.
        Binary hero detection is not reliable - use truth data instead.

        Returns:
            List of HeroCandidate with source="extracted" and confidence=0.0
        """
        if not self.data:
            return self._create_unknown_candidates()

        candidates = []
        for hero_id, hero_name in self.hero_map.items():
            pattern = bytes([hero_id, 0, 0, 0])
            count = self.data.count(pattern)

            if count >= self.EVENT_COUNT_THRESHOLD:
                first_offset = self.data.find(pattern)
                candidates.append(HeroCandidate(
                    hero_id=hero_id,
                    hero_name=hero_name,
                    event_count=count,
                    first_offset=first_offset,
                    confidence=0.0,  # Binary detection is unreliable
                    source="extracted"
                ))

        candidates.sort(key=lambda x: x.first_offset)

        # Return candidates but mark them as unreliable
        result = candidates[:self.expected_heroes]

        # Pad with unknowns if needed
        while len(result) < self.expected_heroes:
            result.append(HeroCandidate(
                hero_name="Unknown",
                confidence=0.0,
                source="unknown"
            ))

        return result

    def detect_heroes_with_probes(
        self,
        entity_ids: Optional[List[int]] = None
    ) -> List[HeroCandidate]:
        """
        Enhanced detection using hero-probe offsets.

        WARNING: This method has 0% accuracy in real-world testing.

        Args:
            entity_ids: List of player entity IDs

        Returns:
            List of HeroCandidate (unreliable)
        """
        # Just return basic detection - probes don't improve accuracy
        return self.detect_heroes()

    def _create_unknown_candidates(self) -> List[HeroCandidate]:
        """Create list of unknown candidates when no data available."""
        return [
            HeroCandidate(
                hero_name="Unknown",
                confidence=0.0,
                source="unknown"
            )
            for _ in range(self.expected_heroes)
        ]

    def match_heroes_to_players(
        self,
        players: List[Dict],
        use_probes: bool = False
    ) -> List[Dict]:
        """
        Match heroes to players.

        NOTE: Without truth data, all heroes will be marked as "Unknown"
        with confidence=0.0. Use ReplayExtractor.extract_with_truth()
        for reliable hero data.

        Args:
            players: List of player dicts
            use_probes: Ignored (probes don't improve accuracy)

        Returns:
            Players with hero_name="Unknown" and hero_confidence=0.0
        """
        result = []
        for player in players:
            player_copy = dict(player)
            # Mark as unknown - binary detection is unreliable
            player_copy['hero_name'] = 'Unknown'
            player_copy['hero_id'] = None
            player_copy['hero_confidence'] = 0.0
            player_copy['hero_source'] = 'unknown'
            result.append(player_copy)

        return result

    @staticmethod
    def from_truth(
        player_name: str,
        hero_name: str,
        hero_id: Optional[int] = None
    ) -> HeroCandidate:
        """
        Create a HeroCandidate from truth data.

        This is the recommended way to get hero information.

        Args:
            player_name: Player name (for reference)
            hero_name: Hero name from truth data
            hero_id: Optional hero ID

        Returns:
            HeroCandidate with confidence=1.0 and source="truth"
        """
        normalized_name = normalize_hero_name(hero_name)
        return HeroCandidate(
            hero_id=hero_id,
            hero_name=normalized_name,
            confidence=1.0,
            source="truth"
        )


def match_heroes(
    data: bytes,
    players: List[Dict],
    team_size: int = 3
) -> List[Dict]:
    """
    Convenience function for hero matching.

    NOTE: Without truth data, returns players with hero_name="Unknown".
    For reliable hero data, use ReplayExtractor.extract_with_truth().

    Args:
        data: Raw replay bytes (not used effectively)
        players: List of player dicts
        team_size: Players per team

    Returns:
        Players with hero_name="Unknown" (binary detection unreliable)
    """
    matcher = HeroMatcher(data, team_size)
    return matcher.match_heroes_to_players(players)
