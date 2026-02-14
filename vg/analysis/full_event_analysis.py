"""
Full Event Code Analysis for Hero Detection

Previous approach used only 6 event codes (0x44, 0x43, 0x0E, 0x65, 0x13, 0x76)
and achieved only 4.17% LOOCV accuracy.

This script analyzes ALL event codes to find hero-discriminative patterns.
Goal: Find event codes that are unique to specific heroes or hero classes.
"""

import json
import sys
from pathlib import Path
from collections import Counter, defaultdict
from typing import Dict, List, Any, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent / "core"))

try:
    from vgr_parser import VGRParser
except ImportError:
    from vg.core.vgr_parser import VGRParser


def read_all_frames(frame_dir: Path, replay_name: str) -> bytes:
    """Read all frames for a replay in order."""
    frames = list(frame_dir.glob(f"{replay_name}.*.vgr"))

    def frame_index(path: Path) -> int:
        try:
            return int(path.stem.split(".")[-1])
        except ValueError:
            return 0

    frames.sort(key=frame_index)
    return b"".join(frame.read_bytes() for frame in frames)


def load_truth(path: str) -> Dict[str, Any]:
    """Load truth data."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {m.get("replay_name"): m for m in data.get("matches", []) if m.get("replay_name")}


def extract_all_events_for_entity(data: bytes, entity_id: int) -> Counter:
    """
    Extract ALL event codes for a given entity.

    Returns counter of event_code -> count
    """
    base = entity_id.to_bytes(2, 'little') + b'\x00\x00'
    event_counts = Counter()

    idx = 0
    while True:
        idx = data.find(base, idx)
        if idx == -1:
            break
        if idx + 4 < len(data):
            action_code = data[idx + 4]
            event_counts[action_code] += 1
        idx += 1

    return event_counts


def analyze_all_events(replays_dir: Path, truth_path: Path) -> Dict[str, Any]:
    """
    Analyze ALL event codes across all replays.

    Find which event codes are most discriminative for hero detection.
    """
    truth_map = load_truth(str(truth_path))

    # Per-hero event distributions
    hero_events = defaultdict(lambda: Counter())
    hero_sample_counts = Counter()

    # Global event statistics
    all_event_counts = Counter()
    event_hero_distribution = defaultdict(lambda: Counter())  # event -> hero -> count

    # Process replays
    for vgr_file in replays_dir.rglob("*.0.vgr"):
        if vgr_file.name.startswith("._") or "__MACOSX" in vgr_file.parts:
            continue

        try:
            parser = VGRParser(str(vgr_file), auto_truth=False)
            parsed = parser.parse()
            replay_name = parsed["replay_name"]

            truth_match = truth_map.get(replay_name)
            if not truth_match:
                continue

            # Read all frames
            all_data = read_all_frames(vgr_file.parent, replay_name)

            # Get players
            players = []
            for team in ("left", "right"):
                players.extend(parsed["teams"][team])

            truth_players = truth_match.get("players", {})

            for player in players:
                entity_id = player.get("entity_id")
                player_name = player.get("name")

                if entity_id is None:
                    continue

                truth_player = truth_players.get(player_name, {})
                hero_name = truth_player.get("hero_name", "Unknown")

                if hero_name == "Unknown":
                    continue

                # Extract ALL events for this entity
                events = extract_all_events_for_entity(all_data, entity_id)

                # Aggregate
                hero_events[hero_name] += events
                hero_sample_counts[hero_name] += 1
                all_event_counts += events

                for event_code, count in events.items():
                    event_hero_distribution[event_code][hero_name] += count

            print(f"[OK] {replay_name}")

        except Exception as e:
            print(f"[ERR] {vgr_file}: {e}")

    # Analyze event discriminativeness
    # For each event code, calculate how concentrated it is among heroes
    # Higher concentration = more discriminative

    event_analysis = []

    for event_code, hero_dist in event_hero_distribution.items():
        total_count = sum(hero_dist.values())
        num_heroes = len(hero_dist)

        if total_count < 10 or num_heroes < 2:
            continue

        # Calculate entropy (lower = more concentrated = more discriminative)
        probabilities = [count / total_count for count in hero_dist.values()]
        entropy = -sum(p * (p if p == 0 else __import__('math').log2(p)) for p in probabilities if p > 0)

        # Calculate concentration ratio (top hero / total)
        top_hero, top_count = hero_dist.most_common(1)[0]
        concentration = top_count / total_count

        # Find heroes that use this event significantly more than average
        avg_per_hero = total_count / num_heroes
        distinctive_heroes = [
            (hero, count, count / avg_per_hero)
            for hero, count in hero_dist.most_common(5)
            if count > avg_per_hero * 2  # At least 2x average
        ]

        event_analysis.append({
            "event_code": f"0x{event_code:02X}",
            "total_count": total_count,
            "num_heroes": num_heroes,
            "entropy": round(entropy, 4),
            "concentration": round(concentration, 4),
            "top_hero": top_hero,
            "distinctive_heroes": [
                {"hero": h, "count": c, "ratio": round(r, 2)}
                for h, c, r in distinctive_heroes
            ]
        })

    # Sort by concentration (most discriminative first)
    event_analysis.sort(key=lambda x: -x["concentration"])

    # Find rare events (appear for only few heroes)
    rare_events = [e for e in event_analysis if e["num_heroes"] <= 5]

    # Find common but concentrated events
    concentrated_events = [
        e for e in event_analysis
        if e["num_heroes"] >= 10 and e["concentration"] > 0.3
    ]

    return {
        "summary": {
            "total_heroes": len(hero_sample_counts),
            "total_event_codes": len(all_event_counts),
            "hero_samples": dict(hero_sample_counts)
        },
        "all_events": event_analysis[:50],  # Top 50 by concentration
        "rare_events": rare_events[:20],
        "concentrated_events": concentrated_events[:20],
        "hero_event_profiles": {
            hero: dict(events.most_common(20))
            for hero, events in hero_events.items()
        }
    }


def print_report(results: Dict[str, Any]):
    """Print analysis report."""
    print("\n" + "=" * 80)
    print("FULL EVENT CODE ANALYSIS REPORT")
    print("=" * 80)

    print(f"\nTotal Heroes: {results['summary']['total_heroes']}")
    print(f"Total Event Codes Found: {results['summary']['total_event_codes']}")

    print("\n" + "=" * 80)
    print("RARE EVENTS (appear for <= 5 heroes) - HIGHLY DISCRIMINATIVE:")
    print("=" * 80)
    print(f"{'Code':<10} {'Total':<10} {'Heroes':<10} {'Top Hero':<20} {'Conc':<10}")
    print("-" * 80)

    for e in results["rare_events"][:15]:
        print(f"{e['event_code']:<10} {e['total_count']:<10} {e['num_heroes']:<10} {e['top_hero']:<20} {e['concentration']:.2%}")

    print("\n" + "=" * 80)
    print("CONCENTRATED EVENTS (common but discriminative):")
    print("=" * 80)
    print(f"{'Code':<10} {'Total':<10} {'Heroes':<10} {'Top Hero':<20} {'Conc':<10}")
    print("-" * 80)

    for e in results["concentrated_events"][:15]:
        distinctive = ", ".join([f"{d['hero']}({d['ratio']}x)" for d in e["distinctive_heroes"][:3]])
        print(f"{e['event_code']:<10} {e['total_count']:<10} {e['num_heroes']:<10} {e['top_hero']:<20} {e['concentration']:.2%}")
        if distinctive:
            print(f"           Distinctive: {distinctive}")

    print("\n" + "=" * 80)
    print("SAMPLE HERO EVENT PROFILES (top events):")
    print("=" * 80)

    # Show a few hero profiles
    for hero in list(results["hero_event_profiles"].keys())[:5]:
        profile = results["hero_event_profiles"][hero]
        top_5 = list(profile.items())[:5]
        events_str = ", ".join([f"0x{k:02X}:{v}" for k, v in top_5])
        print(f"{hero:<20}: {events_str}")


def main():
    """Run full event analysis."""
    base_dir = Path(__file__).parent.parent
    replays_dir = Path(r"D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays")
    truth_path = base_dir / "output" / "tournament_truth.json"
    output_path = base_dir / "output" / "full_event_analysis.json"

    print("=" * 80)
    print("FULL EVENT CODE ANALYSIS")
    print("=" * 80)
    print("\nAnalyzing ALL event codes to find hero-discriminative patterns...")
    print("This may take a moment...\n")

    results = analyze_all_events(replays_dir, truth_path)

    print_report(results)

    # Save results
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nResults saved to: {output_path}")

    return results


if __name__ == "__main__":
    main()
