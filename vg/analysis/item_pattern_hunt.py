#!/usr/bin/env python3
"""
Item Pattern Hunt - Focused discovery script for item ID markers in VG replay data.

Searches for:
1. FF FF FF FF [ItemID] patterns for known test items
2. All FF FF FF FF [XX 00] patterns to find item-like records
3. Reverse search - what prefixes precede item IDs
4. Extended record dumps with field interpretation
5. Inventory state progression tracking
"""

import sys
import os
import struct
from pathlib import Path
from collections import defaultdict, Counter

# Add vg module to path
sys.path.insert(0, r'd:\Documents\GitHub\VG_REVERSE_ENGINEERING')

# Test replay path
REPLAY_BASE = Path(r'D:\Desktop\My Folder\Game\VG\vg replay\replay-test\item buy test')
REPLAY_NAME = 'a8d06624-352e-4897-b920-2cdbafdb48ab-50361b75-aa42-41b7-ac17-8f252350a313'
OUTPUT_PATH = Path(r'd:\Documents\GitHub\VG_REVERSE_ENGINEERING\vg\output\item_pattern_hunt_output.txt')

# Test items from the discovery
TEST_ITEMS = {
    101: 'Weapon Blade',
    102: 'Book of Eulogies',
    103: 'Swift Shooter',
    111: 'Heavy Steel',
    121: 'Sorrowblade'
}

MARKER = b'\xFF\xFF\xFF\xFF'

def load_frame(frame_num):
    """Load a frame's raw bytes."""
    # Default: frames are directly under REPLAY_BASE as .vgr files.
    frame_path = REPLAY_BASE / f'{REPLAY_NAME}.{frame_num}.vgr'
    if frame_path.exists():
        return frame_path.read_bytes()
    # Fallback: some exports may place frames under a subfolder.
    alt_path = REPLAY_BASE / REPLAY_NAME / f'{REPLAY_NAME}.{frame_num}.vgr'
    if alt_path.exists():
        return alt_path.read_bytes()
    return None
def hex_dump(data, offset=0, length=30):
    """Create hex dump with ASCII preview."""
    chunk = data[:length]
    hex_str = ' '.join(f'{b:02X}' for b in chunk)
    ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
    return f"@{offset:08X}: {hex_str}  |{ascii_str}|"

def interpret_bytes(data, base_offset=0):
    """Interpret byte sequences at known offsets as different types."""
    results = []

    # Try interpreting at different offsets
    interpretations = [
        (0, 2, 'uint16_le'),
        (2, 2, 'uint16_le'),
        (4, 1, 'uint8'),
        (5, 1, 'uint8'),
        (6, 2, 'uint16_le'),
        (8, 4, 'float32_le'),
        (8, 4, 'uint32_le'),
        (12, 4, 'float32_le'),
        (12, 4, 'uint32_le'),
    ]

    for offset, size, dtype in interpretations:
        if offset + size > len(data):
            continue

        chunk = data[offset:offset+size]

        if dtype == 'uint8':
            val = chunk[0]
            results.append(f"  +{offset:02d} uint8:  {val:3d} (0x{val:02X})")
        elif dtype == 'uint16_le':
            val = struct.unpack('<H', chunk)[0]
            results.append(f"  +{offset:02d} uint16: {val:5d} (0x{val:04X})")
        elif dtype == 'uint32_le':
            val = struct.unpack('<I', chunk)[0]
            results.append(f"  +{offset:02d} uint32: {val:10d} (0x{val:08X})")
        elif dtype == 'float32_le':
            val = struct.unpack('<f', chunk)[0]
            results.append(f"  +{offset:02d} float:  {val:.6f}")

    return '\n'.join(results)

def search_item_marker_patterns(frames):
    """Search 1: FF FF FF FF [ItemID] for all test items."""
    print("\n" + "="*80)
    print("SEARCH 1: FF FF FF FF [ItemID] Pattern for Test Items")
    print("="*80)

    results = []
    first_appearances = defaultdict(list)

    for item_id, item_name in TEST_ITEMS.items():
        item_bytes = item_id.to_bytes(2, 'little')
        pattern = MARKER + item_bytes

        results.append(f"\n--- Item {item_id} (0x{item_id:02X}): {item_name} ---")
        results.append(f"Pattern: {' '.join(f'{b:02X}' for b in pattern)}")

        found_in_frames = []
        for frame_num, data in frames.items():
            offset = 0
            matches = 0
            while True:
                pos = data.find(pattern, offset)
                if pos == -1:
                    break

                matches += 1
                if frame_num not in found_in_frames:
                    found_in_frames.append(frame_num)

                context = data[pos:pos+34]  # marker(4) + itemid(2) + context(28)
                results.append(f"\n  Frame {frame_num} @ offset {pos:08X}:")
                results.append(f"    {hex_dump(context, pos)}")

                offset = pos + 1

            if matches > 0:
                results.append(f"  Frame {frame_num}: {matches} match(es)")

        if found_in_frames:
            first_appearances[item_id] = min(found_in_frames)
            results.append(f"  FIRST APPEARANCE: Frame {first_appearances[item_id]}")
        else:
            results.append(f"  NOT FOUND in any frame")

    results.append(f"\n\nSUMMARY - First Appearances:")
    for item_id, frame in sorted(first_appearances.items()):
        results.append(f"  Item {item_id:3d} ({TEST_ITEMS[item_id]:20s}): Frame {frame}")

    return '\n'.join(results)

def search_all_marker_patterns(frames):
    """Search 2: All FF FF FF FF [XX 00] patterns."""
    print("\n" + "="*80)
    print("SEARCH 2: All FF FF FF FF [XX 00] Patterns")
    print("="*80)

    results = []
    frame_patterns = defaultdict(Counter)

    for frame_num, data in frames.items():
        offset = 0
        while True:
            pos = data.find(MARKER, offset)
            if pos == -1 or pos + 6 > len(data):
                break

            # Check if followed by [XX 00]
            byte5 = data[pos + 4]
            byte6 = data[pos + 5]

            if byte6 == 0x00:
                frame_patterns[frame_num][byte5] += 1

            offset = pos + 1

    # Analyze which XX values appear in which frames
    all_xx_values = set()
    for counter in frame_patterns.values():
        all_xx_values.update(counter.keys())

    results.append(f"\nFound {len(all_xx_values)} unique XX values in pattern FF FF FF FF [XX 00]\n")

    # Per-frame breakdown
    for frame_num in sorted(frame_patterns.keys()):
        counter = frame_patterns[frame_num]
        results.append(f"\nFrame {frame_num}: {len(counter)} unique XX values, {sum(counter.values())} total matches")

        # Show top 10 most frequent
        for xx, count in counter.most_common(10):
            results.append(f"  XX=0x{xx:02X} ({xx:3d}): {count:3d} occurrences")

    # Frame-specific appearances
    results.append(f"\n\nXX values that appear ONLY in specific frames:")
    xx_to_frames = defaultdict(set)
    for frame_num, counter in frame_patterns.items():
        for xx in counter:
            xx_to_frames[xx].add(frame_num)

    for xx, frames_set in sorted(xx_to_frames.items()):
        if len(frames_set) < len(frame_patterns):  # Not in all frames
            frames_list = sorted(frames_set)
            results.append(f"  XX=0x{xx:02X} ({xx:3d}): frames {frames_list}")

            # Highlight if matches known item IDs
            if xx in TEST_ITEMS:
                results.append(f"    ^ MATCHES ITEM: {TEST_ITEMS[xx]}")

    return '\n'.join(results)

def search_item_prefixes(frames):
    """Search 3: What 4-byte patterns precede item IDs."""
    print("\n" + "="*80)
    print("SEARCH 3: 4-Byte Prefixes Before Item IDs")
    print("="*80)

    results = []
    prefix_patterns = defaultdict(lambda: defaultdict(list))

    for item_id, item_name in TEST_ITEMS.items():
        item_bytes = item_id.to_bytes(2, 'little')

        for frame_num, data in frames.items():
            offset = 0
            while True:
                pos = data.find(item_bytes, offset)
                if pos == -1 or pos < 4:
                    break

                # Get 4 bytes before item ID
                prefix = data[pos-4:pos]
                if len(prefix) == 4:
                    prefix_hex = prefix.hex().upper()
                    prefix_patterns[item_id][prefix_hex].append((frame_num, pos))

                offset = pos + 1

    results.append("\nPrefix patterns for each item:\n")

    common_prefixes = Counter()
    for item_id, item_name in TEST_ITEMS.items():
        results.append(f"\n--- Item {item_id} (0x{item_id:02X}): {item_name} ---")

        patterns = prefix_patterns[item_id]
        if not patterns:
            results.append("  No matches found")
            continue

        for prefix_hex, occurrences in sorted(patterns.items(), key=lambda x: -len(x[1])):
            results.append(f"  Prefix {prefix_hex}: {len(occurrences)} occurrence(s)")
            common_prefixes[prefix_hex] += 1

            # Show first few occurrences
            for frame_num, pos in occurrences[:3]:
                results.append(f"    Frame {frame_num} @ 0x{pos:08X}")

    results.append(f"\n\nMost common prefixes across ALL items:")
    for prefix_hex, count in common_prefixes.most_common(5):
        results.append(f"  {prefix_hex}: appears before {count}/5 items")
        if prefix_hex == 'FFFFFFFF':
            results.append(f"    ^ THIS IS THE MARKER!")

    return '\n'.join(results)

def search_extended_records(frames):
    """Search 4: Extended record dumps with interpretation."""
    print("\n" + "="*80)
    print("SEARCH 4: Extended Record Dumps")
    print("="*80)

    results = []

    for item_id, item_name in TEST_ITEMS.items():
        item_bytes = item_id.to_bytes(2, 'little')
        pattern = MARKER + item_bytes

        results.append(f"\n{'='*60}")
        results.append(f"Item {item_id} (0x{item_id:02X}): {item_name}")
        results.append(f"{'='*60}")

        for frame_num, data in frames.items():
            pos = data.find(pattern)
            if pos == -1:
                continue

            # Dump 50 bytes starting from marker
            record = data[pos:pos+54]
            if len(record) < 20:
                continue

            results.append(f"\nFrame {frame_num} @ offset {pos:08X}:")

            # Hex dump in chunks
            for i in range(0, len(record), 16):
                chunk = record[i:i+16]
                hex_str = ' '.join(f'{b:02X}' for b in chunk)
                ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
                results.append(f"  {i:04X}: {hex_str:<48s} |{ascii_str}|")

            # Field interpretations (skip marker + item_id = first 6 bytes)
            results.append(f"\nField Interpretations (after marker+itemID):")
            payload = record[6:]
            results.append(interpret_bytes(payload, pos + 6))

            break  # Only show first occurrence per item

    return '\n'.join(results)

def search_inventory_progression(frames):
    """Search 5: Track inventory state progression."""
    print("\n" + "="*80)
    print("SEARCH 5: Inventory State Progression")
    print("="*80)

    results = []

    frame_counts = {}
    all_items_found = defaultdict(lambda: defaultdict(int))

    for frame_num, data in frames.items():
        count = 0
        offset = 0

        while True:
            pos = data.find(MARKER, offset)
            if pos == -1 or pos + 6 > len(data):
                break

            # Check if followed by [XX 00] pattern (item-like)
            byte5 = data[pos + 4]
            byte6 = data[pos + 5]

            if byte6 == 0x00:
                count += 1
                all_items_found[frame_num][byte5] += 1

            offset = pos + 1

        frame_counts[frame_num] = count

    results.append("\nTotal FF FF FF FF [XX 00] records per frame:\n")
    for frame_num in sorted(frame_counts.keys()):
        count = frame_counts[frame_num]
        results.append(f"  Frame {frame_num}: {count:3d} records")

    results.append(f"\n\nFrame-to-frame changes:")
    prev_count = None
    for frame_num in sorted(frame_counts.keys()):
        count = frame_counts[frame_num]
        if prev_count is not None:
            delta = count - prev_count
            if delta != 0:
                results.append(f"  Frame {frame_num-1} -> {frame_num}: {delta:+3d} records")
        prev_count = count

    results.append(f"\n\nTest items in each frame:")
    for frame_num in sorted(all_items_found.keys()):
        items = all_items_found[frame_num]
        test_items_found = [(xx, count) for xx, count in items.items() if xx in TEST_ITEMS]

        if test_items_found:
            results.append(f"\n  Frame {frame_num}:")
            for xx, count in sorted(test_items_found):
                results.append(f"    Item {xx:3d} (0x{xx:02X}) {TEST_ITEMS[xx]:20s}: {count} occurrence(s)")

    return '\n'.join(results)

def main():
    print("Item Pattern Hunt - VG Replay Analysis")
    print("="*80)

    # Load all frames
    print(f"\nLoading frames from: {REPLAY_BASE / REPLAY_NAME}")
    frames = {}
    for i in range(7):
        data = load_frame(i)
        if data:
            frames[i] = data
            print(f"  Frame {i}: {len(data):,} bytes")

    if not frames:
        print("ERROR: No frames loaded!")
        return

    # Run all searches
    output_lines = []
    output_lines.append("ITEM PATTERN HUNT - VG REPLAY ANALYSIS")
    output_lines.append("="*80)
    output_lines.append(f"Replay: {REPLAY_NAME}")
    output_lines.append(f"Frames: {len(frames)}")
    output_lines.append("")

    # Search 1
    result = search_item_marker_patterns(frames)
    print(result)
    output_lines.append(result)

    # Search 2
    result = search_all_marker_patterns(frames)
    print(result)
    output_lines.append(result)

    # Search 3
    result = search_item_prefixes(frames)
    print(result)
    output_lines.append(result)

    # Search 4
    result = search_extended_records(frames)
    print(result)
    output_lines.append(result)

    # Search 5
    result = search_inventory_progression(frames)
    print(result)
    output_lines.append(result)

    # Save output
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text('\n'.join(output_lines), encoding='utf-8')
    print(f"\n{'='*80}")
    print(f"Output saved to: {OUTPUT_PATH}")
    print(f"{'='*80}")

if __name__ == '__main__':
    main()


