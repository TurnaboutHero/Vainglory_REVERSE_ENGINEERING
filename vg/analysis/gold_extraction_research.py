#!/usr/bin/env python3
"""
Gold Extraction Research - Brute Force Frequency Matching

Extracts per-player total gold from VGR replay files using brute-force pattern matching
against tournament truth data.

Approach:
1. Test known credit records [10 04 1D] with various value filtering strategies
2. If that fails, brute-force search all 2-byte header patterns for gold sums
3. Match extracted gold against truth values (±100 tolerance for rounding)
"""

import os
import sys
import json
import struct
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Set, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.vgr_parser import VGRParser


def load_all_frames(replay_dir: str) -> List[bytes]:
    """Load all frame files from a replay directory."""
    frames = []
    frame_idx = 0
    while True:
        frame_path = f"{replay_dir}.{frame_idx}.vgr"
        if not os.path.exists(frame_path):
            break
        with open(frame_path, 'rb') as f:
            frames.append(f.read())
        frame_idx += 1
    return frames


def extract_player_entity_ids(frame0: bytes) -> Dict[int, int]:
    """Extract player entity IDs from frame 0. Returns {entity_id_LE: entity_id_BE}."""
    players = {}

    # Player block markers
    markers = [bytes([0xDA, 0x03, 0xEE]), bytes([0xE0, 0x03, 0xEE])]

    for marker in markers:
        pos = 0
        while True:
            pos = frame0.find(marker, pos)
            if pos == -1:
                break

            # Entity ID at offset +0xA5 (uint16 LE)
            eid_offset = pos + 0xA5
            if eid_offset + 2 <= len(frame0):
                eid_le = struct.unpack_from("<H", frame0, eid_offset)[0]
                # Convert to Big Endian for event stream matching
                eid_be = struct.unpack(">H", struct.pack("<H", eid_le))[0]
                players[eid_le] = eid_be

            pos += 1

    return players


def scan_credit_records(frames: List[bytes], valid_eids_be: Set[int],
                       header: bytes = bytes([0x10, 0x04, 0x1D]),
                       min_value: float = 0.0,
                       max_value: float = 100000.0) -> Dict[int, float]:
    """
    Scan all frames for credit records and sum values per entity.

    Args:
        frames: List of frame data
        valid_eids_be: Set of valid entity IDs (Big Endian)
        header: 3-byte header pattern to search for
        min_value: Minimum value to include in sum (filter out flags)
        max_value: Maximum value to include in sum

    Returns:
        Dict mapping entity_id_BE -> total_gold
    """
    gold_totals = defaultdict(float)

    for frame_data in frames:
        pos = 0
        while True:
            pos = frame_data.find(header, pos)
            if pos == -1:
                break

            # Credit record structure: [header 3B] [00 00] [eid uint16 BE] [value f32 BE]
            if pos + 11 > len(frame_data):
                pos += 1
                continue

            # Validate structure: [00 00] padding
            if frame_data[pos+3:pos+5] != b'\x00\x00':
                pos += 1
                continue

            eid = struct.unpack_from(">H", frame_data, pos + 5)[0]
            value = struct.unpack_from(">f", frame_data, pos + 7)[0]

            # Only sum if entity is valid and value is in range
            if eid in valid_eids_be and min_value <= value <= max_value:
                gold_totals[eid] += value

            pos += 1

    return dict(gold_totals)


def brute_force_gold_headers(frames: List[bytes], valid_eids_be: Set[int],
                             truth_gold: Dict[int, int]) -> List[Tuple[bytes, float, Dict[int, float]]]:
    """
    Brute-force search for 2-byte headers that produce gold totals matching truth.

    Returns:
        List of (header, correlation, gold_totals) tuples sorted by correlation
    """
    results = []

    # Try all possible 2-byte headers
    for b1 in range(256):
        for b2 in range(256):
            header = bytes([b1, b2])

            # Skip if this would be too common (performance optimization)
            if frames[0].count(header) > 10000:
                continue

            gold_totals = defaultdict(float)

            for frame_data in frames:
                pos = 0
                while True:
                    pos = frame_data.find(header, pos)
                    if pos == -1:
                        break

                    # Try to parse [header 2B] [eid uint16 BE] [value f32 BE]
                    if pos + 8 > len(frame_data):
                        pos += 1
                        continue

                    eid = struct.unpack_from(">H", frame_data, pos + 2)[0]
                    try:
                        value = struct.unpack_from(">f", frame_data, pos + 4)[0]
                    except:
                        pos += 1
                        continue

                    # Only sum if entity is valid and value is positive
                    if eid in valid_eids_be and 0 <= value <= 100000:
                        gold_totals[eid] += value

                    pos += 1

            # Check correlation with truth
            if len(gold_totals) == 0:
                continue

            correlation = calculate_correlation(gold_totals, truth_gold, valid_eids_be)
            if correlation > 0.5:  # Only keep promising candidates
                results.append((header, correlation, dict(gold_totals)))

    return sorted(results, key=lambda x: x[1], reverse=True)


def scan_last_frame_for_gold(frame_data: bytes, truth_gold: Dict[int, int],
                            valid_eids_be: Set[int]) -> Dict[int, float]:
    """
    Scan last frame for float32 values near truth gold values.
    Returns dict mapping entity_id_BE -> gold_value
    """
    gold_map = {}

    # Build set of expected gold values (±200 tolerance)
    expected_values = set()
    for gold in truth_gold.values():
        for offset in range(-200, 201, 100):
            expected_values.add(gold + offset)

    # Scan frame for float32 values matching expected range
    for i in range(len(frame_data) - 4):
        try:
            value = struct.unpack_from(">f", frame_data, i)[0]
            if 5000 <= value <= 25000:  # Reasonable gold range
                rounded = int(round(value / 100) * 100)
                if rounded in expected_values:
                    # Found a match - look for entity ID nearby
                    # Try offsets -10 to +10 bytes
                    for eid_offset in range(-10, 11, 2):
                        check_pos = i + eid_offset
                        if 0 <= check_pos <= len(frame_data) - 2:
                            eid = struct.unpack_from(">H", frame_data, check_pos)[0]
                            if eid in valid_eids_be and eid not in gold_map:
                                gold_map[eid] = value
                                break
        except:
            pass

    return gold_map


def scan_player_blocks_for_gold(frame_data: bytes, truth_gold: Dict[int, int],
                                player_eids: Dict[int, int]) -> Dict[int, float]:
    """
    Scan player blocks in frame 0 for gold values.
    Returns dict mapping entity_id_BE -> gold_value
    """
    gold_map = {}

    markers = [bytes([0xDA, 0x03, 0xEE]), bytes([0xE0, 0x03, 0xEE])]

    for marker in markers:
        pos = 0
        while True:
            pos = frame_data.find(marker, pos)
            if pos == -1:
                break

            # Entity ID at +0xA5
            eid_offset = pos + 0xA5
            if eid_offset + 2 > len(frame_data):
                pos += 1
                continue

            eid_le = struct.unpack_from("<H", frame_data, eid_offset)[0]
            eid_be = player_eids.get(eid_le)

            if eid_be is None or eid_be not in truth_gold:
                pos += 1
                continue

            # Search for gold value in player block (try offsets +0 to +500)
            expected_gold = truth_gold[eid_be]
            block_end = min(pos + 500, len(frame_data) - 4)

            for scan_pos in range(pos, block_end, 4):
                try:
                    # Try uint32 LE
                    val_u32_le = struct.unpack_from("<I", frame_data, scan_pos)[0]
                    if abs(val_u32_le - expected_gold) <= 100:
                        gold_map[eid_be] = float(val_u32_le)
                        break

                    # Try uint32 BE
                    val_u32_be = struct.unpack_from(">I", frame_data, scan_pos)[0]
                    if abs(val_u32_be - expected_gold) <= 100:
                        gold_map[eid_be] = float(val_u32_be)
                        break

                    # Try float32 LE
                    val_f32_le = struct.unpack_from("<f", frame_data, scan_pos)[0]
                    if 5000 <= val_f32_le <= 25000 and abs(val_f32_le - expected_gold) <= 100:
                        gold_map[eid_be] = val_f32_le
                        break

                    # Try float32 BE
                    val_f32_be = struct.unpack_from(">f", frame_data, scan_pos)[0]
                    if 5000 <= val_f32_be <= 25000 and abs(val_f32_be - expected_gold) <= 100:
                        gold_map[eid_be] = val_f32_be
                        break
                except:
                    pass

            pos += 1

    return gold_map


def brute_force_exact_gold_search(frame_data: bytes, truth_gold: Dict[int, int],
                                  valid_eids_be: Set[int]) -> Dict[int, float]:
    """
    Brute-force search for exact gold values in frame data.
    Try uint32 LE/BE and float32 LE/BE at every offset.
    """
    gold_map = {}

    # Build list of expected values (exact truth values)
    expected = set(truth_gold.values())

    print(f"      Expected gold values: {sorted(expected)}")

    # Try every offset in the frame
    for i in range(len(frame_data) - 4):
        try:
            # Try uint32 LE
            val = struct.unpack_from("<I", frame_data, i)[0]
            if val in expected:
                # Found a match - which player?
                for eid_be, gold in truth_gold.items():
                    if gold == val and eid_be not in gold_map:
                        gold_map[eid_be] = float(val)
                        print(f"      Found uint32 LE {val} at offset {i:08X} for entity {eid_be:04X}")
                        break

            # Try uint32 BE
            val = struct.unpack_from(">I", frame_data, i)[0]
            if val in expected:
                for eid_be, gold in truth_gold.items():
                    if gold == val and eid_be not in gold_map:
                        gold_map[eid_be] = float(val)
                        print(f"      Found uint32 BE {val} at offset {i:08X} for entity {eid_be:04X}")
                        break

            # Try float32 LE
            val_f = struct.unpack_from("<f", frame_data, i)[0]
            if 5000 <= val_f <= 25000:
                val_rounded = int(round(val_f / 100) * 100)
                if val_rounded in expected:
                    for eid_be, gold in truth_gold.items():
                        if abs(gold - val_rounded) <= 100 and eid_be not in gold_map:
                            gold_map[eid_be] = val_f
                            print(f"      Found float32 LE {val_f:.0f} at offset {i:08X} for entity {eid_be:04X}")
                            break

            # Try float32 BE
            val_f = struct.unpack_from(">f", frame_data, i)[0]
            if 5000 <= val_f <= 25000:
                val_rounded = int(round(val_f / 100) * 100)
                if val_rounded in expected:
                    for eid_be, gold in truth_gold.items():
                        if abs(gold - val_rounded) <= 100 and eid_be not in gold_map:
                            gold_map[eid_be] = val_f
                            print(f"      Found float32 BE {val_f:.0f} at offset {i:08X} for entity {eid_be:04X}")
                            break
        except:
            pass

    return gold_map


def calculate_correlation(extracted: Dict[int, float], truth: Dict[int, int],
                          valid_eids: Set[int]) -> float:
    """
    Calculate correlation between extracted gold and truth gold.
    Returns value 0-1 where 1 is perfect match.
    """
    if not extracted:
        return 0.0

    # Count how many players match within tolerance
    matches = 0
    total = len(valid_eids)

    for eid in valid_eids:
        extracted_val = int(round(extracted.get(eid, 0)))
        truth_val = truth.get(eid, 0)

        # Allow ±100 tolerance (truth is rounded to nearest 100)
        if abs(extracted_val - truth_val) <= 100:
            matches += 1

    return matches / total if total > 0 else 0.0


def main():
    # Load truth data
    truth_path = "D:\\Documents\\GitHub\\VG_REVERSE_ENGINEERING\\vg\\output\\tournament_truth.json"
    with open(truth_path, 'r') as f:
        truth_data = json.load(f)

    print("[OBJECTIVE] Extract per-player total gold using brute-force frequency matching")
    print()

    total_matches = 0
    total_players = 0
    perfect_matches = 0

    # Process each match (skip Match 9 - index 8)
    for match_idx, match in enumerate(truth_data['matches']):
        if match_idx == 8:  # Skip incomplete match
            print(f"Match {match_idx + 1}: SKIPPED (incomplete)")
            continue

        replay_name = match['replay_name']
        replay_file = match['replay_file']
        replay_dir = os.path.dirname(replay_file)
        replay_base = replay_file.replace('.0.vgr', '')

        print(f"Match {match_idx + 1}: {replay_name}")

        # Load frames
        try:
            frames = load_all_frames(replay_base)
        except Exception as e:
            print(f"  ERROR loading frames: {e}")
            continue

        if len(frames) == 0:
            print(f"  ERROR: No frames found")
            continue

        print(f"  [DATA] Loaded {len(frames)} frames")

        # Extract player entity IDs from frame 0
        player_eids = extract_player_entity_ids(frames[0])
        print(f"  [DATA] Found {len(player_eids)} players: {list(player_eids.keys())}")

        # Build truth gold mapping (eid_BE -> gold)
        truth_gold = {}
        for player_name, player_data in match['players'].items():
            # We need to map player names to entity IDs - use VGRParser
            pass

        # For now, try to match by player order (this is a simplification)
        # Better approach: use VGRParser to get full player data with entity IDs
        parser = VGRParser(replay_dir)
        try:
            parsed_data = parser.parse()
        except Exception as e:
            print(f"  ERROR parsing replay: {e}")
            continue

        # Build eid -> truth_gold mapping
        truth_gold_map = {}
        all_players = []
        for team in ['left', 'right']:
            for player_dict in parsed_data['teams'][team]:
                all_players.append(player_dict)

        for player_dict in all_players:
            if player_dict.get('entity_id') is not None:
                eid_le = player_dict['entity_id']
                eid_be = struct.unpack(">H", struct.pack("<H", eid_le))[0]
                # Find this player in truth data
                for player_name, player_truth in match['players'].items():
                    if player_dict['name'] == player_name:
                        truth_gold_map[eid_be] = player_truth['gold']
                        break

        if len(truth_gold_map) == 0:
            print(f"  ERROR: Could not map players to truth data")
            continue

        print(f"  [DATA] Mapped {len(truth_gold_map)} players to truth gold")

        valid_eids_be = set(truth_gold_map.keys())

        # Strategy 1: Known credit records [10 04 1D] summing ALL values
        print(f"\n  Strategy 1: Credit records [10 04 1D] - sum ALL values")
        gold_all = scan_credit_records(frames, valid_eids_be, min_value=0.0, max_value=100000.0)
        corr_all = calculate_correlation(gold_all, truth_gold_map, valid_eids_be)
        print(f"    Correlation: {corr_all:.1%}")

        # Strategy 2: Credit records filtering out flags (value > 1.5)
        print(f"  Strategy 2: Credit records [10 04 1D] - filter value > 1.5")
        gold_filtered = scan_credit_records(frames, valid_eids_be, min_value=1.5, max_value=100000.0)
        corr_filtered = calculate_correlation(gold_filtered, truth_gold_map, valid_eids_be)
        print(f"    Correlation: {corr_filtered:.1%}")

        # Strategy 3: Credit records filtering value > 2.0
        print(f"  Strategy 3: Credit records [10 04 1D] - filter value > 2.0")
        gold_filtered2 = scan_credit_records(frames, valid_eids_be, min_value=2.0, max_value=100000.0)
        corr_filtered2 = calculate_correlation(gold_filtered2, truth_gold_map, valid_eids_be)
        print(f"    Correlation: {corr_filtered2:.1%}")

        # Strategy 4: Search last frame for gold values near truth
        print(f"  Strategy 4: Scan last frame for float32 values near truth gold")
        gold_last_frame = scan_last_frame_for_gold(frames[-1], truth_gold_map, valid_eids_be)
        corr_last_frame = calculate_correlation(gold_last_frame, truth_gold_map, valid_eids_be)
        print(f"    Correlation: {corr_last_frame:.1%}")

        # Strategy 5: Search for gold in player blocks (frame 0)
        print(f"  Strategy 5: Scan player blocks in frame 0 for gold values")
        gold_player_blocks = scan_player_blocks_for_gold(frames[0], truth_gold_map, player_eids)
        corr_player_blocks = calculate_correlation(gold_player_blocks, truth_gold_map, valid_eids_be)
        print(f"    Correlation: {corr_player_blocks:.1%}")

        # Strategy 6: Brute-force search for exact gold values in last frame
        if match_idx == 0:  # Only do expensive search on first match
            print(f"\n  Strategy 6: Brute-force search for exact gold patterns (SLOW)")
            print(f"    Searching last frame for exact truth gold values...")
            gold_brute = brute_force_exact_gold_search(frames[-1], truth_gold_map, valid_eids_be)
            corr_brute = calculate_correlation(gold_brute, truth_gold_map, valid_eids_be)
            print(f"    Correlation: {corr_brute:.1%}")
            if corr_brute > 0:
                print(f"    [FINDING] Found matching pattern! Details:")
                for eid_be, value in gold_brute.items():
                    print(f"      Entity {eid_be:04X}: {value:.0f}")

        # Strategy 6 results (if available)
        if match_idx == 0 and 'gold_brute' in locals():
            corr_list = [corr_all, corr_filtered, corr_filtered2, corr_last_frame, corr_player_blocks, corr_brute]
        else:
            corr_list = [corr_all, corr_filtered, corr_filtered2, corr_last_frame, corr_player_blocks]

        # Show detailed comparison for best strategy
        best_corr = max(corr_list)
        if best_corr == corr_all:
            best_gold = gold_all
            best_name = "Strategy 1 (sum all)"
        elif best_corr == corr_filtered:
            best_gold = gold_filtered
            best_name = "Strategy 2 (value > 1.5)"
        elif best_corr == corr_filtered2:
            best_gold = gold_filtered2
            best_name = "Strategy 3 (value > 2.0)"
        elif best_corr == corr_last_frame:
            best_gold = gold_last_frame
            best_name = "Strategy 4 (last frame scan)"
        elif best_corr == corr_player_blocks:
            best_gold = gold_player_blocks
            best_name = "Strategy 5 (player blocks)"
        elif match_idx == 0 and 'gold_brute' in locals() and best_corr == corr_brute:
            best_gold = gold_brute
            best_name = "Strategy 6 (brute-force exact)"

        print(f"\n  Best: {best_name} - {best_corr:.1%}")
        print(f"  {'Player':<20} {'Truth':>8} {'Extracted':>10} {'Diff':>8} {'Match'}")
        print(f"  {'-'*60}")

        for player_dict in all_players:
            if player_dict.get('entity_id') is not None:
                eid_le = player_dict['entity_id']
                eid_be = struct.unpack(">H", struct.pack("<H", eid_le))[0]
                if eid_be in truth_gold_map:
                    truth = truth_gold_map[eid_be]
                    extracted = int(round(best_gold.get(eid_be, 0)))
                    diff = extracted - truth
                    match = "OK" if abs(diff) <= 100 else "X"
                    print(f"  {player_dict['name']:<20} {truth:>8} {extracted:>10} {diff:>+8} {match}")

        print()

    print("[FINDING] Analysis complete - see results above")


if __name__ == "__main__":
    main()
