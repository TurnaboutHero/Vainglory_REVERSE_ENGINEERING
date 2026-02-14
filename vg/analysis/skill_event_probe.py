#!/usr/bin/env python3
"""
Skill Event Probe for Vainglory replays.
Analyzes tournament replays to find skill usage event code candidates.

Candidate event codes: 0x13, 0x43, 0x44, 0x65, 0x76, 0x0C-0x0E
Event structure (RE Notes):
    Offset  Size  Description
    0x00    2B    Entity ID (Little Endian)
    0x02    2B    Padding (00 00)
    0x04    1B    Action Type
    0x05    N     Payload (variable length)
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "core"))

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    # Fallback implementations
    class np:
        @staticmethod
        def mean(lst):
            return sum(lst) / len(lst) if lst else 0
        @staticmethod
        def std(lst):
            if not lst:
                return 0
            avg = sum(lst) / len(lst)
            return (sum((x - avg) ** 2 for x in lst) / len(lst)) ** 0.5
        @staticmethod
        def median(lst):
            if not lst:
                return 0
            s = sorted(lst)
            n = len(s)
            return (s[n//2] + s[(n-1)//2]) / 2

try:
    from vgr_mapping import HERO_NAME_TO_ID
    from vgr_parser import VGRParser
except ImportError:
    from vg.core.vgr_mapping import HERO_NAME_TO_ID
    from vg.core.vgr_parser import VGRParser


# Skill event candidate codes
SKILL_EVENT_CANDIDATES = [0x13, 0x43, 0x44, 0x65, 0x76, 0x0C, 0x0D, 0x0E]


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
    """Load truth data from JSON file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    matches = data.get("matches", [])
    return {m.get("replay_name"): m for m in matches if m.get("replay_name")}


def analyze_skill_events(
    replay_path: Path,
    truth_data: Dict,
    all_data: bytes,
    players: List[Dict],
) -> Dict[str, Any]:
    """
    Analyze skill-related events for a specific replay.

    Args:
        replay_path: Path to the .0.vgr file
        truth_data: Truth data for this match
        all_data: Combined binary data from all frames
        players: List of player data with entity IDs

    Returns:
        Dictionary with per-player event analysis
    """
    results = {}

    for player in players:
        entity_id = player.get("entity_id")
        player_name = player.get("name")

        if entity_id is None:
            continue

        # Count all events for this player
        base = entity_id.to_bytes(2, 'little') + b'\x00\x00'
        event_counts = Counter()

        idx = 0
        while True:
            idx = all_data.find(base, idx)
            if idx == -1:
                break
            if idx + 4 < len(all_data):
                action_code = all_data[idx + 4]
                event_counts[action_code] += 1
            idx += 1

        # Extract candidate event counts
        candidate_counts = {}
        for code in SKILL_EVENT_CANDIDATES:
            count = event_counts.get(code, 0)
            if count > 0:
                candidate_counts[f"0x{code:02X}"] = count

        # Get truth stats
        truth_players = truth_data.get("players", {})
        truth_player = truth_players.get(player_name, {})

        results[player_name] = {
            "entity_id": entity_id,
            "hero_name": truth_player.get("hero_name", "Unknown"),
            "candidate_events": candidate_counts,
            "truth": {
                "kills": truth_player.get("kills", 0),
                "deaths": truth_player.get("deaths", 0),
                "assists": truth_player.get("assists", 0),
            }
        }

    return results


def find_skill_event_candidates(
    replays_dir: Path,
    truth_path: Path
) -> Dict[str, Any]:
    """
    Scan all replays to find skill event candidates.

    Args:
        replays_dir: Directory containing tournament replays
        truth_path: Path to tournament_truth.json

    Returns:
        Analysis results with candidate recommendations
    """
    truth_map = load_truth(str(truth_path))

    # Aggregate statistics
    event_totals = Counter()  # Total occurrences per event code
    event_player_counts = defaultdict(list)  # Per-player counts for each event
    hero_event_patterns = defaultdict(lambda: Counter())  # Events per hero

    replay_results = []
    total_players = 0

    # Find all .0.vgr files
    for vgr_file in replays_dir.rglob("*.0.vgr"):
        if vgr_file.name.startswith("._") or "__MACOSX" in vgr_file.parts:
            continue

        try:
            parser = VGRParser(str(vgr_file), auto_truth=False)
            parsed = parser.parse()
            replay_name = parsed["replay_name"]

            # Get truth data
            truth_match = truth_map.get(replay_name)
            if not truth_match:
                print(f"[SKIP] No truth data for {replay_name}")
                continue

            # Read all frames
            all_data = read_all_frames(vgr_file.parent, replay_name)

            # Get players from both teams
            players = []
            for team in ("left", "right"):
                players.extend(parsed["teams"][team])

            # Analyze this replay
            replay_analysis = analyze_skill_events(
                vgr_file,
                truth_match,
                all_data,
                players
            )

            replay_results.append({
                "replay_name": replay_name,
                "players": replay_analysis
            })

            # Aggregate statistics
            for player_name, player_data in replay_analysis.items():
                total_players += 1
                hero_name = player_data["hero_name"]

                for event_code, count in player_data["candidate_events"].items():
                    event_totals[event_code] += count
                    event_player_counts[event_code].append(count)
                    hero_event_patterns[hero_name][event_code] += count

            print(f"[OK] Analyzed: {replay_name}")

        except Exception as e:
            print(f"[ERR] Error analyzing {vgr_file}: {e}")

    # Calculate statistics for each candidate
    candidates = []

    for code in SKILL_EVENT_CANDIDATES:
        code_str = f"0x{code:02X}"

        if code_str not in event_totals:
            continue

        counts = event_player_counts[code_str]
        if not counts:
            continue

        avg_per_player = np.mean(counts)
        std_per_player = np.std(counts)
        median_per_player = np.median(counts)

        # Correlation with hero (simplified - check variance across heroes)
        hero_averages = []
        for hero, event_counter in hero_event_patterns.items():
            if code_str in event_counter:
                hero_averages.append(event_counter[code_str])

        hero_correlation = np.std(hero_averages) / (avg_per_player + 0.1) if hero_averages else 0

        # Confidence assessment
        # High confidence: consistent counts across players, good hero correlation
        if avg_per_player > 100 and std_per_player < avg_per_player * 0.5:
            confidence = "HIGH"
        elif avg_per_player > 50 and std_per_player < avg_per_player:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        candidates.append({
            "event_code": code_str,
            "total_occurrences": event_totals[code_str],
            "avg_per_player": round(avg_per_player, 2),
            "median_per_player": round(median_per_player, 2),
            "std_per_player": round(std_per_player, 2),
            "hero_correlation": round(hero_correlation, 4),
            "sample_size": len(counts),
            "confidence": confidence
        })

    # Sort by average per player (descending)
    candidates.sort(key=lambda x: -x["avg_per_player"])

    # Generate recommendation
    recommendation = generate_recommendation(candidates)

    return {
        "summary": {
            "total_replays": len(replay_results),
            "total_players": total_players,
            "candidate_codes": len(candidates)
        },
        "candidates": candidates,
        "per_hero_patterns": correlate_events_with_heroes(
            hero_event_patterns,
            total_players
        ),
        "recommendation": recommendation,
        "detailed_replays": replay_results
    }


def correlate_events_with_heroes(
    hero_event_patterns: Dict[str, Counter],
    total_players: int
) -> Dict[str, Any]:
    """
    Analyze correlation between event patterns and specific heroes.

    Args:
        hero_event_patterns: Event counts per hero
        total_players: Total number of players analyzed

    Returns:
        Correlation analysis results
    """
    results = {}

    for hero, event_counter in hero_event_patterns.items():
        # Find top events for this hero
        top_events = event_counter.most_common(10)

        results[hero] = {
            "top_events": [
                {
                    "event_code": code,
                    "count": count
                }
                for code, count in top_events
            ],
            "total_events": sum(event_counter.values())
        }

    return results


def generate_recommendation(candidates: List[Dict[str, Any]]) -> str:
    """Generate a recommendation based on candidate analysis."""
    if not candidates:
        return "No significant skill event candidates found. Try expanding the candidate list."

    high_confidence = [c for c in candidates if c["confidence"] == "HIGH"]
    medium_confidence = [c for c in candidates if c["confidence"] == "MEDIUM"]

    recommendation = []

    if high_confidence:
        codes = ", ".join([c["event_code"] for c in high_confidence[:3]])
        recommendation.append(
            f"HIGH CONFIDENCE: {codes} - These events show consistent "
            f"frequency across players and good correlation patterns."
        )

    if medium_confidence:
        codes = ", ".join([c["event_code"] for c in medium_confidence[:3]])
        recommendation.append(
            f"MEDIUM CONFIDENCE: {codes} - These events are promising but "
            f"show some variance. Requires further validation."
        )

    if not high_confidence and not medium_confidence:
        recommendation.append(
            "LOW CONFIDENCE: All candidates show high variance or low frequency. "
            "Skill events may require different candidate codes or detection method."
        )

    recommendation.append(
        "\nNext steps: Analyze payload structure and cross-reference with "
        "known skill cooldowns/usage patterns."
    )

    return "\n".join(recommendation)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="VGR Skill Event Probe - Find skill usage event candidates"
    )
    parser.add_argument(
        "--replays",
        required=True,
        help="Path to tournament replays directory"
    )
    parser.add_argument(
        "--truth",
        required=True,
        help="Path to tournament_truth.json"
    )
    parser.add_argument(
        "--output",
        default="skill_event_probe_output.json",
        help="Output JSON path (default: skill_event_probe_output.json)"
    )

    args = parser.parse_args()

    replays_dir = Path(args.replays)
    truth_path = Path(args.truth)

    if not replays_dir.exists():
        print(f"Error: Replays directory not found: {replays_dir}")
        return 1

    if not truth_path.exists():
        print(f"Error: Truth file not found: {truth_path}")
        return 1

    print(f"=== Skill Event Probe ===")
    print(f"Replays: {replays_dir}")
    print(f"Truth: {truth_path}")
    print(f"Candidate codes: {', '.join([f'0x{c:02X}' for c in SKILL_EVENT_CANDIDATES])}")
    print()

    # Run analysis
    results = find_skill_event_candidates(replays_dir, truth_path)

    # Print summary
    print(f"\n=== Analysis Summary ===")
    print(f"Replays analyzed: {results['summary']['total_replays']}")
    print(f"Players analyzed: {results['summary']['total_players']}")
    print(f"Candidate codes found: {results['summary']['candidate_codes']}")
    print()

    print("=== Candidate Event Codes ===")
    for candidate in results["candidates"][:10]:
        print(
            f"  {candidate['event_code']}: "
            f"avg={candidate['avg_per_player']:.1f}, "
            f"median={candidate['median_per_player']:.1f}, "
            f"std={candidate['std_per_player']:.1f}, "
            f"hero_corr={candidate['hero_correlation']:.3f}, "
            f"confidence={candidate['confidence']}"
        )
    print()

    print("=== Recommendation ===")
    print(results["recommendation"])
    print()

    # Save to JSON
    output_path = Path(args.output)
    output_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print(f"Results saved to: {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
