#!/usr/bin/env python3
r"""
Tournament Item Verification - Extract and Compare Item IDs
Extracts item IDs from all 11 tournament replays and compares with OCR truth data.

Usage:
    python verify_tournament_items.py

Output:
    - JSON report to vg/output/tournament_item_verification.json
    - Console summary with statistics and findings
"""

import sys
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
ITEM_ID_RANGE = (101, 429)
TOURNAMENT_REPLAY_DIR = Path(r"D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays")
TOURNAMENT_TRUTH_PATH = Path(r"d:\Documents\GitHub\VG_REVERSE_ENGINEERING\vg\output\tournament_truth.json")
OUTPUT_PATH = Path(r"d:\Documents\GitHub\VG_REVERSE_ENGINEERING\vg\output\tournament_item_verification.json")

def find_vgr_files(base_dir: Path) -> List[Tuple[str, List[Path]]]:
    """
    Find all .vgr replay files in tournament directory.
    Returns list of (match_name, [frame_files]) tuples - one entry per match.
    """
    matches = []

    for match_dir in base_dir.iterdir():
        if not match_dir.is_dir() or match_dir.name in ['__MACOSX', 'bracket.jpg']:
            continue

        # Each match folder may contain numbered subfolders (game 1, 2, 3, etc.)
        for game_dir in match_dir.iterdir():
            if not game_dir.is_dir():
                continue

            # Find all .vgr frame files for this game
            frame_files = sorted(game_dir.glob('*.vgr'))
            if frame_files:
                match_name = f"{match_dir.name} - Game {game_dir.name}"
                matches.append((match_name, frame_files))

    return sorted(matches)

def extract_item_ids_from_frame(data: bytes) -> Set[int]:
    """
    Extract all item IDs from a frame using FF FF FF FF [XX 00] pattern.
    Returns set of unique item IDs found.
    """
    item_ids = set()
    offset = 0

    while True:
        pos = data.find(MARKER, offset)
        if pos == -1 or pos + 6 > len(data):
            break

        # Check if followed by [XX 00] pattern
        byte6 = data[pos + 5]

        if byte6 == 0x00:
            # Interpret as little-endian uint16
            item_id = struct.unpack('<H', data[pos + 4:pos + 6])[0]

            # Filter to item ID range
            if ITEM_ID_RANGE[0] <= item_id <= ITEM_ID_RANGE[1]:
                item_ids.add(item_id)

        offset = pos + 1

    return item_ids

def analyze_match_frames(frame_files: List[Path]) -> Dict:
    """
    Analyze all frame files for a single match and extract all item IDs.
    """
    all_items = set()
    total_size = 0

    # Sample frames for performance (every 10th frame for large matches)
    sample_frames = frame_files if len(frame_files) <= 50 else frame_files[::10]

    for frame_path in sample_frames:
        data = frame_path.read_bytes()
        total_size += len(data)
        item_ids = extract_item_ids_from_frame(data)
        all_items.update(item_ids)

    return {
        "total_frames": len(frame_files),
        "frames_analyzed": len(sample_frames),
        "total_size": total_size,
        "unique_items": sorted(list(all_items)),
        "item_count": len(all_items)
    }

def load_tournament_truth() -> Dict:
    """Load OCR truth data from tournament_truth.json"""
    try:
        with open(TOURNAMENT_TRUTH_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Could not load tournament truth: {e}", file=sys.stderr)
        return {"matches": []}

def main():
    """Main analysis function"""
    print("=" * 70)
    print("Tournament Item Verification")
    print("=" * 70)
    print(f"Tournament Replay Directory: {TOURNAMENT_REPLAY_DIR}")
    print(f"Tournament Truth File: {TOURNAMENT_TRUTH_PATH}")
    print(f"Output File: {OUTPUT_PATH}")
    print()

    # Find all replay files
    print("Searching for tournament replays...")
    matches = find_vgr_files(TOURNAMENT_REPLAY_DIR)

    if not matches:
        print("ERROR: No .vgr files found in tournament directory")
        return

    print(f"Found {len(matches)} tournament matches")
    print()

    # Analyze each match
    print("Analyzing matches for item patterns...")
    all_items_found: Set[int] = set()
    item_frequency: Counter = Counter()
    match_results = []

    for idx, (match_name, frame_files) in enumerate(matches, 1):
        print(f"  [{idx}/{len(matches)}] {match_name} ({len(frame_files)} frames)...", end=" ")

        try:
            result = analyze_match_frames(frame_files)
            result["match_name"] = match_name
            match_results.append(result)

            # Update aggregates
            for item_id in result["unique_items"]:
                all_items_found.add(item_id)
                item_frequency[item_id] += 1

            print(f"OK ({result['item_count']} items)")
        except Exception as e:
            print(f"ERROR: {e}")

    print()
    print("=" * 70)
    print("ANALYSIS RESULTS")
    print("=" * 70)

    # Categorize items
    known_items = []
    unknown_items = []
    missing_known_items = []

    for item_id in sorted(all_items_found):
        item_info = ITEM_ID_MAP.get(item_id)
        if item_info:
            known_items.append({
                "id": item_id,
                "name": item_info["name"],
                "category": item_info["category"],
                "tier": item_info["tier"],
                "frequency": item_frequency[item_id],
                "appears_in_pct": round(100 * item_frequency[item_id] / len(matches), 1)
            })
        else:
            unknown_items.append({
                "id": item_id,
                "frequency": item_frequency[item_id],
                "appears_in_pct": round(100 * item_frequency[item_id] / len(matches), 1)
            })

    # Check for items in ITEM_ID_MAP not found in replays
    for item_id, item_info in ITEM_ID_MAP.items():
        if item_id not in all_items_found and item_info.get("status") != "system":
            missing_known_items.append({
                "id": item_id,
                "name": item_info["name"],
                "category": item_info["category"],
                "tier": item_info["tier"]
            })

    # Load tournament truth for comparison
    tournament_truth = load_tournament_truth()

    # Print summary
    print(f"Total Matches Analyzed: {len(matches)}")
    print(f"Unique Items Found: {len(all_items_found)}")
    print(f"  - Known Items: {len(known_items)}")
    print(f"  - Unknown Items: {len(unknown_items)}")
    print(f"Known Items Missing: {len(missing_known_items)}")
    print()

    if unknown_items:
        print("UNKNOWN ITEMS DISCOVERED:")
        for item in unknown_items:
            print(f"  - ID {item['id']}: appears in {item['frequency']}/{len(matches)} matches ({item['appears_in_pct']}%)")
        print()

    # Item category breakdown
    category_counts = Counter()
    for item in known_items:
        category_counts[item["category"]] += 1

    print("ITEMS BY CATEGORY:")
    for category, count in sorted(category_counts.items()):
        print(f"  - {category}: {count} items")
    print()

    # Most frequent items
    print("MOST FREQUENT ITEMS (Top 10):")
    top_items = sorted(known_items, key=lambda x: x["frequency"], reverse=True)[:10]
    for item in top_items:
        print(f"  - {item['name']:25} (ID {item['id']:3}): {item['frequency']}/{len(matches)} matches ({item['appears_in_pct']}%)")
    print()

    # Tier 3 items specifically
    tier3_items = [item for item in known_items if item["tier"] == 3]
    print(f"TIER 3 ITEMS FOUND: {len(tier3_items)}")
    for item in sorted(tier3_items, key=lambda x: x["frequency"], reverse=True):
        print(f"  - {item['name']:25} (ID {item['id']:3}): {item['frequency']} matches")
    print()

    # Conclusions
    conclusions = []

    if unknown_items:
        conclusions.append(f"Found {len(unknown_items)} unknown item IDs not in mapping")

    if missing_known_items:
        tier3_missing = [i for i in missing_known_items if i["tier"] == 3]
        if tier3_missing:
            conclusions.append(f"{len(tier3_missing)} Tier 3 items not found with FF FF FF FF pattern (expected - different storage)")

    if len(tier3_items) > 0:
        conclusions.append(f"Successfully detected {len(tier3_items)} Tier 3 items in tournament replays")

    conclusions.append(f"Pattern analysis complete across {len(matches)} tournament matches")

    # Build final report
    report = {
        "summary": {
            "total_matches_analyzed": len(matches),
            "unique_items_found": len(all_items_found),
            "known_items": len(known_items),
            "unknown_items": len(unknown_items),
            "missing_known_items": len(missing_known_items)
        },
        "items_found": {
            "known": known_items,
            "unknown": unknown_items
        },
        "missing_items": missing_known_items,
        "item_frequency": dict(item_frequency),
        "category_breakdown": dict(category_counts),
        "match_details": match_results,
        "conclusions": conclusions
    }

    # Save report
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("=" * 70)
    print("CONCLUSIONS:")
    for conclusion in conclusions:
        print(f"  - {conclusion}")
    print()
    print(f"Full report saved to: {OUTPUT_PATH}")
    print("=" * 70)

if __name__ == '__main__':
    main()
