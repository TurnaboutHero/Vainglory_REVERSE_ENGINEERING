"""
Signature Event-Based Hero Detection

Uses hero-specific "signature events" - event codes that are highly concentrated
for specific heroes. Much more discriminative than the generic event ratio approach.

Key insight: Certain event codes appear almost exclusively for specific heroes.
For example:
- 0xEE, 0xEF, 0xB8, 0xE0 → Skaarf (80%+ concentration)
- 0x08 → Grumpjaw (65%, 24x average)
- 0xCE → Ylva (66.57%)
"""

import json
import math
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Optional, Any


# Hero signature events - derived from full_event_analysis.py
# Format: {hero_name: [(event_code, weight), ...]}
# Weight based on concentration and distinctiveness

HERO_SIGNATURES = {
    "Skaarf": [
        (0xEE, 0.836),   # 83.6% concentration
        (0xEF, 0.814),   # 81.37%
        (0xB8, 0.793),   # 79.31%
        (0xE0, 0.762),   # 76.22%
    ],
    "Caine": [
        (0xF3, 0.678),   # 67.82%
        (0x98, 0.669),   # 66.89%
        (0x87, 0.664),   # 66.41%
        (0x03, 0.435),   # 43.50% (rare event)
    ],
    "Kensei": [
        (0x96, 0.678),   # 67.77%
    ],
    "Ylva": [
        (0xCE, 0.666),   # 66.57%
    ],
    "Grumpjaw": [
        (0x08, 0.654),   # 65.38%, 24x average
    ],
    "Gwen": [
        (0x83, 0.618),   # 61.83%
    ],
    "Joule": [
        (0x82, 0.575),   # 57.51%
        (0xC9, 0.587),   # 58.66%
    ],
    "Kestrel": [
        (0xFE, 0.390),   # 39.00%
    ],
    "Reza": [
        (0xCF, 0.399),   # 39.88%
    ],
}


class SignatureDetector:
    """
    Detects heroes based on signature event codes.

    Algorithm:
    1. For each hero with known signatures, check if player has those events
    2. Calculate weighted score based on presence and count of signature events
    3. Heroes with strong signature matches are prioritized
    """

    def __init__(self, full_analysis_path: str = None):
        """
        Initialize detector.

        Args:
            full_analysis_path: Path to full_event_analysis.json for dynamic signature building
        """
        self.signatures = HERO_SIGNATURES.copy()

        if full_analysis_path and Path(full_analysis_path).exists():
            self._load_dynamic_signatures(full_analysis_path)

    def _load_dynamic_signatures(self, path: str):
        """Load and enhance signatures from full analysis."""
        with open(path, 'r', encoding='utf-8') as f:
            analysis = json.load(f)

        # Build signatures from concentrated events
        for event in analysis.get("concentrated_events", []):
            top_hero = event["top_hero"]
            event_code = int(event["event_code"], 16)
            concentration = event["concentration"]

            if concentration >= 0.5:  # Only use highly concentrated events
                if top_hero not in self.signatures:
                    self.signatures[top_hero] = []

                # Check if this event is already in the signature
                existing_codes = [e[0] for e in self.signatures[top_hero]]
                if event_code not in existing_codes:
                    self.signatures[top_hero].append((event_code, concentration))

    def detect_hero(self, player_events: Dict[int, int], top_n: int = 5) -> List[Tuple[str, float, str]]:
        """
        Detect hero based on signature events.

        Args:
            player_events: Dictionary of event_code (int) -> count
            top_n: Number of top matches to return

        Returns:
            List of (hero_name, score, explanation) tuples
        """
        scores = []

        for hero, sigs in self.signatures.items():
            score, explanation = self._calculate_signature_score(player_events, sigs)
            if score > 0:
                scores.append((hero, score, explanation))

        # Sort by score descending
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_n]

    def _calculate_signature_score(
        self,
        player_events: Dict[int, int],
        signatures: List[Tuple[int, float]]
    ) -> Tuple[float, str]:
        """
        Calculate signature match score.

        Score = sum(weight * presence * log(count + 1)) for each signature event
        """
        total_score = 0.0
        matched_events = []

        for event_code, weight in signatures:
            count = player_events.get(event_code, 0)
            if count > 0:
                # Log scale to prevent huge counts from dominating
                event_score = weight * math.log(count + 1)
                total_score += event_score
                matched_events.append(f"0x{event_code:02X}:{count}")

        # Normalize by number of signatures
        if signatures:
            total_score /= len(signatures)

        explanation = f"Matched: {', '.join(matched_events)}" if matched_events else "No signature match"
        return total_score, explanation

    def detect_hero_best(self, player_events: Dict[int, int]) -> Tuple[str, float, str]:
        """
        Detect single best hero match.

        Returns:
            (hero_name, confidence, explanation)
        """
        results = self.detect_hero(player_events, top_n=1)
        if results:
            return results[0]
        return ("Unknown", 0.0, "No signature events found")

    def get_hero_signatures(self, hero_name: str) -> Optional[List[Tuple[int, float]]]:
        """Get signature events for a specific hero."""
        return self.signatures.get(hero_name)

    def get_all_heroes_with_signatures(self) -> List[str]:
        """Get list of all heroes that have known signatures."""
        return list(self.signatures.keys())


class HybridDetector:
    """
    Hybrid detector combining signature-based and pattern-based detection.

    Strategy:
    1. First try signature detection (high confidence for heroes with signatures)
    2. Fall back to pattern detection for heroes without clear signatures
    """

    def __init__(
        self,
        full_analysis_path: str = None,
        hero_profiles_path: str = None
    ):
        self.signature_detector = SignatureDetector(full_analysis_path)
        self.hero_profiles = self._load_profiles(hero_profiles_path) if hero_profiles_path else {}

    def _load_profiles(self, path: str) -> Dict[str, Dict[int, float]]:
        """Load hero event profiles."""
        if not Path(path).exists():
            return {}

        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Convert to int keys
        profiles = {}
        for hero, profile in data.get("hero_event_profiles", {}).items():
            profiles[hero] = {
                (int(k, 16) if isinstance(k, str) else k): v
                for k, v in profile.items()
            }
        return profiles

    def detect_hero(self, player_events: Dict[int, int]) -> Tuple[str, float, str]:
        """
        Detect hero using hybrid approach.

        Returns:
            (hero_name, confidence, method_used)
        """
        # Try signature detection first
        sig_results = self.signature_detector.detect_hero(player_events, top_n=3)

        if sig_results and sig_results[0][1] > 0.5:  # Strong signature match
            hero, score, explanation = sig_results[0]
            return (hero, min(score / 3.0, 1.0), f"Signature: {explanation}")

        # No strong signature - could fall back to pattern matching
        # For now, return best signature match even if weak
        if sig_results:
            hero, score, explanation = sig_results[0]
            return (hero, min(score / 5.0, 0.5), f"Weak signature: {explanation}")

        return ("Unknown", 0.0, "No detection method succeeded")


def main():
    """Demo signature detection."""
    print("=" * 70)
    print("SIGNATURE-BASED HERO DETECTION")
    print("=" * 70)

    detector = SignatureDetector()

    print("\nHeroes with known signatures:")
    for hero in detector.get_all_heroes_with_signatures():
        sigs = detector.get_hero_signatures(hero)
        sig_str = ", ".join([f"0x{code:02X}({weight:.2f})" for code, weight in sigs])
        print(f"  {hero}: {sig_str}")

    # Test with sample data
    print("\n" + "=" * 70)
    print("TEST DETECTION:")
    print("=" * 70)

    # Simulated Skaarf player (should detect Skaarf)
    skaarf_events = {
        0xEE: 1200,
        0xEF: 950,
        0xB8: 1500,
        0xE0: 780,
        0x44: 100,
        0x43: 80,
    }

    result = detector.detect_hero_best(skaarf_events)
    print(f"\nSkaarf test data: {result}")

    # Simulated Grumpjaw player
    grumpjaw_events = {
        0x08: 6000,
        0x44: 150,
        0x43: 100,
    }

    result = detector.detect_hero_best(grumpjaw_events)
    print(f"Grumpjaw test data: {result}")


if __name__ == "__main__":
    main()
