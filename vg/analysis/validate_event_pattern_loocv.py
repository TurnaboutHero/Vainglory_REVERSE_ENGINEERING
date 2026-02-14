"""
Leave-One-Out Cross-Validation for Event Pattern Hero Detection

This script implements proper cross-validation to avoid overfitting:
- For each replay: build profiles from the OTHER 10 replays, test on this one
- This measures true generalization ability, not memorization

Key insight: The original 17.76% accuracy was inflated because we tested on the same
data used to build profiles. LOOCV gives us the real accuracy.
"""

import json
import math
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Any


class LOOCVValidator:
    """Leave-One-Out Cross-Validation for event pattern detection."""

    def __init__(self, candidates_path: str):
        """
        Initialize validator.

        Args:
            candidates_path: Path to skill_event_candidates.json
        """
        self.candidates_data = self._load_candidates(candidates_path)
        self.event_codes = ["0x44", "0x43", "0x0E", "0x65", "0x13", "0x76"]

    def _load_candidates(self, path: str) -> dict:
        """Load skill event candidates JSON."""
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def build_profiles_excluding_replay(self, exclude_replay: str) -> Dict[str, Dict[str, float]]:
        """
        Build hero profiles from all replays EXCEPT the specified one.

        Args:
            exclude_replay: Name of replay to exclude from profile building

        Returns:
            Dictionary of hero_name -> event_ratios
        """
        hero_events = defaultdict(lambda: defaultdict(int))
        hero_counts = defaultdict(int)

        for replay in self.candidates_data.get("detailed_replays", []):
            if replay["replay_name"] == exclude_replay:
                continue  # Skip this replay

            for player_name, player_data in replay["players"].items():
                hero_name = player_data["hero_name"]
                if hero_name == "Unknown":
                    continue

                hero_counts[hero_name] += 1
                for event_code, count in player_data["candidate_events"].items():
                    hero_events[hero_name][event_code] += count

        # Build normalized profiles
        profiles = {}
        for hero_name, events in hero_events.items():
            total = sum(events.values())
            if total > 0:
                profiles[hero_name] = {
                    code: events.get(code, 0) / total
                    for code in self.event_codes
                }
            else:
                profiles[hero_name] = {code: 0.0 for code in self.event_codes}

        return profiles

    def normalize_events(self, events: Dict[str, int]) -> Dict[str, float]:
        """Normalize event counts to ratios."""
        total = sum(events.values())
        if total == 0:
            return {code: 0.0 for code in self.event_codes}
        return {code: events.get(code, 0) / total for code in self.event_codes}

    def cosine_similarity(self, pattern1: Dict[str, float], pattern2: Dict[str, float]) -> float:
        """Calculate cosine similarity between two patterns."""
        all_codes = set(pattern1.keys()) | set(pattern2.keys())

        dot_product = 0.0
        magnitude1 = 0.0
        magnitude2 = 0.0

        for code in all_codes:
            val1 = pattern1.get(code, 0.0)
            val2 = pattern2.get(code, 0.0)
            dot_product += val1 * val2
            magnitude1 += val1 * val1
            magnitude2 += val2 * val2

        magnitude1 = math.sqrt(magnitude1)
        magnitude2 = math.sqrt(magnitude2)

        if magnitude1 == 0.0 or magnitude2 == 0.0:
            return 0.0

        return dot_product / (magnitude1 * magnitude2)

    def detect_hero(self, player_events: Dict[str, int], profiles: Dict[str, Dict[str, float]]) -> Tuple[str, float]:
        """
        Detect hero using provided profiles.

        Args:
            player_events: Event counts for this player
            profiles: Hero profiles (built from OTHER replays)

        Returns:
            (predicted_hero, confidence)
        """
        player_pattern = self.normalize_events(player_events)

        best_hero = "Unknown"
        best_score = 0.0

        for hero_name, hero_pattern in profiles.items():
            score = self.cosine_similarity(player_pattern, hero_pattern)
            if score > best_score:
                best_score = score
                best_hero = hero_name

        return best_hero, best_score

    def run_loocv(self) -> Dict[str, Any]:
        """
        Run Leave-One-Out Cross-Validation.

        For each replay:
        1. Build profiles from the OTHER 10 replays
        2. Test detection on this replay's players
        3. Record accuracy

        Returns:
            Comprehensive validation results
        """
        results = {
            "total_players": 0,
            "correct_predictions": 0,
            "incorrect_predictions": 0,
            "unknown_heroes": 0,
            "per_replay_accuracy": {},
            "predictions": [],
            "hero_accuracy": {},
            "confusion_matrix": {}
        }

        replays = self.candidates_data.get("detailed_replays", [])
        print(f"\nRunning LOOCV on {len(replays)} replays...")
        print("=" * 70)

        for i, test_replay in enumerate(replays):
            test_replay_name = test_replay["replay_name"]
            print(f"\n[{i+1}/{len(replays)}] Testing on: {test_replay_name}")

            # Build profiles excluding this replay
            profiles = self.build_profiles_excluding_replay(test_replay_name)
            print(f"  Profiles built from other replays: {len(profiles)} heroes")

            replay_correct = 0
            replay_total = 0

            for player_name, player_data in test_replay["players"].items():
                true_hero = player_data["hero_name"]
                player_events = player_data["candidate_events"]

                if true_hero == "Unknown":
                    results["unknown_heroes"] += 1
                    continue

                # Check if this hero has a profile (from other replays)
                if true_hero not in profiles:
                    # This hero only appears in this replay - can't test
                    print(f"  [SKIP] {player_name} ({true_hero}) - hero only in this replay")
                    continue

                # Detect hero using profiles from OTHER replays
                predicted_hero, confidence = self.detect_hero(player_events, profiles)

                is_correct = (predicted_hero == true_hero)
                results["total_players"] += 1
                replay_total += 1

                if is_correct:
                    results["correct_predictions"] += 1
                    replay_correct += 1
                else:
                    results["incorrect_predictions"] += 1

                # Store prediction
                results["predictions"].append({
                    "replay": test_replay_name,
                    "player": player_name,
                    "true_hero": true_hero,
                    "predicted_hero": predicted_hero,
                    "confidence": confidence,
                    "correct": is_correct
                })

                # Update confusion matrix
                if true_hero not in results["confusion_matrix"]:
                    results["confusion_matrix"][true_hero] = {}
                if predicted_hero not in results["confusion_matrix"][true_hero]:
                    results["confusion_matrix"][true_hero][predicted_hero] = 0
                results["confusion_matrix"][true_hero][predicted_hero] += 1

                # Update hero accuracy
                if true_hero not in results["hero_accuracy"]:
                    results["hero_accuracy"][true_hero] = {"total": 0, "correct": 0}
                results["hero_accuracy"][true_hero]["total"] += 1
                if is_correct:
                    results["hero_accuracy"][true_hero]["correct"] += 1

            # Per-replay accuracy
            replay_acc = replay_correct / replay_total if replay_total > 0 else 0.0
            results["per_replay_accuracy"][test_replay_name] = {
                "correct": replay_correct,
                "total": replay_total,
                "accuracy": replay_acc
            }
            print(f"  Replay accuracy: {replay_correct}/{replay_total} ({replay_acc:.2%})")

        # Calculate final accuracy
        results["accuracy"] = (
            results["correct_predictions"] / results["total_players"]
            if results["total_players"] > 0 else 0.0
        )

        # Calculate per-hero accuracy
        for hero, stats in results["hero_accuracy"].items():
            stats["accuracy"] = stats["correct"] / stats["total"] if stats["total"] > 0 else 0.0

        return results

    def print_report(self, results: Dict[str, Any]):
        """Print detailed validation report."""
        print("\n" + "=" * 80)
        print("LEAVE-ONE-OUT CROSS-VALIDATION REPORT")
        print("=" * 80)

        print("\nOVERALL STATISTICS:")
        print("-" * 80)
        print(f"Total Players Tested:     {results['total_players']}")
        print(f"Correct Predictions:      {results['correct_predictions']}")
        print(f"Incorrect Predictions:    {results['incorrect_predictions']}")
        print(f"Skipped (Unknown/Single): {results['unknown_heroes']}")
        print(f"\n*** LOOCV ACCURACY:       {results['accuracy']:.2%} ***")

        print("\n" + "=" * 80)
        print("PER-REPLAY ACCURACY:")
        print("=" * 80)
        print(f"{'Replay':<45} {'Correct':<10} {'Total':<10} {'Accuracy':<10}")
        print("-" * 80)

        for replay_name, stats in sorted(results["per_replay_accuracy"].items()):
            print(f"{replay_name[:44]:<45} {stats['correct']:<10} {stats['total']:<10} {stats['accuracy']:.2%}")

        print("\n" + "=" * 80)
        print("PER-HERO ACCURACY (sorted by total samples):")
        print("=" * 80)
        print(f"{'Hero':<20} {'Correct':<10} {'Total':<10} {'Accuracy':<10}")
        print("-" * 80)

        sorted_heroes = sorted(
            results["hero_accuracy"].items(),
            key=lambda x: x[1]["total"],
            reverse=True
        )

        for hero, stats in sorted_heroes:
            print(f"{hero:<20} {stats['correct']:<10} {stats['total']:<10} {stats['accuracy']:.2%}")

        # Top confusions
        print("\n" + "=" * 80)
        print("TOP 10 CONFUSION PAIRS:")
        print("=" * 80)

        confusions = []
        for true_hero, predictions in results["confusion_matrix"].items():
            for pred_hero, count in predictions.items():
                if true_hero != pred_hero:
                    confusions.append((true_hero, pred_hero, count))

        confusions.sort(key=lambda x: x[2], reverse=True)

        print(f"{'True Hero':<20} {'Predicted':<20} {'Count':<10}")
        print("-" * 80)
        for true_hero, pred_hero, count in confusions[:10]:
            print(f"{true_hero:<20} {pred_hero:<20} {count}")

        # Analysis of incorrect predictions
        print("\n" + "=" * 80)
        print("HIGH CONFIDENCE MISTAKES (>0.90):")
        print("=" * 80)

        high_conf_wrong = [
            p for p in results["predictions"]
            if not p["correct"] and p["confidence"] > 0.90
        ]
        high_conf_wrong.sort(key=lambda x: x["confidence"], reverse=True)

        if high_conf_wrong:
            print(f"{'True':<15} {'Predicted':<15} {'Conf':<10} {'Player':<20}")
            print("-" * 80)
            for p in high_conf_wrong[:10]:
                print(f"{p['true_hero']:<15} {p['predicted_hero']:<15} {p['confidence']:.4f}    {p['player']:<20}")
        else:
            print("No high-confidence mistakes found.")

        print("\n" + "=" * 80)

    def save_results(self, results: Dict[str, Any], output_path: str):
        """Save results to JSON file."""
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"Results saved to: {output_path}")


def main():
    """Run LOOCV validation."""
    base_dir = Path(__file__).parent.parent
    candidates_path = base_dir / "output" / "skill_event_candidates.json"
    output_path = base_dir / "output" / "loocv_validation_results.json"

    print("=" * 80)
    print("LEAVE-ONE-OUT CROSS-VALIDATION")
    print("=" * 80)
    print("\nThis validation builds hero profiles from N-1 replays and tests on")
    print("the remaining replay. This measures TRUE generalization, not memorization.")
    print("\nPrevious validation (same data train/test): 17.76% accuracy")
    print("This validation will show real accuracy...")

    validator = LOOCVValidator(str(candidates_path))
    results = validator.run_loocv()

    validator.print_report(results)
    validator.save_results(results, str(output_path))

    print("\n" + "=" * 80)
    print("VALIDATION COMPLETE")
    print("=" * 80)

    return results


if __name__ == "__main__":
    main()
