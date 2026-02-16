#!/usr/bin/env python3
"""
Gold Pattern Analyzer - Deep dive into gold value storage structure

Based on Match 1 findings:
- Gold values found as float32 (both LE and BE) in last frame
- 90% correlation (9/10 players matched)
- Values scattered at different offsets

Goal: Find the structural pattern around gold values
"""

import os
import sys
import json
import struct
from pathlib import Path
from typing import Dict, List, Tuple

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
    """Extract player entity IDs. Returns {entity_id_LE: entity_id_BE}."""
    players = {}
    markers = [bytes([0xDA, 0x03, 0xEE]), bytes([0xE0, 0x03, 0xEE])]

    for marker in markers:
        pos = 0
        while True:
            pos = frame0.find(marker, pos)
            if pos == -1:
                break
            eid_offset = pos + 0xA5
            if eid_offset + 2 <= len(frame0):
                eid_le = struct.unpack_from("<H", frame0, eid_offset)[0]
                eid_be = struct.unpack(">H", struct.pack("<H", eid_le))[0]
                players[eid_le] = eid_be
            pos += 1

    return players


def find_gold_occurrences(frame_data: bytes, gold_value: int, tolerance: int = 100) -> List[Tuple[int, str, float]]:
    """
    Find all occurrences of a gold value (±tolerance) in frame data.
    Returns list of (offset, format, exact_value) tuples.
    """
    occurrences = []

    for i in range(len(frame_data) - 4):
        try:
            # uint32 LE
            val = struct.unpack_from("<I", frame_data, i)[0]
            if abs(val - gold_value) <= tolerance:
                occurrences.append((i, "uint32_LE", val))

            # uint32 BE
            val = struct.unpack_from(">I", frame_data, i)[0]
            if abs(val - gold_value) <= tolerance:
                occurrences.append((i, "uint32_BE", val))

            # float32 LE
            val_f = struct.unpack_from("<f", frame_data, i)[0]
            if 5000 <= val_f <= 25000 and abs(val_f - gold_value) <= tolerance:
                occurrences.append((i, "float32_LE", val_f))

            # float32 BE
            val_f = struct.unpack_from(">f", frame_data, i)[0]
            if 5000 <= val_f <= 25000 and abs(val_f - gold_value) <= tolerance:
                occurrences.append((i, "float32_BE", val_f))
        except:
            pass

    return occurrences


def analyze_context(frame_data: bytes, offset: int, window: int = 32) -> Dict:
    """Analyze the bytes surrounding a gold value."""
    start = max(0, offset - window)
    end = min(len(frame_data), offset + window)

    context_bytes = frame_data[start:end]
    hex_dump = ' '.join(f'{b:02X}' for b in context_bytes)

    # Look for entity IDs nearby (uint16 BE in range 0x05DC-0x05E5 = 1500-1509)
    entity_ids = []
    for i in range(start, end - 1):
        eid_be = struct.unpack_from(">H", frame_data, i)[0]
        if 0x05DC <= eid_be <= 0x05E5:
            entity_ids.append((i - offset, eid_be))

    return {
        'hex_dump': hex_dump,
        'nearby_entity_ids': entity_ids,
    }


def main():
    # Load truth data
    truth_path = "D:\\Documents\\GitHub\\VG_REVERSE_ENGINEERING\\vg\\output\\tournament_truth.json"
    with open(truth_path, 'r') as f:
        truth_data = json.load(f)

    # Analyze Match 1 (known to have 90% correlation)
    match = truth_data['matches'][0]
    replay_file = match['replay_file']
    replay_dir = os.path.dirname(replay_file)
    replay_base = replay_file.replace('.0.vgr', '')

    print("[OBJECTIVE] Analyze gold value storage structure in Match 1 last frame")
    print()

    # Load frames
    frames = load_all_frames(replay_base)
    print(f"[DATA] Loaded {len(frames)} frames")

    # Extract player entity IDs
    player_eids = extract_player_entity_ids(frames[0])
    print(f"[DATA] Found {len(player_eids)} players")

    # Parse replay to get player names
    parser = VGRParser(replay_dir)
    parsed_data = parser.parse()

    # Build eid_be -> player mapping
    eid_to_player = {}
    for team in ['left', 'right']:
        for player_dict in parsed_data['teams'][team]:
            if player_dict.get('entity_id') is not None:
                eid_le = player_dict['entity_id']
                eid_be = struct.unpack(">H", struct.pack("<H", eid_le))[0]
                eid_to_player[eid_be] = {
                    'name': player_dict['name'],
                    'truth_gold': None
                }

    # Map truth gold
    for player_name, player_truth in match['players'].items():
        for eid_be, player_info in eid_to_player.items():
            if player_info['name'] == player_name:
                player_info['truth_gold'] = player_truth['gold']
                break

    print()
    print("[FINDING] Analyzing gold value occurrences in last frame:")
    print()

    last_frame = frames[-1]

    # For each player, find all occurrences of their gold value
    for eid_be, player_info in sorted(eid_to_player.items()):
        name = player_info['name']
        gold = player_info['truth_gold']

        if gold is None:
            continue

        print(f"Player: {name} (Entity 0x{eid_be:04X})")
        print(f"  Truth Gold: {gold}")

        occurrences = find_gold_occurrences(last_frame, gold, tolerance=100)
        print(f"  Found {len(occurrences)} occurrences:")

        for offset, fmt, exact_value in occurrences[:5]:  # Show first 5
            print(f"    Offset 0x{offset:08X} ({fmt}): {exact_value:.0f}")

            # Analyze context
            context = analyze_context(last_frame, offset, window=16)

            # Show hex dump
            print(f"      Context: {context['hex_dump']}")

            # Show nearby entity IDs
            if context['nearby_entity_ids']:
                for eid_offset, nearby_eid in context['nearby_entity_ids']:
                    print(f"      Entity ID 0x{nearby_eid:04X} at offset {eid_offset:+d}")

        print()

    # Look for common patterns
    print("[FINDING] Searching for common header patterns before gold values:")
    print()

    # Collect all gold offsets
    all_gold_offsets = []
    for eid_be, player_info in eid_to_player.items():
        gold = player_info['truth_gold']
        if gold is None:
            continue

        occurrences = find_gold_occurrences(last_frame, gold, tolerance=100)
        for offset, fmt, exact_value in occurrences:
            all_gold_offsets.append((offset, fmt, exact_value, eid_be, player_info['name']))

    # Check for common headers before gold values
    header_patterns = {}
    for offset, fmt, value, eid_be, name in all_gold_offsets:
        if offset >= 10:
            # Check 1, 2, 3, 4 byte headers before the gold value
            for header_len in [1, 2, 3, 4]:
                header_offset = offset - header_len
                if header_offset >= 0:
                    header = last_frame[header_offset:offset]
                    if header not in header_patterns:
                        header_patterns[header] = []
                    header_patterns[header].append((offset, fmt, value, eid_be, name))

    # Show most common headers
    common_headers = sorted(header_patterns.items(), key=lambda x: len(x[1]), reverse=True)
    print(f"[STAT:unique_headers] {len(common_headers)}")
    print()
    print("Most common headers (top 10):")
    for header, occurrences in common_headers[:10]:
        hex_str = ' '.join(f'{b:02X}' for b in header)
        print(f"  Header [{hex_str}] - {len(occurrences)} occurrences:")
        for offset, fmt, value, eid_be, name in occurrences[:3]:
            print(f"    {name} @ 0x{offset:08X}: {value:.0f} ({fmt})")


if __name__ == "__main__":
    main()
