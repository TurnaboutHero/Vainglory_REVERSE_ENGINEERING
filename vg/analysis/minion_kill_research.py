#!/usr/bin/env python3
"""
Minion Kill Pattern Research - Brute Force Frequency Matching

Uses the proven method that discovered kill ([18 04 1C]) and death ([08 04 31]) patterns.

Strategy:
1. Load truth data with minion_kills per player
2. For each match, concatenate all frames
3. Search for patterns where occurrence count matches truth minion_kills
4. Test entity ID at various offsets relative to pattern

Optimization: Instead of testing ALL byte patterns, find entity ID locations
and extract surrounding context to discover minion kill signatures.
"""

import json
import struct
import sys
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Set, Tuple, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.vgr_parser import VGRParser


def load_truth_data(truth_path: str) -> Dict:
    """Load tournament truth data."""
    with open(truth_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_all_frames(replay_file: str) -> bytes:
    """Load and concatenate all frames for a replay."""
    replay_path = Path(replay_file)
    if not replay_path.exists():
        raise FileNotFoundError(f"Replay file not found: {replay_file}")

    frame_dir = replay_path.parent
    replay_name = replay_path.stem.rsplit('.', 1)[0]  # Remove .0 suffix

    # Find all frames
    frames = list(frame_dir.glob(f"{replay_name}.*.vgr"))

    def frame_index(path: Path) -> int:
        try:
            return int(path.stem.split('.')[-1])
        except ValueError:
            return 0

    frames.sort(key=frame_index)

    # Concatenate all frame data
    all_data = b""
    for frame in frames:
        all_data += frame.read_bytes()

    print(f"[DATA] Loaded {len(frames)} frames, {len(all_data):,} bytes total")
    return all_data


def extract_player_entity_ids(replay_file: str) -> Dict[str, int]:
    """Extract player entity IDs from player blocks."""
    parser = VGRParser(replay_file, detect_heroes=False, auto_truth=False)
    data = parser.parse()

    player_eids = {}
    for team in ['left', 'right']:
        for player in data['teams'][team]:
            if player['entity_id']:
                player_eids[player['name']] = player['entity_id']

    return player_eids


def convert_eid_le_to_be(eid_le: int) -> int:
    """Convert entity ID from Little Endian to Big Endian."""
    le_bytes = struct.pack('<H', eid_le)
    be_value = struct.unpack('>H', le_bytes)[0]
    return be_value


def find_entity_id_occurrences(data: bytes, eid_be: int) -> List[int]:
    """Find all positions where entity ID (BE) appears in data."""
    eid_bytes = struct.pack('>H', eid_be)
    positions = []
    pos = 0
    while True:
        pos = data.find(eid_bytes, pos)
        if pos == -1:
            break
        positions.append(pos)
        pos += 1
    return positions


def extract_context_patterns(data: bytes, positions: List[int],
                            context_before: int = 10,
                            context_after: int = 10) -> Dict[bytes, int]:
    """Extract byte patterns around entity ID occurrences."""
    pattern_counts = Counter()

    for pos in positions:
        start = max(0, pos - context_before)
        end = min(len(data), pos + 2 + context_after)  # +2 for uint16 eid
        context = data[start:end]

        # Extract various sub-patterns
        # Pattern: 3 bytes before entity ID
        if pos >= 3:
            pattern = data[pos-3:pos]
            pattern_counts[pattern] += 1

        # Pattern: 2 bytes before entity ID
        if pos >= 2:
            pattern = data[pos-2:pos]
            pattern_counts[pattern] += 1

        # Pattern: 1 byte before entity ID
        if pos >= 1:
            pattern = data[pos-1:pos]
            pattern_counts[pattern] += 1

        # Pattern: 3 bytes after entity ID
        if pos + 5 <= len(data):
            pattern = data[pos+2:pos+5]
            pattern_counts[pattern] += 1

    return pattern_counts


def test_pattern_frequency_match(data: bytes, pattern: bytes,
                                 eid_offset: int,
                                 truth_counts: Dict[int, int],
                                 all_eids_be: Set[int]) -> bool:
    """
    Test if pattern occurrence counts match truth minion_kills.

    Args:
        data: Full concatenated frame data
        pattern: Byte pattern to search for
        eid_offset: Offset from pattern start to entity ID (can be negative)
        truth_counts: Dict mapping entity_id (BE) -> minion_kills count
        all_eids_be: Set of all valid player entity IDs (BE)

    Returns:
        True if counts match truth for ALL players
    """
    detected_counts = defaultdict(int)

    pos = 0
    while True:
        pos = data.find(pattern, pos)
        if pos == -1:
            break

        # Calculate entity ID position
        eid_pos = pos + eid_offset

        # Check bounds
        if eid_pos < 0 or eid_pos + 2 > len(data):
            pos += 1
            continue

        # Extract entity ID (Big Endian)
        eid_be = struct.unpack('>H', data[eid_pos:eid_pos+2])[0]

        # Only count if valid player entity
        if eid_be in all_eids_be:
            detected_counts[eid_be] += 1

        pos += 1

    # Check if detected counts match truth
    for eid_be, expected_count in truth_counts.items():
        detected = detected_counts.get(eid_be, 0)
        if detected != expected_count:
            return False

    return True


def search_minion_kill_pattern(match_data: Dict, match_idx: int) -> List[Dict]:
    """
    Brute-force search for minion kill pattern in a single match.

    Returns list of matching (pattern, offset) combinations.
    """
    print(f"\n{'='*80}")
    print(f"[STAGE:begin:match_{match_idx}_search]")
    print(f"Match {match_idx}: {match_data['replay_name']}")

    # Load all frames
    all_data = load_all_frames(match_data['replay_file'])

    # Extract player entity IDs and truth minion_kills
    player_eids = extract_player_entity_ids(match_data['replay_file'])

    # Build truth counts: eid_be -> minion_kills
    truth_counts = {}
    all_eids_be = set()

    print("\n[DATA] Player entity IDs and truth minion_kills:")
    for player_name, player_data in match_data['players'].items():
        if player_name not in player_eids:
            print(f"  WARNING: {player_name} not found in player blocks")
            continue

        eid_le = player_eids[player_name]
        eid_be = convert_eid_le_to_be(eid_le)
        minion_kills = player_data.get('minion_kills', 0)

        truth_counts[eid_be] = minion_kills
        all_eids_be.add(eid_be)

        print(f"  {player_name:20s} | EID: {eid_le:5d} (LE) = {eid_be:5d} (BE) | Minion Kills: {minion_kills:3d}")

    print(f"\n[OBJECTIVE] Find pattern where occurrence count matches minion_kills for ALL players")

    # Strategy 1: Find entity ID locations and extract context
    print("\n[STAGE:begin:context_extraction]")
    print("Extracting context patterns around entity ID occurrences...")

    all_context_patterns = Counter()

    for eid_be in all_eids_be:
        positions = find_entity_id_occurrences(all_data, eid_be)
        print(f"  Entity {eid_be}: {len(positions)} occurrences")

        # Extract patterns around these positions
        patterns = extract_context_patterns(all_data, positions,
                                           context_before=10, context_after=10)
        all_context_patterns.update(patterns)

    print(f"\n[FINDING] Extracted {len(all_context_patterns)} unique context patterns")

    # Test top context patterns
    print("\n[STAGE:begin:pattern_testing]")
    print("Testing context patterns for frequency match...")

    matches = []

    # Test 1-byte, 2-byte, 3-byte patterns
    for pattern_len in [1, 2, 3]:
        patterns_of_len = [(p, c) for p, c in all_context_patterns.items() if len(p) == pattern_len]
        patterns_of_len.sort(key=lambda x: -x[1])  # Sort by count descending

        print(f"\n  Testing {len(patterns_of_len)} {pattern_len}-byte patterns...")

        # Test top 100 patterns of each length
        for pattern, count in patterns_of_len[:100]:
            # Test various entity ID offsets relative to pattern
            for eid_offset in range(-10, 11):
                if test_pattern_frequency_match(all_data, pattern, eid_offset,
                                               truth_counts, all_eids_be):
                    pattern_hex = ' '.join(f'{b:02X}' for b in pattern)
                    print(f"\n  [FINDING] MATCH FOUND!")
                    print(f"    Pattern: [{pattern_hex}]")
                    print(f"    Entity ID offset: {eid_offset} (from pattern start)")
                    print(f"    Pattern count in data: {count}")

                    matches.append({
                        'pattern': pattern_hex,
                        'pattern_bytes': list(pattern),
                        'eid_offset': eid_offset,
                        'pattern_count': count,
                    })

    print(f"\n[STAGE:status:success]")
    print(f"[STAGE:end:match_{match_idx}_search]")

    return matches


def main():
    """Main research function."""
    print("[OBJECTIVE] Find minion kill pattern using brute-force frequency matching")

    # Load truth data
    truth_path = Path(__file__).parent.parent / "output" / "tournament_truth.json"
    if not truth_path.exists():
        print(f"[ERROR] Truth data not found: {truth_path}")
        return

    truth_data = load_truth_data(str(truth_path))
    print(f"[DATA] Loaded truth data with {len(truth_data['matches'])} matches")

    # Test on first 3 matches with minion_kills data
    matches_to_test = []
    for match in truth_data['matches']:
        # Check if match has minion_kills data
        has_minion_kills = any('minion_kills' in p for p in match['players'].values())
        if has_minion_kills:
            matches_to_test.append(match)
        if len(matches_to_test) >= 3:
            break

    print(f"\n[DATA] Testing on {len(matches_to_test)} matches with minion_kills data")

    # Search each match
    all_matches = []
    for idx, match in enumerate(matches_to_test, 1):
        try:
            matches = search_minion_kill_pattern(match, idx)
            if matches:
                all_matches.extend(matches)
                print(f"\n[FINDING] Match {idx}: Found {len(matches)} matching pattern(s)")
            else:
                print(f"\n[LIMITATION] Match {idx}: No exact matches found")
        except Exception as e:
            print(f"\n[ERROR] Match {idx}: {e}")
            import traceback
            traceback.print_exc()

    # Summary
    print(f"\n{'='*80}")
    print(f"[STAGE:begin:summary]")
    print(f"\nRESEARCH SUMMARY")
    print(f"{'='*80}")

    if all_matches:
        print(f"\n[FINDING] Found {len(all_matches)} total matching (pattern, offset) combinations:")
        for i, match in enumerate(all_matches, 1):
            print(f"\n  {i}. Pattern: [{match['pattern']}]")
            print(f"     Entity ID offset: {match['eid_offset']}")
            print(f"     Pattern count: {match['pattern_count']}")
    else:
        print("\n[LIMITATION] No exact matches found across all tested matches")
        print("\n[RECOMMENDATION] Next steps:")
        print("  1. Try wider entity ID offset range (-20 to +20)")
        print("  2. Test 4-byte and 5-byte patterns")
        print("  3. Consider minion entity IDs instead of player entity IDs")
        print("  4. Check if minion kills are accumulated differently (e.g., jungle vs lane)")

    print(f"\n[STAGE:status:success]")
    print(f"[STAGE:end:summary]")


if __name__ == '__main__':
    main()
