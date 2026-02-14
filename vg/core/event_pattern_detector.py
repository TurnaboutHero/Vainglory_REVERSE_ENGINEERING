"""
Event Pattern-Based Hero Detection

This module uses event frequency patterns to identify heroes based on their
gameplay signature. Different heroes exhibit distinct event patterns:
- Ranged heroes have high 0x0E (ranged attack) frequencies
- Melee heroes have low/zero 0x0E frequencies
- High-mobility heroes have unique 0x13 patterns
"""

import json
import math
from pathlib import Path
from typing import Dict, List, Tuple, Optional


class EventPatternDetector:
    """Detects heroes based on event frequency patterns."""

    def __init__(self, profiles_path: str = None):
        """
        Initialize the detector with hero event profiles.

        Args:
            profiles_path: Path to hero_event_profiles.json. If None, uses default location.
        """
        if profiles_path is None:
            # Default to vg/data/hero_event_profiles.json relative to this file
            base_dir = Path(__file__).parent.parent
            profiles_path = base_dir / "data" / "hero_event_profiles.json"

        self.profiles = self._load_profiles(str(profiles_path))
        self.event_codes = self.profiles.get("event_codes", [])

    def _load_profiles(self, path: str) -> dict:
        """Load hero event profiles from JSON file."""
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def detect_hero(self, player_events: Dict[str, int], top_n: int = 5) -> List[Tuple[str, float]]:
        """
        Detect the most likely hero based on event frequency patterns.

        Args:
            player_events: Dictionary of event code -> count (e.g., {"0x44": 60, "0x43": 30})
            top_n: Number of top matches to return

        Returns:
            List of (hero_name, similarity_score) tuples, sorted by similarity (highest first)
        """
        # Normalize player events to ratios
        player_pattern = self._normalize_events(player_events)

        # Calculate similarity with all hero profiles
        similarities = []
        for hero_name, profile in self.profiles["profiles"].items():
            hero_pattern = profile["event_ratios"]
            similarity = self._calculate_cosine_similarity(player_pattern, hero_pattern)
            similarities.append((hero_name, similarity))

        # Sort by similarity (highest first) and return top N
        similarities.sort(key=lambda x: x[1], reverse=True)
        return similarities[:top_n]

    def detect_hero_best(self, player_events: Dict[str, int]) -> Tuple[str, float]:
        """
        Detect the single best hero match.

        Args:
            player_events: Dictionary of event code -> count

        Returns:
            Tuple of (hero_name, confidence_score)
        """
        results = self.detect_hero(player_events, top_n=1)
        if results:
            return results[0]
        return ("Unknown", 0.0)

    def _normalize_events(self, events: Dict[str, int]) -> Dict[str, float]:
        """
        Normalize event counts to ratios (0.0 to 1.0).

        Args:
            events: Dictionary of event code -> count

        Returns:
            Dictionary of event code -> ratio
        """
        total = sum(events.values())
        if total == 0:
            return {code: 0.0 for code in self.event_codes}

        # Normalize to ratios
        ratios = {}
        for code in self.event_codes:
            ratios[code] = events.get(code, 0) / total

        return ratios

    def _calculate_cosine_similarity(self, pattern1: Dict[str, float], pattern2: Dict[str, float]) -> float:
        """
        Calculate cosine similarity between two event patterns.

        Cosine similarity measures the angle between two vectors:
        similarity = dot(A, B) / (||A|| * ||B||)

        Range: 0.0 (completely different) to 1.0 (identical)

        Args:
            pattern1: First pattern (event code -> ratio)
            pattern2: Second pattern (event code -> ratio)

        Returns:
            Similarity score between 0.0 and 1.0
        """
        # Get all event codes from both patterns
        all_codes = set(pattern1.keys()) | set(pattern2.keys())

        # Calculate dot product and magnitudes
        dot_product = 0.0
        magnitude1 = 0.0
        magnitude2 = 0.0

        for code in all_codes:
            val1 = pattern1.get(code, 0.0)
            val2 = pattern2.get(code, 0.0)

            dot_product += val1 * val2
            magnitude1 += val1 * val1
            magnitude2 += val2 * val2

        # Calculate cosine similarity
        magnitude1 = math.sqrt(magnitude1)
        magnitude2 = math.sqrt(magnitude2)

        if magnitude1 == 0.0 or magnitude2 == 0.0:
            return 0.0

        return dot_product / (magnitude1 * magnitude2)

    def _calculate_euclidean_distance(self, pattern1: Dict[str, float], pattern2: Dict[str, float]) -> float:
        """
        Calculate Euclidean distance between two event patterns.

        Lower distance = more similar patterns.

        Args:
            pattern1: First pattern (event code -> ratio)
            pattern2: Second pattern (event code -> ratio)

        Returns:
            Distance score (lower is better)
        """
        all_codes = set(pattern1.keys()) | set(pattern2.keys())

        distance_squared = 0.0
        for code in all_codes:
            val1 = pattern1.get(code, 0.0)
            val2 = pattern2.get(code, 0.0)
            distance_squared += (val1 - val2) ** 2

        return math.sqrt(distance_squared)

    def get_hero_profile(self, hero_name: str) -> Optional[dict]:
        """
        Get the event profile for a specific hero.

        Args:
            hero_name: Name of the hero

        Returns:
            Hero profile dictionary or None if not found
        """
        return self.profiles["profiles"].get(hero_name)

    def get_all_heroes(self) -> List[str]:
        """Get list of all heroes with profiles."""
        return list(self.profiles["profiles"].keys())

    def analyze_pattern(self, player_events: Dict[str, int]) -> dict:
        """
        Comprehensive analysis of an event pattern.

        Args:
            player_events: Dictionary of event code -> count

        Returns:
            Dictionary with analysis results including top matches, pattern breakdown, etc.
        """
        normalized = self._normalize_events(player_events)
        top_matches = self.detect_hero(player_events, top_n=5)

        total_events = sum(player_events.values())

        # Identify dominant events
        sorted_events = sorted(normalized.items(), key=lambda x: x[1], reverse=True)
        dominant_events = [(code, ratio) for code, ratio in sorted_events if ratio > 0.1]

        return {
            "total_events": total_events,
            "normalized_pattern": normalized,
            "dominant_events": dominant_events,
            "top_matches": top_matches,
            "best_match": top_matches[0] if top_matches else ("Unknown", 0.0),
            "confidence_gap": top_matches[0][1] - top_matches[1][1] if len(top_matches) >= 2 else 0.0
        }


def main():
    """Example usage of EventPatternDetector."""
    detector = EventPatternDetector()

    # Example: Grumpjaw pattern from the data
    grumpjaw_events = {
        "0x44": 473,
        "0x43": 340,
        "0x0E": 308,
        "0x65": 212,
        "0x13": 152,
        "0x76": 123
    }

    print("Event Pattern Detection Demo")
    print("=" * 60)
    print(f"\nTest Pattern (Grumpjaw sample):")
    print(f"Total Events: {sum(grumpjaw_events.values())}")
    for code, count in grumpjaw_events.items():
        print(f"  {code}: {count}")

    print("\n" + "=" * 60)
    print("Top 5 Matches:")
    print("=" * 60)

    matches = detector.detect_hero(grumpjaw_events, top_n=5)
    for i, (hero, score) in enumerate(matches, 1):
        print(f"{i}. {hero:20s} - Similarity: {score:.4f} ({score*100:.2f}%)")

    print("\n" + "=" * 60)
    print("Detailed Analysis:")
    print("=" * 60)

    analysis = detector.analyze_pattern(grumpjaw_events)
    print(f"\nBest Match: {analysis['best_match'][0]} (confidence: {analysis['best_match'][1]:.4f})")
    print(f"Confidence Gap: {analysis['confidence_gap']:.4f}")
    print(f"\nDominant Events (>10%):")
    for code, ratio in analysis['dominant_events']:
        print(f"  {code}: {ratio:.2%}")


if __name__ == "__main__":
    main()
