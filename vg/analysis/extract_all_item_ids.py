#!/usr/bin/env python3
r"""
Extract All Item IDs - VG Replay Analysis
Automatically discovers all item IDs from replay frames using the FF FF FF FF [XX 00] pattern.

Usage:
    python extract_all_item_ids.py <replay_folder_path>

Example:
    python extract_all_item_ids.py "D:\Desktop\My Folder\Game\VG\vg replay\replay-test\item buy test"

Output:
    - JSON report to stdout
    - Detailed analysis comparing discovered IDs with known ITEM_ID_MAP
"""

import sys
import os
import json
import struct
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Set, Tuple

# Add vg module to path
sys.path.insert(0, r'd:\Documents\GitHub\VG_REVERSE_ENGINEERING')

from vg.core.vgr_mapping import ITEM_ID_MAP

# Constants
MARKER = b'\xFF\xFF\xFF\xFF'
ITEM_ID_RANGE = (101, 429)  # Valid item ID range based on ITEM_ID_MAP structure

def find_replay_frames(replay_folder: Path) -> List[Path]:
    """Find all .vgr frame files in the replay folder."""
    frames = []

    # Try direct .vgr files in folder
    vgr_files = list(replay_folder.glob('*.vgr'))
    if vgr_files:
        frames = sorted(vgr_files)
    else:
        # Try subdirectories
        for subdir in replay_folder.iterdir():
            if subdir.is_dir():
                vgr_files = list(subdir.glob('*.vgr'))
                if vgr_files:
                    frames = sorted(vgr_files)
                    break

    return frames

def load_frame(frame_path: Path) -> bytes:
    """Load a frame's raw bytes."""
    return frame_path.read_bytes()

def extract_item_ids_from_frame(data: bytes) -> Dict[int, List[int]]:
    """
    Extract all item IDs from a frame using FF FF FF FF [XX 00] pattern.
    Returns dict of {item_id: [offset1, offset2, ...]}
    """
    item_positions = defaultdict(list)
    offset = 0

    while True:
        pos = data.find(MARKER, offset)
        if pos == -1 or pos + 6 > len(data):
            break

        # Check if followed by [XX 00] pattern
        byte5 = data[pos + 4]
        byte6 = data[pos + 5]

        if byte6 == 0x00:
            # Interpret as little-endian uint16
            item_id = struct.unpack('<H', data[pos + 4:pos + 6])[0]

            # Filter to item ID range
            if ITEM_ID_RANGE[0] <= item_id <= ITEM_ID_RANGE[1]:
                item_positions[item_id].append(pos)

        offset = pos + 1

    return item_positions

def analyze_replay(replay_folder: Path) -> Dict:
    """
    Analyze entire replay and extract all item IDs.
    Returns comprehensive analysis report.
    """
    frames = find_replay_frames(replay_folder)

    if not frames:
        return {
            "error": "No .vgr frame files found",
            "replay_folder": str(replay_folder)
        }

    # Aggregate data
    all_item_ids: Set[int] = set()
    item_first_frame: Dict[int, int] = {}
    item_frame_appearances: Dict[int, List[int]] = defaultdict(list)
    item_total_occurrences: Counter = Counter()

    # Process each frame
    for frame_idx, frame_path in enumerate(frames):
        data = load_frame(frame_path)
        item_positions = extract_item_ids_from_frame(data)

        for item_id, positions in item_positions.items():
            all_item_ids.add(item_id)
            item_total_occurrences[item_id] += len(positions)

            if item_id not in item_first_frame:
                item_first_frame[item_id] = frame_idx

            if frame_idx not in item_frame_appearances[item_id]:
                item_frame_appearances[item_id].append(frame_idx)

    # Build report
    known_items = []
    new_items = []
    missing_items = []

    # Check known items
    for item_id, item_info in ITEM_ID_MAP.items():
        if item_id in all_item_ids:
            known_items.append({
                "id": item_id,
                "name": item_info["name"],
                "category": item_info["category"],
                "tier": item_info["tier"],
                "found": True,
                "first_frame": item_first_frame[item_id],
                "frame_count": len(item_frame_appearances[item_id]),
                "total_occurrences": item_total_occurrences[item_id]
            })
        else:
            missing_items.append({
                "id": item_id,
                "name": item_info["name"],
                "category": item_info["category"],
                "tier": item_info["tier"],
                "note": "Not found with FF FF FF FF pattern in this replay"
            })

    # Check for new/unknown items
    known_ids = set(ITEM_ID_MAP.keys())
    for item_id in all_item_ids:
        if item_id not in known_ids:
            new_items.append({
                "id": item_id,
                "first_frame": item_first_frame[item_id],
                "found_in_frames": item_frame_appearances[item_id],
                "total_occurrences": item_total_occurrences[item_id]
            })

    report = {
        "replay_folder": str(replay_folder),
        "total_frames": len(frames),
        "analysis": {
            "total_unique_items_found": len(all_item_ids),
            "known_items_found": len(known_items),
            "known_items_missing": len(missing_items),
            "new_items_discovered": len(new_items)
        },
        "known_items": sorted(known_items, key=lambda x: x["id"]),
        "new_items": sorted(new_items, key=lambda x: x["id"]),
        "missing_items": sorted(missing_items, key=lambda x: x["id"])
    }

    return report

def main():
    """Main CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: python extract_all_item_ids.py <replay_folder_path>", file=sys.stderr)
        print("\nExample:", file=sys.stderr)
        print('  python extract_all_item_ids.py "D:\\Desktop\\replay-test\\item buy test"', file=sys.stderr)
        sys.exit(1)

    replay_folder = Path(sys.argv[1])

    if not replay_folder.exists():
        print(f"ERROR: Folder not found: {replay_folder}", file=sys.stderr)
        sys.exit(1)

    if not replay_folder.is_dir():
        print(f"ERROR: Not a directory: {replay_folder}", file=sys.stderr)
        sys.exit(1)

    # Run analysis
    print(f"Analyzing replay: {replay_folder}", file=sys.stderr)
    print(f"Searching for pattern: FF FF FF FF [XX 00]", file=sys.stderr)
    print(f"Item ID range: {ITEM_ID_RANGE[0]}-{ITEM_ID_RANGE[1]}", file=sys.stderr)
    print("", file=sys.stderr)

    report = analyze_replay(replay_folder)

    # Print summary to stderr
    if "error" not in report:
        print("="*60, file=sys.stderr)
        print("ANALYSIS SUMMARY", file=sys.stderr)
        print("="*60, file=sys.stderr)
        print(f"Total Frames: {report['total_frames']}", file=sys.stderr)
        print(f"Unique Items Found: {report['analysis']['total_unique_items_found']}", file=sys.stderr)
        print(f"Known Items Found: {report['analysis']['known_items_found']}", file=sys.stderr)
        print(f"Known Items Missing: {report['analysis']['known_items_missing']}", file=sys.stderr)
        print(f"New Items Discovered: {report['analysis']['new_items_discovered']}", file=sys.stderr)
        print("="*60, file=sys.stderr)

    # Output JSON to stdout
    print(json.dumps(report, indent=2, ensure_ascii=False))

if __name__ == '__main__':
    main()
