"""
Validation Script for Event Pattern Hero Detection

This script validates the event pattern detection system using tournament replay data.
It compares predicted heroes against known ground truth from tournament replays.
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from vg.core.event_pattern_detector import EventPatternDetector


class EventPatternValidator:
    """Validates event pattern detection against tournament data."""

    def __init__(self, candidates_path: str, profiles_path: str = None):
        """
        Initialize validator.

        Args:
            candidates_path: Path to skill_event_candidates.json with ground truth
            profiles_path: Path to hero_event_profiles.json
        """
        self.detector = EventPatternDetector(profiles_path)
        self.candidates_data = self._load_candidates(candidates_path)

    def _load_candidates(self, path: str) -> dict:
        """Load skill event candidates JSON."""
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def validate_all_replays(self) -> Dict[str, any]:
        """
        Validate detection across all replays in the dataset.

        Returns:
            Dictionary with validation results and statistics
        """
        results = {
            "total_players": 0,
            "correct_predictions": 0,
            "incorrect_predictions": 0,
            "unknown_heroes": 0,
            "predictions": [],
            "confusion_matrix": {},
            "hero_accuracy": {}
        }

        # Process each replay
        for replay in self.candidates_data.get("detailed_replays", []):
            replay_name = replay["replay_name"]

            for player_name, player_data in replay["players"].items():
                true_hero = player_data["hero_name"]
                player_events = player_data["candidate_events"]

                # Skip unknown heroes
                if true_hero == "Unknown":
                    results["unknown_heroes"] += 1
                    continue

                # Detect hero
                predicted_hero, confidence = self.detector.detect_hero_best(player_events)

                # Get top 5 for analysis
                top_5 = self.detector.detect_hero(player_events, top_n=5)

                # Record result
                is_correct = (predicted_hero == true_hero)
                results["total_players"] += 1

                if is_correct:
                    results["correct_predictions"] += 1
                else:
                    results["incorrect_predictions"] += 1

                # Store prediction details
                prediction = {
                    "replay": replay_name,
                    "player": player_name,
                    "true_hero": true_hero,
                    "predicted_hero": predicted_hero,
                    "confidence": confidence,
                    "correct": is_correct,
                    "total_events": sum(player_events.values()),
                    "top_5_matches": top_5
                }
                results["predictions"].append(prediction)

                # Update confusion matrix
                if true_hero not in results["confusion_matrix"]:
                    results["confusion_matrix"][true_hero] = {}
                if predicted_hero not in results["confusion_matrix"][true_hero]:
                    results["confusion_matrix"][true_hero][predicted_hero] = 0
                results["confusion_matrix"][true_hero][predicted_hero] += 1

                # Update hero-specific accuracy
                if true_hero not in results["hero_accuracy"]:
                    results["hero_accuracy"][true_hero] = {
                        "total": 0,
                        "correct": 0,
                        "accuracy": 0.0
                    }
                results["hero_accuracy"][true_hero]["total"] += 1
                if is_correct:
                    results["hero_accuracy"][true_hero]["correct"] += 1

        # Calculate hero-specific accuracy
        for hero, stats in results["hero_accuracy"].items():
            stats["accuracy"] = stats["correct"] / stats["total"] if stats["total"] > 0 else 0.0

        # Calculate overall accuracy
        results["accuracy"] = (
            results["correct_predictions"] / results["total_players"]
            if results["total_players"] > 0 else 0.0
        )

        return results

    def print_validation_report(self, results: dict):
        """Print a detailed validation report."""
        print("=" * 80)
        print("EVENT PATTERN HERO DETECTION - VALIDATION REPORT")
        print("=" * 80)

        # Overall Statistics
        print("\nOVERALL STATISTICS:")
        print("-" * 80)
        print(f"Total Players Tested:     {results['total_players']}")
        print(f"Correct Predictions:      {results['correct_predictions']}")
        print(f"Incorrect Predictions:    {results['incorrect_predictions']}")
        print(f"Unknown Heroes (Skipped): {results['unknown_heroes']}")
        print(f"\nOverall Accuracy:         {results['accuracy']:.2%}")

        # Per-Hero Accuracy
        print("\n" + "=" * 80)
        print("PER-HERO ACCURACY:")
        print("=" * 80)
        print(f"{'Hero':<20} {'Total':<10} {'Correct':<10} {'Accuracy':<10}")
        print("-" * 80)

        # Sort by total occurrences (descending)
        sorted_heroes = sorted(
            results["hero_accuracy"].items(),
            key=lambda x: x[1]["total"],
            reverse=True
        )

        for hero, stats in sorted_heroes:
            print(f"{hero:<20} {stats['total']:<10} {stats['correct']:<10} {stats['accuracy']:<10.2%}")

        # Top Confusions
        print("\n" + "=" * 80)
        print("TOP 10 CONFUSION PAIRS (True Hero -> Predicted Hero):")
        print("=" * 80)

        confusions = []
        for true_hero, predictions in results["confusion_matrix"].items():
            for pred_hero, count in predictions.items():
                if true_hero != pred_hero:  # Only incorrect predictions
                    confusions.append((true_hero, pred_hero, count))

        confusions.sort(key=lambda x: x[2], reverse=True)

        print(f"{'True Hero':<20} {'Predicted Hero':<20} {'Count':<10}")
        print("-" * 80)
        for true_hero, pred_hero, count in confusions[:10]:
            print(f"{true_hero:<20} {pred_hero:<20} {count:<10}")

        # Low Confidence Correct Predictions
        print("\n" + "=" * 80)
        print("CORRECT PREDICTIONS WITH LOW CONFIDENCE (<0.90):")
        print("=" * 80)

        low_conf_correct = [
            p for p in results["predictions"]
            if p["correct"] and p["confidence"] < 0.90
        ]
        low_conf_correct.sort(key=lambda x: x["confidence"])

        if low_conf_correct:
            print(f"{'Hero':<20} {'Confidence':<15} {'Events':<10} {'Player':<20}")
            print("-" * 80)
            for p in low_conf_correct[:10]:
                print(f"{p['true_hero']:<20} {p['confidence']:<15.4f} {p['total_events']:<10} {p['player']:<20}")
        else:
            print("None found - all correct predictions have high confidence!")

        # High Confidence Incorrect Predictions
        print("\n" + "=" * 80)
        print("INCORRECT PREDICTIONS WITH HIGH CONFIDENCE (>0.85):")
        print("=" * 80)

        high_conf_incorrect = [
            p for p in results["predictions"]
            if not p["correct"] and p["confidence"] > 0.85
        ]
        high_conf_incorrect.sort(key=lambda x: x["confidence"], reverse=True)

        if high_conf_incorrect:
            print(f"{'True Hero':<15} {'Predicted':<15} {'Conf':<10} {'Events':<10} {'Player':<15}")
            print("-" * 80)
            for p in high_conf_incorrect[:10]:
                print(f"{p['true_hero']:<15} {p['predicted_hero']:<15} {p['confidence']:<10.4f} {p['total_events']:<10} {p['player']:<15}")
        else:
            print("None found - no high confidence mistakes!")

        # Sample Analysis
        print("\n" + "=" * 80)
        print("SAMPLE SIZE ANALYSIS:")
        print("=" * 80)

        hero_samples = {}
        for hero, stats in results["hero_accuracy"].items():
            sample_count = stats["total"]
            if sample_count not in hero_samples:
                hero_samples[sample_count] = []
            hero_samples[sample_count].append((hero, stats["accuracy"]))

        print(f"{'Sample Size':<15} {'Heroes':<10} {'Avg Accuracy':<15}")
        print("-" * 80)

        for sample_size in sorted(hero_samples.keys(), reverse=True):
            heroes_list = hero_samples[sample_size]
            avg_accuracy = sum(h[1] for h in heroes_list) / len(heroes_list)
            hero_names = ", ".join(h[0] for h in heroes_list[:3])
            if len(heroes_list) > 3:
                hero_names += f" +{len(heroes_list)-3} more"
            print(f"{sample_size:<15} {len(heroes_list):<10} {avg_accuracy:<15.2%}")

        print("\n" + "=" * 80)

    def save_results(self, results: dict, output_path: str):
        """Save validation results to JSON file."""
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\nResults saved to: {output_path}")


def main():
    """Run validation."""
    # Paths
    base_dir = Path(__file__).parent.parent
    candidates_path = base_dir / "output" / "skill_event_candidates.json"
    output_path = base_dir / "output" / "event_pattern_validation_results.json"

    print("Initializing Event Pattern Validator...")
    validator = EventPatternValidator(str(candidates_path))

    print("Running validation against tournament data...")
    results = validator.validate_all_replays()

    # Print report
    validator.print_validation_report(results)

    # Save results
    validator.save_results(results, str(output_path))

    print("\n" + "=" * 80)
    print("VALIDATION COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
