#!/usr/bin/env python3
"""
Cross-validate Entity 0 Action Code 0x28 as Death Event Detector

Validates the hypothesis that Entity 0 action code 0x28 represents death events
by comparing event counts against ground truth data from tournament replays.
"""

import sys
import os
import json
import struct
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.vgr_parser import VGRParser


class Entity0EventExtractor:
    """Extract Entity 0 events from VGR binary data"""

    ENTITY0_PATTERN = b'\x00\x00\x00\x00'

    def __init__(self, vgr_dir: str):
        self.vgr_dir = Path(vgr_dir)
        self.frames_data = []

    def load_all_frames(self) -> None:
        """Load all VGR frame files from directory"""
        vgr_files = sorted(self.vgr_dir.glob("*.vgr"), key=lambda x: self._extract_frame_num(x.name))

        print(f"  Loading {len(vgr_files)} frame files from {self.vgr_dir}")

        for vgr_file in vgr_files:
            with open(vgr_file, 'rb') as f:
                self.frames_data.append(f.read())

    @staticmethod
    def _extract_frame_num(filename: str) -> int:
        """Extract frame number from filename like 'uuid.123.vgr'"""
        try:
            return int(filename.split('.')[-2])
        except (ValueError, IndexError):
            return 0

    def extract_entity0_events(self) -> Dict[int, List[Dict]]:
        """
        Extract all Entity 0 events grouped by action code

        Returns:
            Dict mapping action_code -> list of event details
        """
        events_by_code = defaultdict(list)

        for frame_idx, frame_data in enumerate(self.frames_data):
            idx = 0
            while idx < len(frame_data) - 5:
                # Search for Entity 0 marker (4 zero bytes)
                if frame_data[idx:idx+4] == self.ENTITY0_PATTERN:
                    action_code = frame_data[idx + 4]

                    # Skip action_code == 0x00 (not an actual event)
                    if action_code != 0x00:
                        # Payload is 32 bytes starting at idx + 5
                        payload_start = idx + 5
                        payload_end = payload_start + 32

                        if payload_end <= len(frame_data):
                            payload = frame_data[payload_start:payload_end]

                            # Extract victim entity ID from bytes 4-5 (uint16 LE)
                            if len(payload) >= 6:
                                victim_entity_id = struct.unpack('<H', payload[4:6])[0]
                            else:
                                victim_entity_id = None

                            events_by_code[action_code].append({
                                'frame': frame_idx,
                                'offset': idx,
                                'action_code': action_code,
                                'victim_entity_id': victim_entity_id,
                                'payload': payload.hex()
                            })

                        # Move past this event (4 entity bytes + 1 action + 32 payload)
                        idx += 37
                    else:
                        idx += 1
                else:
                    idx += 1

        return dict(events_by_code)


def parse_tournament_replay(match_data: Dict) -> Optional[Dict]:
    """
    Parse a tournament replay and validate 0x28 events

    Args:
        match_data: Match info from tournament_truth.json

    Returns:
        Validation results or None if parsing failed
    """
    replay_file = match_data['replay_file']
    replay_dir = Path(replay_file).parent

    print(f"\n[PROCESSING] {match_data['replay_name']}")
    print(f"  Directory: {replay_dir}")

    # Calculate total truth deaths
    total_truth_deaths = sum(player['deaths'] for player in match_data['players'].values())
    print(f"  Truth deaths: {total_truth_deaths}")

    # Extract Entity 0 events
    try:
        extractor = Entity0EventExtractor(replay_dir)
        extractor.load_all_frames()
        events = extractor.extract_entity0_events()
    except Exception as e:
        print(f"  ERROR extracting events: {e}")
        return None

    # Count 0x28 and 0x24 events
    count_0x28 = len(events.get(0x28, []))
    count_0x24 = len(events.get(0x24, []))

    print(f"  Entity 0 0x28 events: {count_0x28}")
    print(f"  Entity 0 0x24 events: {count_0x24}")

    # Try to parse player entity IDs
    player_entity_map = {}
    try:
        parser = VGRParser(str(replay_dir), detect_heroes=False)
        parsed_data = parser.parse()

        # Extract entity IDs from both teams
        for team in ['left', 'right']:
            if team in parsed_data.get('teams', {}):
                for player in parsed_data['teams'][team]:
                    player_name = player.get('name', 'Unknown')
                    entity_id = player.get('entity_id')
                    if entity_id:
                        player_entity_map[player_name] = entity_id

        print(f"  Mapped {len(player_entity_map)} players to entity IDs")
    except Exception as e:
        print(f"  WARNING: Could not parse entity IDs: {e}")

    # Analyze victim entity IDs in 0x28 events
    victim_counts = defaultdict(int)
    for event in events.get(0x28, []):
        victim_id = event.get('victim_entity_id')
        if victim_id:
            victim_counts[victim_id] += 1

    # Try to match victim counts to truth deaths
    per_player_accuracy = {}
    if player_entity_map:
        for player_name, truth_deaths in match_data['players'].items():
            entity_id = player_entity_map.get(player_name)
            if entity_id:
                detected_deaths = victim_counts.get(entity_id, 0)
                truth_death_count = truth_deaths['deaths']
                per_player_accuracy[player_name] = {
                    'entity_id': entity_id,
                    'truth_deaths': truth_death_count,
                    'detected_deaths': detected_deaths,
                    'match': detected_deaths == truth_death_count
                }

    return {
        'match_name': match_data['replay_name'],
        'replay_file': str(replay_file),
        'total_truth_deaths': total_truth_deaths,
        'entity0_0x28_count': count_0x28,
        'entity0_0x24_count': count_0x24,
        'match_0x28': count_0x28 == total_truth_deaths,
        'match_0x24': count_0x24 == total_truth_deaths,
        'victim_entity_distribution': dict(victim_counts),
        'per_player_accuracy': per_player_accuracy,
        'all_action_codes': {hex(code): len(events) for code, events in sorted(events.items())}
    }


def parse_regular_replay(cache_dir: str, replay_name: str) -> Optional[Dict]:
    """
    Parse a regular 3v3 replay (no truth data)

    Args:
        cache_dir: Path to cache directory containing VGR files
        replay_name: Name identifier for the replay

    Returns:
        Event counts or None if parsing failed
    """
    cache_path = Path(cache_dir)

    print(f"\n[PROCESSING] {replay_name}")
    print(f"  Directory: {cache_path}")

    try:
        extractor = Entity0EventExtractor(cache_path)
        extractor.load_all_frames()
        events = extractor.extract_entity0_events()
    except Exception as e:
        print(f"  ERROR extracting events: {e}")
        return None

    count_0x28 = len(events.get(0x28, []))
    count_0x24 = len(events.get(0x24, []))

    print(f"  Entity 0 0x28 events: {count_0x28}")
    print(f"  Entity 0 0x24 events: {count_0x24}")

    # Victim entity distribution
    victim_counts = defaultdict(int)
    for event in events.get(0x28, []):
        victim_id = event.get('victim_entity_id')
        if victim_id:
            victim_counts[victim_id] += 1

    return {
        'replay_name': replay_name,
        'cache_dir': str(cache_path),
        'entity0_0x28_count': count_0x28,
        'entity0_0x24_count': count_0x24,
        'victim_entity_distribution': dict(victim_counts),
        'all_action_codes': {hex(code): len(events) for code, events in sorted(events.items())}
    }


def main():
    """Main cross-validation execution"""

    print("[OBJECTIVE] Cross-validate Entity 0 action code 0x28 as death event detector")
    print("=" * 80)

    # Load tournament truth data
    truth_file = Path("D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/tournament_truth.json")

    print(f"\n[DATA] Loading truth data from {truth_file}")

    with open(truth_file, 'r') as f:
        truth_data = json.load(f)

    print(f"[DATA] Loaded {len(truth_data['matches'])} tournament matches")

    # Process tournament replays
    tournament_results = []

    print("\n" + "=" * 80)
    print("PHASE 1: TOURNAMENT REPLAYS (with ground truth)")
    print("=" * 80)

    for match in truth_data['matches']:
        result = parse_tournament_replay(match)
        if result:
            tournament_results.append(result)

    # Process regular replays
    regular_replays = [
        ("D:/Desktop/My Folder/Game/VG/vg replay/21.11.04/cache", "21.11.04 (3v3)"),
        ("D:/Desktop/My Folder/Game/VG/vg replay/21.12.06/cache", "21.12.06 (3v3)"),
        ("D:/Desktop/My Folder/Game/VG/vg replay/21.12.07/cache", "21.12.07 (3v3)"),
    ]

    regular_results = []

    print("\n" + "=" * 80)
    print("PHASE 2: REGULAR REPLAYS (no ground truth)")
    print("=" * 80)

    for cache_dir, name in regular_replays:
        if Path(cache_dir).exists():
            result = parse_regular_replay(cache_dir, name)
            if result:
                regular_results.append(result)
        else:
            print(f"\n[SKIP] {name} - directory not found: {cache_dir}")

    # Calculate summary statistics
    print("\n" + "=" * 80)
    print("SUMMARY STATISTICS")
    print("=" * 80)

    total_matches = len(tournament_results)
    matches_0x28 = sum(1 for r in tournament_results if r['match_0x28'])
    matches_0x24 = sum(1 for r in tournament_results if r['match_0x24'])

    print(f"\n[FINDING] Tournament matches analyzed: {total_matches}")
    print(f"[FINDING] 0x28 perfect matches: {matches_0x28}/{total_matches} ({100*matches_0x28/total_matches:.1f}%)")
    print(f"[FINDING] 0x24 perfect matches: {matches_0x24}/{total_matches} ({100*matches_0x24/total_matches:.1f}%)")

    print(f"\n[FINDING] Regular replays analyzed: {len(regular_results)}")

    # Per-player accuracy analysis
    total_players = 0
    correct_players = 0

    for result in tournament_results:
        for player_name, acc in result['per_player_accuracy'].items():
            total_players += 1
            if acc['match']:
                correct_players += 1

    if total_players > 0:
        print(f"\n[STAT:per_player_accuracy] {correct_players}/{total_players} ({100*correct_players/total_players:.1f}%)")

    # Detail mismatches
    print("\n" + "=" * 80)
    print("DETAILED MISMATCH ANALYSIS")
    print("=" * 80)

    for result in tournament_results:
        if not result['match_0x28']:
            print(f"\n[LIMITATION] {result['match_name']}")
            print(f"  Expected: {result['total_truth_deaths']} deaths")
            print(f"  Detected: {result['entity0_0x28_count']} events (0x28)")
            print(f"  Difference: {result['entity0_0x28_count'] - result['total_truth_deaths']:+d}")

    # Save results
    output = {
        'validation_results': tournament_results,
        'regular_replay_results': regular_results,
        'summary': {
            'total_tournament_matches': total_matches,
            '0x28_perfect_matches': matches_0x28,
            '0x24_perfect_matches': matches_0x24,
            '0x28_accuracy': f"{100*matches_0x28/total_matches:.1f}%" if total_matches > 0 else "N/A",
            '0x24_accuracy': f"{100*matches_0x24/total_matches:.1f}%" if total_matches > 0 else "N/A",
            'total_regular_replays': len(regular_results),
            'per_player_accuracy': f"{100*correct_players/total_players:.1f}%" if total_players > 0 else "N/A",
            'total_players_validated': total_players,
            'correct_player_predictions': correct_players
        }
    }

    output_file = Path("D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/cross_validation_0x28.json")
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\n[FINDING] Results saved to {output_file}")

    # Final verdict
    print("\n" + "=" * 80)
    print("FINAL VERDICT")
    print("=" * 80)

    if matches_0x28 == total_matches:
        print("\n[FINDING] CONFIRMED: Entity 0 action code 0x28 is death event detector")
        print(f"[STAT:confidence] 100% match across {total_matches} tournament matches")
    elif matches_0x28 / total_matches >= 0.9:
        print("\n[FINDING] LIKELY: Entity 0 action code 0x28 is death event detector")
        print(f"[STAT:confidence] {100*matches_0x28/total_matches:.1f}% match rate")
        print("[LIMITATION] Some edge cases exist that require investigation")
    else:
        print("\n[FINDING] REJECTED: Entity 0 action code 0x28 is NOT a reliable death event detector")
        print(f"[STAT:confidence] Only {100*matches_0x28/total_matches:.1f}% match rate")
        print("[LIMITATION] Hypothesis requires revision - counts do not match truth data")
        print("[LIMITATION] Initial finding from 21.11.04 was a false positive (coincidence)")

    if matches_0x24 == total_matches:
        print("\n[FINDING] CONFIRMED: Entity 0 action code 0x24 is ALSO a perfect death event detector")
        print(f"[STAT:confidence] 100% match across {total_matches} tournament matches")


if __name__ == '__main__':
    main()
