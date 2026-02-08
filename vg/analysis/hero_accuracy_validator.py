#!/usr/bin/env python3
"""
Hero Accuracy Validator - Validate hero matching against tournament truth data.

Measures accuracy of binary hero extraction against ground truth from OCR/manual data.
Provides detailed mismatch analysis and improvement suggestions.
"""

import argparse
import json
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from collections import Counter, defaultdict

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "core"))

try:
    from replay_extractor import ReplayExtractor
    from hero_matcher import HeroMatcher
    from vgr_mapping import normalize_hero_name, ASSET_HERO_ID_INT_MAP
except ImportError:
    from vg.core.replay_extractor import ReplayExtractor
    from vg.core.hero_matcher import HeroMatcher
    from vg.core.vgr_mapping import normalize_hero_name, ASSET_HERO_ID_INT_MAP


@dataclass
class MismatchDetail:
    """Details about a hero matching mismatch."""
    player_name: str
    replay_name: str
    expected_hero: str       # From truth
    detected_hero: str       # From binary
    confidence: float
    mismatch_type: str       # "wrong_hero", "not_detected", "order_error"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MatchAccuracy:
    """Accuracy metrics for a single match."""
    replay_name: str
    total_players: int
    correct_matches: int
    accuracy: float
    mismatches: List[MismatchDetail] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["mismatches"] = [m.to_dict() for m in self.mismatches]
        return result


@dataclass
class ValidationReport:
    """Complete validation report across all matches."""
    total_players: int
    correct_matches: int
    accuracy: float
    per_match_accuracy: Dict[str, float] = field(default_factory=dict)
    mismatches: List[MismatchDetail] = field(default_factory=list)
    mismatch_summary: Dict[str, int] = field(default_factory=dict)
    confidence_accuracy_correlation: float = 0.0
    hero_accuracy: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["mismatches"] = [m.to_dict() for m in self.mismatches]
        return result

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


class HeroAccuracyValidator:
    """
    Validate hero matching accuracy against ground truth data.

    Usage:
        validator = HeroAccuracyValidator(truth_path, replays_path)
        report = validator.validate()
        print(report.to_json())
    """

    def __init__(
        self,
        truth_path: str,
        replays_path: Optional[str] = None,
        verbose: bool = False
    ):
        """
        Initialize validator.

        Args:
            truth_path: Path to tournament_truth.json
            replays_path: Path to replay files (optional, uses truth paths if not provided)
            verbose: Print progress messages
        """
        self.truth_path = Path(truth_path)
        self.replays_path = Path(replays_path) if replays_path else None
        self.verbose = verbose

        # Load truth data
        with open(self.truth_path, 'r', encoding='utf-8') as f:
            self.truth_data = json.load(f)

        self.matches = self.truth_data.get("matches", [])

    def validate(self) -> ValidationReport:
        """
        Run validation across all matches.

        Returns:
            ValidationReport with accuracy metrics and mismatch analysis
        """
        total_players = 0
        correct_matches = 0
        all_mismatches: List[MismatchDetail] = []
        per_match_accuracy: Dict[str, float] = {}
        hero_results: Dict[str, Dict[str, int]] = defaultdict(lambda: {"correct": 0, "incorrect": 0})
        confidence_data: List[Tuple[float, bool]] = []  # (confidence, is_correct)

        for match in self.matches:
            replay_name = match.get("replay_name", "")
            truth_players = match.get("players", {})

            if self.verbose:
                print(f"Validating: {replay_name[:40]}...")

            # Try to find and process replay
            replay_path = self._find_replay_path(match)
            if not replay_path:
                if self.verbose:
                    print(f"  Skipped: Replay not found")
                continue

            # Extract heroes from binary
            try:
                extractor = ReplayExtractor(str(replay_path))
                extracted = extractor.extract()
            except Exception as e:
                if self.verbose:
                    print(f"  Error: {e}")
                continue

            # Compare extracted heroes with truth
            match_correct = 0
            match_total = len(truth_players)
            match_mismatches: List[MismatchDetail] = []

            # Build lookup of extracted heroes by player name
            extracted_heroes: Dict[str, Tuple[str, float]] = {}
            for player in extracted.all_players:
                extracted_heroes[player.name] = (
                    player.hero_name,
                    player.hero_confidence
                )

            for player_name, player_data in truth_players.items():
                expected_hero = normalize_hero_name(player_data.get("hero_name", "Unknown"))
                detected_hero, confidence = extracted_heroes.get(
                    player_name,
                    ("Unknown", 0.0)
                )
                detected_hero = normalize_hero_name(detected_hero)

                total_players += 1

                # Check if match
                is_correct = self._heroes_match(expected_hero, detected_hero)

                if is_correct:
                    correct_matches += 1
                    match_correct += 1
                    hero_results[expected_hero]["correct"] += 1
                else:
                    mismatch_type = self._classify_mismatch(
                        expected_hero, detected_hero
                    )
                    mismatch = MismatchDetail(
                        player_name=player_name,
                        replay_name=replay_name,
                        expected_hero=expected_hero,
                        detected_hero=detected_hero,
                        confidence=confidence,
                        mismatch_type=mismatch_type
                    )
                    match_mismatches.append(mismatch)
                    all_mismatches.append(mismatch)
                    hero_results[expected_hero]["incorrect"] += 1

                # Track confidence correlation data
                confidence_data.append((confidence, is_correct))

            # Store per-match accuracy
            if match_total > 0:
                per_match_accuracy[replay_name] = match_correct / match_total

        # Calculate overall accuracy
        accuracy = correct_matches / total_players if total_players > 0 else 0.0

        # Calculate mismatch summary
        mismatch_summary = Counter(m.mismatch_type for m in all_mismatches)

        # Calculate confidence-accuracy correlation
        correlation = self._calculate_confidence_correlation(confidence_data)

        # Calculate per-hero accuracy
        hero_accuracy = {}
        for hero, results in hero_results.items():
            total = results["correct"] + results["incorrect"]
            hero_accuracy[hero] = {
                "total": total,
                "correct": results["correct"],
                "accuracy": results["correct"] / total if total > 0 else 0.0
            }

        # Generate recommendations
        recommendations = self._generate_recommendations(
            accuracy, mismatch_summary, hero_accuracy
        )

        return ValidationReport(
            total_players=total_players,
            correct_matches=correct_matches,
            accuracy=accuracy,
            per_match_accuracy=per_match_accuracy,
            mismatches=all_mismatches,
            mismatch_summary=dict(mismatch_summary),
            confidence_accuracy_correlation=correlation,
            hero_accuracy=hero_accuracy,
            recommendations=recommendations
        )

    def _find_replay_path(self, match: Dict) -> Optional[Path]:
        """Find replay file path from match data."""
        # Try truth file path first
        truth_path = match.get("replay_file", "")
        if truth_path and Path(truth_path).exists():
            return Path(truth_path)

        # Try replays_path if provided
        if self.replays_path:
            replay_name = match.get("replay_name", "")
            # Search recursively for .0.vgr file
            for vgr in self.replays_path.rglob("*.0.vgr"):
                if replay_name in str(vgr):
                    return vgr

        return None

    def _heroes_match(self, expected: str, detected: str) -> bool:
        """Check if two hero names match (case-insensitive, normalized)."""
        if not expected or not detected:
            return False
        return expected.lower() == detected.lower()

    def _classify_mismatch(self, expected: str, detected: str) -> str:
        """Classify the type of mismatch."""
        if not detected or detected.lower() == "unknown":
            return "not_detected"
        # Could add more sophisticated classification here
        return "wrong_hero"

    def _calculate_confidence_correlation(
        self,
        data: List[Tuple[float, bool]]
    ) -> float:
        """Calculate correlation between confidence and correctness."""
        if len(data) < 2:
            return 0.0

        # Simple point-biserial correlation approximation
        correct_conf = [c for c, is_correct in data if is_correct]
        incorrect_conf = [c for c, is_correct in data if not is_correct]

        if not correct_conf or not incorrect_conf:
            return 0.0

        avg_correct = sum(correct_conf) / len(correct_conf)
        avg_incorrect = sum(incorrect_conf) / len(incorrect_conf)

        # Normalized difference (rough correlation estimate)
        return min(max(avg_correct - avg_incorrect, -1.0), 1.0)

    def _generate_recommendations(
        self,
        accuracy: float,
        mismatch_summary: Dict[str, int],
        hero_accuracy: Dict[str, Dict]
    ) -> List[str]:
        """Generate improvement recommendations based on analysis."""
        recommendations = []

        if accuracy < 0.85:
            recommendations.append(
                f"Overall accuracy ({accuracy:.1%}) below target (85%). "
                "Consider tuning detection parameters."
            )

        total_mismatches = sum(mismatch_summary.values())
        if total_mismatches > 0:
            # Check for dominant mismatch type
            for mtype, count in mismatch_summary.items():
                ratio = count / total_mismatches
                if mtype == "not_detected" and ratio > 0.5:
                    recommendations.append(
                        "High 'not_detected' rate. Consider lowering EVENT_COUNT_THRESHOLD."
                    )
                elif mtype == "wrong_hero" and ratio > 0.5:
                    recommendations.append(
                        "High 'wrong_hero' rate. Consider adjusting offset weights or "
                        "adding more detection signals."
                    )

        # Check for problematic heroes
        for hero, stats in hero_accuracy.items():
            if stats["total"] >= 3 and stats["accuracy"] < 0.5:
                recommendations.append(
                    f"Hero '{hero}' has low accuracy ({stats['accuracy']:.1%}). "
                    "May need special handling."
                )

        if not recommendations:
            recommendations.append("All metrics look good! No specific recommendations.")

        return recommendations


def validate_hero_accuracy(
    truth_path: str,
    replays_path: Optional[str] = None,
    verbose: bool = False
) -> ValidationReport:
    """
    Convenience function for hero accuracy validation.

    Args:
        truth_path: Path to tournament_truth.json
        replays_path: Optional path to replay files
        verbose: Print progress

    Returns:
        ValidationReport
    """
    validator = HeroAccuracyValidator(truth_path, replays_path, verbose)
    return validator.validate()


def main():
    parser = argparse.ArgumentParser(
        description="Validate hero matching accuracy against tournament truth data"
    )
    parser.add_argument(
        "--truth", "-t",
        required=True,
        help="Path to tournament_truth.json"
    )
    parser.add_argument(
        "--replays", "-r",
        help="Path to replay files directory"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output JSON file path"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print progress messages"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Hero Accuracy Validator")
    print("=" * 60)

    report = validate_hero_accuracy(
        args.truth,
        args.replays,
        args.verbose
    )

    # Print summary
    print(f"\nResults:")
    print(f"  Total Players: {report.total_players}")
    print(f"  Correct Matches: {report.correct_matches}")
    print(f"  Accuracy: {report.accuracy:.1%}")
    print(f"  Confidence Correlation: {report.confidence_accuracy_correlation:.3f}")

    print(f"\nMismatch Summary:")
    for mtype, count in report.mismatch_summary.items():
        print(f"  {mtype}: {count}")

    print(f"\nRecommendations:")
    for rec in report.recommendations:
        print(f"  - {rec}")

    # Save to file if requested
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(report.to_json())
        print(f"\nFull report saved to: {args.output}")

    # Return exit code based on accuracy
    target_accuracy = 0.85
    if report.accuracy >= target_accuracy:
        print(f"\n[PASS] Accuracy target ({target_accuracy:.0%}) met!")
        return 0
    else:
        print(f"\n[FAIL] Accuracy target ({target_accuracy:.0%}) not met.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
