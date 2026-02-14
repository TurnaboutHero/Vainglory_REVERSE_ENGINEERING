"""
LOOCV Validation for Signature-Based Hero Detection

Tests the signature-based detection method using Leave-One-Out Cross-Validation.
"""

import json
import sys
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Any, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent / "core"))

try:
    from signature_detector import SignatureDetector, HERO_SIGNATURES
except ImportError:
    from vg.core.signature_detector import SignatureDetector, HERO_SIGNATURES


def read_all_frames(frame_dir: Path, replay_name: str) -> bytes:
    """Read all frames for a replay."""
    frames = list(frame_dir.glob(f"{replay_name}.*.vgr"))
    frames.sort(key=lambda p: int(p.stem.split(".")[-1]) if p.stem.split(".")[-1].isdigit() else 0)
    return b"".join(f.read_bytes() for f in frames)


def extract_all_events(data: bytes, entity_id: int) -> Dict[int, int]:
    """Extract all events for an entity, returning int keys."""
    base = entity_id.to_bytes(2, 'little') + b'\x00\x00'
    events = Counter()

    idx = 0
    while True:
        idx = data.find(base, idx)
        if idx == -1:
            break
        if idx + 4 < len(data):
            events[data[idx + 4]] += 1
        idx += 1

    return dict(events)


def load_truth(path: str) -> Dict:
    """Load truth data."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {m["replay_name"]: m for m in data.get("matches", []) if m.get("replay_name")}


def build_signatures_excluding_replay(
    replays_dir: Path,
    truth_map: Dict,
    exclude_replay: str,
    min_concentration: float = 0.5
) -> Dict[str, List[Tuple[int, float]]]:
    """
    Build hero signatures from all replays EXCEPT the excluded one.

    Returns dynamic signatures based on event concentration.
    """
    # Collect all events per hero
    hero_events = defaultdict(lambda: Counter())
    hero_counts = defaultdict(int)
    event_totals = Counter()

    try:
        from vgr_parser import VGRParser
    except ImportError:
        from vg.core.vgr_parser import VGRParser

    for vgr_file in replays_dir.rglob("*.0.vgr"):
        if vgr_file.name.startswith("._") or "__MACOSX" in vgr_file.parts:
            continue

        try:
            parser = VGRParser(str(vgr_file), auto_truth=False)
            parsed = parser.parse()
            replay_name = parsed["replay_name"]

            if replay_name == exclude_replay:
                continue  # Skip test replay

            truth_match = truth_map.get(replay_name)
            if not truth_match:
                continue

            all_data = read_all_frames(vgr_file.parent, replay_name)
            players = parsed["teams"]["left"] + parsed["teams"]["right"]
            truth_players = truth_match.get("players", {})

            for player in players:
                entity_id = player.get("entity_id")
                player_name = player.get("name")
                if entity_id is None:
                    continue

                hero_name = truth_players.get(player_name, {}).get("hero_name", "Unknown")
                if hero_name == "Unknown":
                    continue

                events = extract_all_events(all_data, entity_id)
                hero_events[hero_name] += Counter(events)
                hero_counts[hero_name] += 1

                for code, count in events.items():
                    event_totals[code] += count

        except Exception:
            pass

    # Build signatures from concentrated events
    signatures = defaultdict(list)
    event_hero_dist = defaultdict(lambda: Counter())

    for hero, events in hero_events.items():
        for code, count in events.items():
            event_hero_dist[code][hero] += count

    for code, hero_dist in event_hero_dist.items():
        total = sum(hero_dist.values())
        if total < 50:  # Skip rare events
            continue

        for hero, count in hero_dist.items():
            concentration = count / total
            if concentration >= min_concentration:
                signatures[hero].append((code, concentration))

    # Sort by concentration
    for hero in signatures:
        signatures[hero].sort(key=lambda x: -x[1])
        signatures[hero] = signatures[hero][:5]  # Top 5 signatures per hero

    return dict(signatures)


def run_loocv(replays_dir: Path, truth_path: Path) -> Dict[str, Any]:
    """Run LOOCV validation for signature detection."""
    truth_map = load_truth(str(truth_path))

    try:
        from vgr_parser import VGRParser
    except ImportError:
        from vg.core.vgr_parser import VGRParser

    results = {
        "total_players": 0,
        "correct_predictions": 0,
        "with_signature_correct": 0,
        "with_signature_total": 0,
        "without_signature_total": 0,
        "predictions": [],
        "hero_accuracy": defaultdict(lambda: {"total": 0, "correct": 0})
    }

    # Get all replay files
    replay_files = [f for f in replays_dir.rglob("*.0.vgr")
                    if not f.name.startswith("._") and "__MACOSX" not in str(f)]

    print(f"\nRunning Signature-based LOOCV on {len(replay_files)} replays...")
    print("=" * 70)

    for i, vgr_file in enumerate(replay_files):
        try:
            parser = VGRParser(str(vgr_file), auto_truth=False)
            parsed = parser.parse()
            test_replay = parsed["replay_name"]

            truth_match = truth_map.get(test_replay)
            if not truth_match:
                continue

            print(f"\n[{i+1}/{len(replay_files)}] Testing: {test_replay[:50]}...")

            # Build signatures excluding this replay
            dynamic_sigs = build_signatures_excluding_replay(
                replays_dir, truth_map, test_replay
            )

            # Create detector with dynamic signatures
            detector = SignatureDetector()
            detector.signatures = dynamic_sigs

            # Test on this replay
            all_data = read_all_frames(vgr_file.parent, test_replay)
            players = parsed["teams"]["left"] + parsed["teams"]["right"]
            truth_players = truth_match.get("players", {})

            replay_correct = 0
            replay_total = 0

            for player in players:
                entity_id = player.get("entity_id")
                player_name = player.get("name")
                if entity_id is None:
                    continue

                true_hero = truth_players.get(player_name, {}).get("hero_name", "Unknown")
                if true_hero == "Unknown":
                    continue

                events = extract_all_events(all_data, entity_id)
                predicted, score, explanation = detector.detect_hero_best(events)

                has_signature = true_hero in dynamic_sigs
                is_correct = (predicted == true_hero)

                results["total_players"] += 1
                replay_total += 1
                results["hero_accuracy"][true_hero]["total"] += 1

                if has_signature:
                    results["with_signature_total"] += 1
                    if is_correct:
                        results["with_signature_correct"] += 1
                else:
                    results["without_signature_total"] += 1

                if is_correct:
                    results["correct_predictions"] += 1
                    results["hero_accuracy"][true_hero]["correct"] += 1
                    replay_correct += 1

                results["predictions"].append({
                    "replay": test_replay,
                    "player": player_name,
                    "true_hero": true_hero,
                    "predicted": predicted,
                    "score": score,
                    "has_signature": has_signature,
                    "correct": is_correct
                })

            acc = replay_correct / replay_total if replay_total > 0 else 0
            print(f"   Replay accuracy: {replay_correct}/{replay_total} ({acc:.2%})")

        except Exception as e:
            print(f"   Error: {e}")

    # Calculate overall accuracy
    results["accuracy"] = (
        results["correct_predictions"] / results["total_players"]
        if results["total_players"] > 0 else 0.0
    )

    results["with_signature_accuracy"] = (
        results["with_signature_correct"] / results["with_signature_total"]
        if results["with_signature_total"] > 0 else 0.0
    )

    return results


def print_report(results: Dict):
    """Print validation report."""
    print("\n" + "=" * 80)
    print("SIGNATURE-BASED DETECTION - LOOCV REPORT")
    print("=" * 80)

    print("\nOVERALL RESULTS:")
    print("-" * 80)
    print(f"Total Players Tested:      {results['total_players']}")
    print(f"Correct Predictions:       {results['correct_predictions']}")
    print(f"\n*** OVERALL ACCURACY:      {results['accuracy']:.2%} ***")

    print("\nBREAKDOWN BY SIGNATURE AVAILABILITY:")
    print("-" * 80)
    print(f"Players WITH signature:    {results['with_signature_total']} "
          f"({results['with_signature_correct']} correct, "
          f"{results['with_signature_accuracy']:.2%})")
    print(f"Players WITHOUT signature: {results['without_signature_total']}")

    print("\nPER-HERO ACCURACY:")
    print("-" * 80)
    print(f"{'Hero':<20} {'Correct':<10} {'Total':<10} {'Accuracy':<10}")
    print("-" * 80)

    sorted_heroes = sorted(
        results["hero_accuracy"].items(),
        key=lambda x: x[1]["total"],
        reverse=True
    )

    for hero, stats in sorted_heroes:
        acc = stats["correct"] / stats["total"] if stats["total"] > 0 else 0
        print(f"{hero:<20} {stats['correct']:<10} {stats['total']:<10} {acc:.2%}")


def main():
    """Run validation."""
    base_dir = Path(__file__).parent.parent
    replays_dir = Path(r"D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays")
    truth_path = base_dir / "output" / "tournament_truth.json"
    output_path = base_dir / "output" / "signature_loocv_results.json"

    print("=" * 80)
    print("SIGNATURE-BASED HERO DETECTION - LOOCV VALIDATION")
    print("=" * 80)
    print("\nThis uses hero-specific 'signature events' for detection.")
    print("Signatures are built dynamically, excluding the test replay.")

    results = run_loocv(replays_dir, truth_path)

    print_report(results)

    # Save results
    # Convert defaultdict to dict for JSON
    results["hero_accuracy"] = dict(results["hero_accuracy"])

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nResults saved to: {output_path}")


if __name__ == "__main__":
    main()
