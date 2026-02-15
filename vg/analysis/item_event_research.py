#!/usr/bin/env python3
"""
Item Event Research - Find item purchase/equip events in VGR replays.

Instead of searching for raw item ID bytes (too many false positives),
look for STRUCTURED records that link entity IDs to item IDs.

Approach:
1. For each known item ID, find all occurrences in a late-game frame
2. At each occurrence, check fixed offsets for player entity IDs
3. If a consistent offset has player entity IDs, that's the item record format
4. Validate by checking if builds make sense (crystal hero → crystal items)

Usage:
    python -m vg.analysis.item_event_research
"""

import sys
import struct
import json
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Set, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from vg.core.vgr_mapping import ITEM_ID_MAP

# Player block markers
PLAYER_MARKERS = [b'\xDA\x03\xEE', b'\xE0\x03\xEE']


def load_replay(replay_dir):
    """Load all frames from a replay directory."""
    frames = sorted(
        Path(replay_dir).glob('*.vgr'),
        key=lambda p: int(p.stem.split('.')[-1])
    )
    return frames


def extract_players(data):
    """Extract player info from frame 0."""
    players = []
    seen_eids = set()
    for marker in PLAYER_MARKERS:
        pos = 0
        while True:
            pos = data.find(marker, pos)
            if pos == -1:
                break
            # Entity ID at +0xA5 (uint16 LE)
            if pos + 0xD6 <= len(data):
                eid = struct.unpack('<H', data[pos + 0xA5:pos + 0xA5 + 2])[0]
                team_byte = data[pos + 0xD5]
                team = "left" if team_byte == 1 else "right" if team_byte == 2 else "?"
                # Name extraction
                name_start = pos + len(marker)
                name_end = name_start
                while name_end < len(data) and name_end < name_start + 30:
                    b = data[name_end]
                    if b < 32 or b > 126:
                        break
                    name_end += 1
                name = data[name_start:name_end].decode('ascii', errors='replace')
                if eid not in seen_eids and len(name) >= 3 and not name.startswith('GameMode'):
                    players.append({
                        'name': name, 'eid_le': eid, 'team': team,
                        'eid_be': struct.unpack('>H', struct.pack('<H', eid))[0],
                    })
                    seen_eids.add(eid)
            pos += 1
    return players


def find_t3_items_in_frame(data, exclude_ranges=None):
    """Find T3 item IDs in frame data, return (item_id, offset) list.

    Only search for T3 items (tier >= 3) to reduce noise.
    exclude_ranges: list of (start, end) byte ranges to skip (e.g., player blocks)
    """
    results = []
    exclude_ranges = exclude_ranges or []

    for item_id, info in ITEM_ID_MAP.items():
        if info.get('tier', 0) < 3:
            continue
        item_bytes = struct.pack('<H', item_id)
        pos = 0
        while True:
            pos = data.find(item_bytes, pos)
            if pos == -1:
                break
            # Skip if in excluded range (player blocks)
            skip = False
            for ex_start, ex_end in exclude_ranges:
                if ex_start <= pos <= ex_end:
                    skip = True
                    break
            if not skip:
                results.append((item_id, pos))
            pos += 1
    return results


def analyze_offset_pattern(data, item_occurrences, player_eids_le, player_eids_be):
    """For each item occurrence, check various offsets for player entity IDs.

    Returns: dict of offset -> list of (item_id, item_offset, eid, endian)
    """
    offset_hits = defaultdict(list)

    for item_id, item_pos in item_occurrences:
        # Check offsets -32 to +32 (excluding 0, 1 which are the item ID itself)
        for offset in range(-32, 33):
            if offset in (0, 1):
                continue
            check_pos = item_pos + offset
            if check_pos < 0 or check_pos + 2 > len(data):
                continue
            val = struct.unpack('<H', data[check_pos:check_pos + 2])[0]
            if val in player_eids_le:
                offset_hits[offset].append((item_id, item_pos, val, 'LE'))
            val_be = struct.unpack('>H', data[check_pos:check_pos + 2])[0]
            if val_be in player_eids_be:
                offset_hits[offset].append((item_id, item_pos, val_be, 'BE'))

    return offset_hits


def check_build_coherence(player_items, players):
    """Check if detected item builds make sense per player/role."""
    # Simple heuristic: count items per player
    for p in players:
        items = player_items.get(p['eid_le'], [])
        if items:
            cats = Counter(ITEM_ID_MAP.get(iid, {}).get('category', '?') for iid in items)
            print(f"  {p['name']} ({p['team']}): {len(items)} items - {dict(cats)}")
            for iid in sorted(set(items)):
                info = ITEM_ID_MAP.get(iid, {})
                print(f"    - {info.get('name', f'?{iid}')} (T{info.get('tier', '?')})")


def main():
    # Load first tournament replay
    truth_path = Path("vg/output/tournament_truth.json")
    with open(truth_path) as f:
        truth = json.load(f)

    match = truth['matches'][0]
    replay_file = match['replay_file']
    replay_dir = Path(replay_file).parent
    replay_name = Path(replay_file).stem.rsplit('.', 1)[0]

    print(f"Replay: {match['replay_name']}")

    # Load frames
    frames = load_replay(replay_dir)
    print(f"Total frames: {len(frames)}")

    # Get players from frame 0
    frame0_data = frames[0].read_bytes()
    players = extract_players(frame0_data)
    print(f"\nPlayers ({len(players)}):")
    for p in players:
        print(f"  {p['name']} (EID LE={p['eid_le']}, BE={p['eid_be']}, {p['team']})")

    player_eids_le = {p['eid_le'] for p in players}
    player_eids_be = {p['eid_be'] for p in players}

    # Find player block ranges to exclude
    player_block_ranges = []
    for marker in PLAYER_MARKERS:
        pos = 0
        while True:
            pos = frame0_data.find(marker, pos)
            if pos == -1:
                break
            player_block_ranges.append((pos, pos + 0x200))
            pos += 1

    # Analyze LAST frame (players have final builds)
    last_frame_data = frames[-1].read_bytes()
    # Also find player blocks in last frame to exclude
    last_player_ranges = []
    for marker in PLAYER_MARKERS:
        pos = 0
        while True:
            pos = last_frame_data.find(marker, pos)
            if pos == -1:
                break
            last_player_ranges.append((pos, pos + 0x200))
            pos += 1

    print(f"\n--- Analyzing LAST frame ({len(last_frame_data):,} bytes) ---")

    # Find T3 items outside player blocks
    t3_items = find_t3_items_in_frame(last_frame_data, last_player_ranges)
    print(f"T3 item occurrences (outside player blocks): {len(t3_items)}")

    # Count unique items
    unique_items = Counter(iid for iid, _ in t3_items)
    print(f"Unique T3 items found: {len(unique_items)}")
    for iid, count in unique_items.most_common(15):
        info = ITEM_ID_MAP.get(iid, {})
        print(f"  {info.get('name', f'?{iid}'):25s} x{count}")

    # Analyze offset patterns - which offsets consistently have player entity IDs?
    print(f"\n--- Offset pattern analysis ---")
    offset_hits = analyze_offset_pattern(
        last_frame_data, t3_items, player_eids_le, player_eids_be
    )

    # Sort by frequency
    print(f"Offsets with player entity IDs near T3 items:")
    for offset in sorted(offset_hits.keys(), key=lambda k: -len(offset_hits[k])):
        hits = offset_hits[offset]
        if len(hits) < 3:
            continue
        endians = Counter(h[3] for h in hits)
        # Check how many unique players are referenced
        unique_players = len(set(h[2] for h in hits))
        print(f"  Offset {offset:+3d}: {len(hits):4d} hits, {unique_players} unique players, endian={dict(endians)}")

    # For the top offset, build per-player inventories
    if offset_hits:
        best_offset = max(offset_hits.keys(), key=lambda k: len(offset_hits[k]))
        print(f"\n--- Best offset: {best_offset:+d} ({len(offset_hits[best_offset])} hits) ---")

        # Build player -> items mapping
        player_items = defaultdict(list)
        for item_id, item_pos, eid, endian in offset_hits[best_offset]:
            if endian == 'LE':
                player_items[eid].append(item_id)
            else:
                # Convert BE back to LE for lookup
                eid_le = struct.unpack('<H', struct.pack('>H', eid))[0]
                player_items[eid_le].append(item_id)

        print("\nPer-player builds (best offset):")
        check_build_coherence(player_items, players)

    # Also try mid-game frame
    mid_idx = len(frames) // 2
    mid_data = frames[mid_idx].read_bytes()
    mid_player_ranges = []
    for marker in PLAYER_MARKERS:
        pos = 0
        while True:
            pos = mid_data.find(marker, pos)
            if pos == -1:
                break
            mid_player_ranges.append((pos, pos + 0x200))
            pos += 1

    mid_items = find_t3_items_in_frame(mid_data, mid_player_ranges)
    print(f"\n--- Mid-game frame {mid_idx} ({len(mid_data):,} bytes) ---")
    print(f"T3 item occurrences: {len(mid_items)}")

    mid_offset_hits = analyze_offset_pattern(
        mid_data, mid_items, player_eids_le, player_eids_be
    )

    if mid_offset_hits:
        # Compare with last frame - consistent offsets?
        print("Consistent offsets (appear in both mid and last frame):")
        for offset in sorted(set(offset_hits.keys()) & set(mid_offset_hits.keys()),
                           key=lambda k: -(len(offset_hits.get(k, [])) + len(mid_offset_hits.get(k, [])))):
            last_n = len(offset_hits.get(offset, []))
            mid_n = len(mid_offset_hits.get(offset, []))
            if last_n >= 3 and mid_n >= 3:
                print(f"  Offset {offset:+3d}: last={last_n}, mid={mid_n}")


if __name__ == '__main__':
    main()
