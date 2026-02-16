#!/usr/bin/env python3
"""
Item-to-Player Mapping Research
================================
Investigates how items are associated with specific players in VGR replay data.

Approach:
1. Extract player entity IDs from player blocks in frame 0
2. For known item IDs, search for byte patterns that co-locate item_id and entity_id
3. Search for item purchase/equip event headers (XX 04 YY patterns)
4. Check if player blocks in later frames contain item slots at fixed offsets
5. Look at credit records and event streams near item ID occurrences

Usage:
    python -m vg.analysis.item_player_mapping
"""

import sys
import struct
import json
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Set, Tuple, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from vg.core.vgr_mapping import ITEM_ID_MAP, BINARY_HERO_ID_MAP

# Player block markers
PLAYER_BLOCK_MARKER = bytes([0xDA, 0x03, 0xEE])
PLAYER_BLOCK_MARKER_ALT = bytes([0xE0, 0x03, 0xEE])
HERO_ID_OFFSET = 0x0A9
ENTITY_ID_OFFSET = 0xA5
TEAM_OFFSET = 0xD5

# Known event headers from KDA detection
KILL_HEADER = bytes([0x18, 0x04, 0x1C])
DEATH_HEADER = bytes([0x08, 0x04, 0x31])
CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])

# T3 items that are distinctive enough to search for
T3_ITEMS = {k: v for k, v in ITEM_ID_MAP.items() if v.get('tier', 0) == 3}
T2_ITEMS = {k: v for k, v in ITEM_ID_MAP.items() if v.get('tier', 0) == 2}


def load_truth():
    """Load tournament truth data."""
    truth_path = Path(__file__).parent.parent / "output" / "tournament_truth.json"
    with open(truth_path, 'r') as f:
        return json.load(f)


def load_frames(replay_file: str) -> List[Tuple[int, bytes]]:
    """Load all frames for a replay, returns list of (frame_idx, data)."""
    replay_path = Path(replay_file)
    frame_dir = replay_path.parent
    replay_name = replay_path.stem.rsplit('.', 1)[0]  # Remove .0 suffix -> base name

    frames = list(frame_dir.glob(f"{replay_name}.*.vgr"))
    def frame_index(p: Path) -> int:
        try:
            return int(p.stem.split('.')[-1])
        except ValueError:
            return 0
    frames.sort(key=frame_index)

    result = []
    for fp in frames:
        idx = frame_index(fp)
        result.append((idx, fp.read_bytes()))
    return result


def extract_players(data: bytes) -> List[Dict]:
    """Extract player info from frame 0 player blocks."""
    players = []
    seen = set()
    search_start = 0
    markers = (PLAYER_BLOCK_MARKER, PLAYER_BLOCK_MARKER_ALT)

    while True:
        pos = -1
        marker = None
        for candidate in markers:
            idx = data.find(candidate, search_start)
            if idx != -1 and (pos == -1 or idx < pos):
                pos = idx
                marker = candidate
        if pos == -1 or marker is None:
            break

        name_start = pos + len(marker)
        name_end = name_start
        while name_end < len(data) and name_end < name_start + 30:
            byte = data[name_end]
            if byte < 32 or byte > 126:
                break
            name_end += 1

        name = ""
        if name_end > name_start:
            try:
                name = data[name_start:name_end].decode('ascii')
            except Exception:
                pass

        if len(name) >= 3 and not name.startswith('GameMode') and name not in seen:
            seen.add(name)
            entity_id_le = None
            entity_id_be = None
            if pos + ENTITY_ID_OFFSET + 2 <= len(data):
                entity_id_le = int.from_bytes(data[pos + ENTITY_ID_OFFSET:pos + ENTITY_ID_OFFSET + 2], 'little')
                entity_id_be = struct.unpack_from(">H", data, pos + ENTITY_ID_OFFSET)[0]

            team_id = data[pos + TEAM_OFFSET] if pos + TEAM_OFFSET < len(data) else None
            team = {1: "left", 2: "right"}.get(team_id, "unknown")

            hero_name = "Unknown"
            if pos + HERO_ID_OFFSET + 2 <= len(data):
                binary_hero_id = int.from_bytes(data[pos + HERO_ID_OFFSET:pos + HERO_ID_OFFSET + 2], 'little')
                hero_name = BINARY_HERO_ID_MAP.get(binary_hero_id, "Unknown")

            players.append({
                'name': name,
                'entity_id_le': entity_id_le,
                'entity_id_be': entity_id_be,
                'team': team,
                'hero': hero_name,
                'block_offset': pos,
                'position': len(players),
            })

        search_start = pos + 1

    return players


def search_item_entity_proximity(data: bytes, item_ids: Set[int], entity_ids_be: Set[int],
                                  max_distance: int = 20) -> List[Dict]:
    """
    Search for occurrences where an item ID (uint16 LE) appears near
    a player entity ID (uint16 BE) within max_distance bytes.
    """
    results = []

    for item_id in sorted(item_ids):
        item_bytes_le = struct.pack('<H', item_id)
        item_bytes_be = struct.pack('>H', item_id)
        item_name = ITEM_ID_MAP[item_id]['name']

        for encoding, item_bytes in [('LE', item_bytes_le), ('BE', item_bytes_be)]:
            offset = 0
            while True:
                pos = data.find(item_bytes, offset)
                if pos == -1:
                    break

                # Check vicinity for entity IDs
                search_start = max(0, pos - max_distance)
                search_end = min(len(data), pos + max_distance + 2)
                vicinity = data[search_start:search_end]

                for eid_be in entity_ids_be:
                    eid_bytes = struct.pack('>H', eid_be)
                    eid_pos_in_vicinity = vicinity.find(eid_bytes)
                    if eid_pos_in_vicinity != -1:
                        abs_eid_pos = search_start + eid_pos_in_vicinity
                        distance = abs_eid_pos - pos
                        if distance != 0:  # Skip if they overlap
                            context_start = max(0, min(pos, abs_eid_pos) - 4)
                            context_end = min(len(data), max(pos, abs_eid_pos) + 6)
                            results.append({
                                'item_id': item_id,
                                'item_name': item_name,
                                'item_encoding': encoding,
                                'item_offset': pos,
                                'entity_id_be': eid_be,
                                'eid_offset': abs_eid_pos,
                                'distance': distance,
                                'context_hex': data[context_start:context_end].hex(),
                            })

                offset = pos + 1

    return results


def search_04_headers_near_items(data: bytes, item_ids: Set[int],
                                  search_range: int = 30) -> Dict[str, Counter]:
    """
    For each item ID occurrence, look for [XX 04 YY] headers within search_range bytes.
    This follows the event protocol pattern where 04 is common in action headers.
    """
    header_counts = defaultdict(Counter)  # item_id -> Counter of (XX, YY) tuples

    for item_id in sorted(item_ids):
        item_bytes_le = struct.pack('<H', item_id)
        offset = 0
        while True:
            pos = data.find(item_bytes_le, offset)
            if pos == -1:
                break

            # Search backwards and forwards for [XX 04 YY] patterns
            start = max(0, pos - search_range)
            end = min(len(data), pos + search_range)

            for i in range(start, end - 2):
                if data[i + 1] == 0x04:
                    header = (data[i], data[i + 2])
                    header_counts[item_id][header] += 1

            offset = pos + 1

    return header_counts


def check_player_block_item_slots(frames: List[Tuple[int, bytes]], players: List[Dict],
                                   block_size: int = 0x200) -> Dict[str, List]:
    """
    Check if player blocks in later frames contain item IDs at fixed offsets.
    Compare player block regions across frames to find changing item slots.
    """
    results = {}
    all_item_ids = set(ITEM_ID_MAP.keys())

    # Use the last few frames (items should be fully built by end)
    late_frames = frames[-3:] if len(frames) > 3 else frames

    for frame_idx, data in late_frames:
        frame_results = {}
        for player in players:
            player_items = []
            block_start = player['block_offset']

            # Scan the player block region for item IDs
            scan_end = min(len(data), block_start + block_size)
            if block_start >= len(data):
                continue

            for off in range(block_start, scan_end - 1):
                val_le = int.from_bytes(data[off:off + 2], 'little')
                if val_le in all_item_ids and ITEM_ID_MAP[val_le].get('tier', 0) >= 2:
                    rel_offset = off - block_start
                    player_items.append({
                        'item_id': val_le,
                        'item_name': ITEM_ID_MAP[val_le]['name'],
                        'tier': ITEM_ID_MAP[val_le]['tier'],
                        'relative_offset': hex(rel_offset),
                        'absolute_offset': hex(off),
                    })

            if player_items:
                frame_results[player['name']] = player_items

        if frame_results:
            results[f"frame_{frame_idx}"] = frame_results

    return results


def search_item_event_patterns(data: bytes, entity_ids_be: Dict[int, str],
                                 item_ids: Set[int]) -> List[Dict]:
    """
    Search for structured event patterns that contain both an entity ID and item ID.
    Try common event layouts:
      - [header 3B] [00 00] [eid BE 2B] [... item_id ...]
      - [item_id 2B LE] [00 00] [eid BE 2B]
      - [eid BE 2B] [item_id 2B LE]
    """
    results = []

    for item_id in sorted(item_ids):
        item_le = struct.pack('<H', item_id)
        item_name = ITEM_ID_MAP[item_id]['name']

        offset = 0
        while True:
            pos = data.find(item_le, offset)
            if pos == -1:
                break

            # Check several fixed-offset positions for entity IDs
            for delta in range(-16, 17, 2):
                if delta == 0:
                    continue
                eid_pos = pos + delta
                if 0 <= eid_pos and eid_pos + 2 <= len(data):
                    eid_val = struct.unpack_from(">H", data, eid_pos)[0]
                    if eid_val in entity_ids_be:
                        ctx_start = max(0, min(pos, eid_pos) - 8)
                        ctx_end = min(len(data), max(pos + 2, eid_pos + 2) + 8)
                        results.append({
                            'item_id': item_id,
                            'item_name': item_name,
                            'item_offset': pos,
                            'eid': eid_val,
                            'player': entity_ids_be[eid_val],
                            'eid_offset': eid_pos,
                            'delta': delta,
                            'context_hex': data[ctx_start:ctx_end].hex(),
                        })

            offset = pos + 1

    return results


def analyze_delta_frequency(events: List[Dict]) -> Dict[int, int]:
    """Count how many item-entity co-occurrences happen at each delta offset."""
    delta_counts = Counter()
    for ev in events:
        delta_counts[ev['delta']] += 1
    return dict(sorted(delta_counts.items(), key=lambda x: -x[1]))


def scan_all_04_patterns(data: bytes, entity_ids_be: Set[int]) -> Dict[Tuple[int, int], List]:
    """
    Scan for all [XX 04 YY] [00 00] [eid BE] patterns and group by (XX, YY).
    Then check if any of those patterns also have item IDs nearby.
    """
    pattern_groups = defaultdict(list)
    pos = 0
    while pos < len(data) - 7:
        if data[pos + 1] == 0x04 and data[pos + 3] == 0x00 and data[pos + 4] == 0x00:
            xx = data[pos]
            yy = data[pos + 2]
            eid = struct.unpack_from(">H", data, pos + 5)[0]
            if eid in entity_ids_be:
                # Check for item IDs in the bytes following eid
                for item_off in range(7, 30):
                    if pos + item_off + 2 <= len(data):
                        val_le = struct.unpack_from("<H", data, pos + item_off)[0]
                        val_be = struct.unpack_from(">H", data, pos + item_off)[0]
                        if val_le in ITEM_ID_MAP and ITEM_ID_MAP[val_le].get('tier', 0) >= 1:
                            pattern_groups[(xx, yy)].append({
                                'header_offset': pos,
                                'eid': eid,
                                'item_id': val_le,
                                'item_name': ITEM_ID_MAP[val_le]['name'],
                                'item_relative_offset': item_off,
                                'item_encoding': 'LE',
                                'context': data[pos:pos+item_off+4].hex(),
                            })
                        if val_be in ITEM_ID_MAP and ITEM_ID_MAP[val_be].get('tier', 0) >= 1:
                            pattern_groups[(xx, yy)].append({
                                'header_offset': pos,
                                'eid': eid,
                                'item_id': val_be,
                                'item_name': ITEM_ID_MAP[val_be]['name'],
                                'item_relative_offset': item_off,
                                'item_encoding': 'BE',
                                'context': data[pos:pos+item_off+4].hex(),
                            })
        pos += 1

    return pattern_groups


def search_credit_records_with_items(data: bytes, entity_ids_be: Dict[int, str]) -> List[Dict]:
    """
    Search for credit records [10 04 1D] near item IDs.
    Maybe item purchases show up as a specific credit/cost record.
    """
    results = []
    pos = 0
    while True:
        pos = data.find(CREDIT_HEADER, pos)
        if pos == -1:
            break
        if pos + 12 > len(data):
            pos += 1
            continue

        if data[pos+3:pos+5] != b'\x00\x00':
            pos += 1
            continue

        eid = struct.unpack_from(">H", data, pos + 5)[0]
        if eid not in entity_ids_be:
            pos += 1
            continue

        value = struct.unpack_from(">f", data, pos + 7)[0]
        action = data[pos + 11] if pos + 11 < len(data) else None

        # Check if any item ID appears within 20 bytes after the credit record
        for item_off in range(12, 32):
            if pos + item_off + 2 <= len(data):
                val_le = struct.unpack_from("<H", data, pos + item_off)[0]
                if val_le in ITEM_ID_MAP and ITEM_ID_MAP[val_le].get('tier', 0) >= 2:
                    results.append({
                        'credit_offset': pos,
                        'eid': eid,
                        'player': entity_ids_be[eid],
                        'value': round(value, 2),
                        'action': hex(action) if action is not None else None,
                        'item_id': val_le,
                        'item_name': ITEM_ID_MAP[val_le]['name'],
                        'item_at_offset': item_off,
                        'context': data[pos:pos+item_off+4].hex(),
                    })

        pos += 3

    return results


def player_block_diff_across_frames(frames: List[Tuple[int, bytes]], players: List[Dict],
                                      block_size: int = 0x200) -> Dict:
    """
    Compare player blocks across frames to find offsets that change
    and might correspond to item acquisitions.
    Focus on offsets that hold values in the item ID range.
    """
    if len(frames) < 2:
        return {}

    results = {}
    # Sample frames: first, middle, last
    sample_indices = [0, len(frames) // 2, len(frames) - 1]
    sample_frames = [frames[i] for i in sample_indices if i < len(frames)]

    for player in players:
        block_start = player['block_offset']
        changing_offsets = defaultdict(list)  # relative offset -> list of (frame_idx, value)

        for frame_idx, data in sample_frames:
            if block_start + block_size > len(data):
                continue
            block_data = data[block_start:block_start + block_size]

            for off in range(0, min(len(block_data) - 1, block_size), 2):
                val = struct.unpack_from('<H', block_data, off)[0]
                changing_offsets[off].append((frame_idx, val))

        # Find offsets where value changes AND falls in item range at some point
        item_relevant_offsets = {}
        for off, frame_vals in changing_offsets.items():
            values = [v for _, v in frame_vals]
            if len(set(values)) > 1:  # Value changed across frames
                for val in values:
                    if val in ITEM_ID_MAP and ITEM_ID_MAP[val].get('tier', 0) >= 1:
                        item_relevant_offsets[hex(off)] = [
                            {'frame': fi, 'value': v,
                             'item': ITEM_ID_MAP.get(v, {}).get('name', f'raw_{v}')}
                            for fi, v in frame_vals
                        ]
                        break

        if item_relevant_offsets:
            results[player['name']] = item_relevant_offsets

    return results


def main():
    print("=" * 80)
    print("ITEM-TO-PLAYER MAPPING RESEARCH")
    print("=" * 80)

    truth = load_truth()
    match_1 = truth['matches'][0]
    replay_file = match_1['replay_file']
    print(f"\nMatch 1: {match_1['replay_name'][:40]}...")
    print(f"Replay: {replay_file}")

    # Load frames
    print("\n--- Loading frames ---")
    frames = load_frames(replay_file)
    print(f"Loaded {len(frames)} frames")

    if not frames:
        print("ERROR: No frames found!")
        return

    # Extract players from frame 0
    print("\n--- Extracting players from frame 0 ---")
    frame0_data = frames[0][1]
    players = extract_players(frame0_data)
    print(f"Found {len(players)} players:")

    entity_ids_be = {}  # BE eid -> player name
    entity_ids_be_set = set()
    for p in players:
        print(f"  {p['name']:<20} team={p['team']:<6} hero={p['hero']:<15} "
              f"eid_le=0x{p['entity_id_le']:04X} eid_be=0x{p['entity_id_be']:04X}")
        entity_ids_be[p['entity_id_be']] = p['name']
        entity_ids_be_set.add(p['entity_id_be'])

    # Use last frame for most analysis (items are fully built)
    last_frame_idx, last_frame_data = frames[-1]
    print(f"\nUsing last frame (#{last_frame_idx}) for analysis, size={len(last_frame_data)} bytes")

    # Also concatenate all frames for event scanning
    all_data = b"".join(d for _, d in frames)
    print(f"Total data across all frames: {len(all_data)} bytes")

    # ===== ANALYSIS 1: Item IDs near entity IDs in last frame =====
    print("\n" + "=" * 80)
    print("ANALYSIS 1: T3 Item IDs near Player Entity IDs (last frame)")
    print("=" * 80)
    t3_ids = set(T3_ITEMS.keys())
    events = search_item_event_patterns(last_frame_data, entity_ids_be, t3_ids)
    print(f"Found {len(events)} item-entity co-occurrences (T3 items, last frame)")

    if events:
        # Show delta frequency
        delta_freq = analyze_delta_frequency(events)
        print("\nDelta frequency (eid_offset - item_offset):")
        for delta, count in list(delta_freq.items())[:20]:
            print(f"  delta={delta:+4d}: {count} occurrences")

        # Show top events grouped by delta
        print("\nTop co-occurrences by most common deltas:")
        for delta in sorted(delta_freq, key=lambda d: -delta_freq[d])[:5]:
            subset = [e for e in events if e['delta'] == delta]
            print(f"\n  Delta {delta:+d} ({delta_freq[delta]} hits):")
            # Show unique item-player pairs
            seen = set()
            for e in subset[:15]:
                key = (e['item_id'], e['player'])
                if key not in seen:
                    seen.add(key)
                    print(f"    {e['item_name']:<25} -> {e['player']:<20} ctx={e['context_hex'][:60]}")

    # ===== ANALYSIS 2: T3 Items in player blocks of late frames =====
    print("\n" + "=" * 80)
    print("ANALYSIS 2: Item IDs in Player Block Regions (late frames)")
    print("=" * 80)
    block_items = check_player_block_item_slots(frames, players, block_size=0x300)
    for frame_key, frame_data_dict in block_items.items():
        print(f"\n  {frame_key}:")
        for pname, items in frame_data_dict.items():
            t3_items_found = [it for it in items if it['tier'] == 3]
            if t3_items_found:
                print(f"    {pname}:")
                for it in t3_items_found:
                    print(f"      {it['item_name']:<25} (ID {it['item_id']}) at offset {it['relative_offset']}")

    # ===== ANALYSIS 3: [XX 04 YY] headers with entity IDs and item IDs =====
    print("\n" + "=" * 80)
    print("ANALYSIS 3: [XX 04 YY] event headers with entity+item (all frames)")
    print("=" * 80)
    pattern_groups = scan_all_04_patterns(all_data, entity_ids_be_set)
    print(f"Found {len(pattern_groups)} distinct (XX, YY) header patterns with item+entity co-occurrence")

    for (xx, yy), hits in sorted(pattern_groups.items(), key=lambda x: -len(x[1])):
        if len(hits) < 3:
            continue
        # Count unique items and players
        unique_items = set((h['item_id'], h['item_name']) for h in hits)
        unique_eids = set(h['eid'] for h in hits)
        print(f"\n  [{xx:02X} 04 {yy:02X}]: {len(hits)} hits, "
              f"{len(unique_items)} unique items, {len(unique_eids)} unique players")
        # Show item offset distribution
        offset_dist = Counter(h['item_relative_offset'] for h in hits)
        print(f"    Item at relative offsets: {dict(offset_dist.most_common(5))}")
        # Show first few examples
        for h in hits[:5]:
            player = entity_ids_be.get(h['eid'], f"eid_{h['eid']:04X}")
            print(f"    {h['item_name']:<25} -> {player:<20} "
                  f"enc={h['item_encoding']} off={h['item_relative_offset']} "
                  f"ctx={h['context'][:60]}")

    # ===== ANALYSIS 4: Credit records near items =====
    print("\n" + "=" * 80)
    print("ANALYSIS 4: Credit records [10 04 1D] near item IDs (all frames)")
    print("=" * 80)
    credit_items = search_credit_records_with_items(all_data, entity_ids_be)
    print(f"Found {len(credit_items)} credit records near item IDs")
    if credit_items:
        # Group by item
        by_item = defaultdict(list)
        for ci in credit_items:
            by_item[ci['item_id']].append(ci)
        print("\nItems found near credit records:")
        for item_id in sorted(by_item.keys()):
            hits = by_item[item_id]
            players_found = set(h['player'] for h in hits)
            print(f"  {ITEM_ID_MAP[item_id]['name']:<25} (ID {item_id}): "
                  f"{len(hits)} hits, players: {players_found}")
            # Show first example
            ex = hits[0]
            print(f"    Example: value={ex['value']}, action={ex['action']}, "
                  f"item_at_offset={ex['item_at_offset']}")
            print(f"    Context: {ex['context'][:80]}")

    # ===== ANALYSIS 5: Player block diff across frames =====
    print("\n" + "=" * 80)
    print("ANALYSIS 5: Player block diffs across frames (item-range values)")
    print("=" * 80)
    diffs = player_block_diff_across_frames(frames, players, block_size=0x300)
    if diffs:
        for pname, offsets in diffs.items():
            print(f"\n  {pname}:")
            for off, vals in sorted(offsets.items()):
                print(f"    Offset {off}:")
                for v in vals:
                    print(f"      Frame {v['frame']}: {v['item']}")
    else:
        print("  No item-range values found changing across sampled frames")

    # ===== ANALYSIS 6: Brute-force search for item purchase events =====
    print("\n" + "=" * 80)
    print("ANALYSIS 6: Brute-force item purchase event search")
    print("=" * 80)
    print("Searching for any [XX 04 YY] [00 00] [eid BE] patterns where")
    print("the subsequent payload contains an item ID at a consistent offset...")

    # For each (XX, YY) header pattern, check if it consistently maps items to players
    # across multiple occurrences
    promising = {}
    for (xx, yy), hits in pattern_groups.items():
        if len(hits) < 5:
            continue
        # Check if items at a consistent offset
        offset_counts = Counter(h['item_relative_offset'] for h in hits)
        best_offset, best_count = offset_counts.most_common(1)[0]
        if best_count >= 3:
            consistency = best_count / len(hits)
            if consistency >= 0.3:
                promising[(xx, yy)] = {
                    'total_hits': len(hits),
                    'best_offset': best_offset,
                    'best_count': best_count,
                    'consistency': round(consistency, 2),
                    'unique_items': len(set(h['item_id'] for h in hits)),
                    'unique_players': len(set(h['eid'] for h in hits)),
                    'sample_items': list(set(h['item_name'] for h in hits))[:10],
                }

    if promising:
        print(f"\nFound {len(promising)} promising header patterns:")
        for (xx, yy), info in sorted(promising.items(), key=lambda x: -x[1]['consistency']):
            print(f"\n  [{xx:02X} 04 {yy:02X}]:")
            print(f"    Total hits: {info['total_hits']}")
            print(f"    Best item offset: +{info['best_offset']} bytes from header")
            print(f"    Consistency: {info['consistency']} ({info['best_count']}/{info['total_hits']})")
            print(f"    Unique items: {info['unique_items']}, Unique players: {info['unique_players']}")
            print(f"    Sample items: {info['sample_items'][:5]}")
    else:
        print("  No promising patterns found with consistency >= 0.3")

    # ===== ANALYSIS 7: Search for item IDs stored as Big Endian =====
    print("\n" + "=" * 80)
    print("ANALYSIS 7: Item IDs as Big Endian near entity IDs")
    print("=" * 80)
    # Some values might be stored BE like entity IDs
    events_be = search_item_event_patterns(last_frame_data, entity_ids_be,
                                            {k for k in T3_ITEMS.keys()})
    # Already covered in Analysis 1, but let's look for BE item encoding specifically
    # by searching for item IDs encoded as BE
    be_hits = []
    for item_id in sorted(T3_ITEMS.keys()):
        item_be = struct.pack('>H', item_id)
        item_name = ITEM_ID_MAP[item_id]['name']
        offset = 0
        while True:
            pos = last_frame_data.find(item_be, offset)
            if pos == -1:
                break
            # Check vicinity for entity IDs
            for delta in range(-12, 13, 2):
                if delta == 0:
                    continue
                eid_pos = pos + delta
                if 0 <= eid_pos and eid_pos + 2 <= len(last_frame_data):
                    eid_val = struct.unpack_from(">H", last_frame_data, eid_pos)[0]
                    if eid_val in entity_ids_be:
                        be_hits.append({
                            'item_id': item_id,
                            'item_name': item_name,
                            'delta': delta,
                            'player': entity_ids_be[eid_val],
                        })
            offset = pos + 1

    if be_hits:
        delta_freq_be = Counter(h['delta'] for h in be_hits)
        print(f"Found {len(be_hits)} BE item-entity co-occurrences")
        print("Delta frequency:")
        for d, c in delta_freq_be.most_common(10):
            print(f"  delta={d:+4d}: {c}")
        # Show unique pairs at most common delta
        best_d = delta_freq_be.most_common(1)[0][0]
        print(f"\nItem-player pairs at delta={best_d:+d}:")
        seen = set()
        for h in be_hits:
            if h['delta'] == best_d:
                key = (h['item_id'], h['player'])
                if key not in seen:
                    seen.add(key)
                    print(f"  {h['item_name']:<25} -> {h['player']}")
    else:
        print("  No BE item-entity co-occurrences found")

    # ===== ANALYSIS 8: Detailed player block scan at wide range of offsets =====
    print("\n" + "=" * 80)
    print("ANALYSIS 8: Comprehensive player block scan for item slots")
    print("=" * 80)
    print("Scanning each player block in last frame for ALL item ID values at every offset...")

    for player in players:
        block_start = player['block_offset']
        scan_size = 0x400  # Extended scan
        if block_start + scan_size > len(last_frame_data):
            scan_size = len(last_frame_data) - block_start

        items_found = []
        for off in range(0, scan_size - 1):
            val = struct.unpack_from('<H', last_frame_data, block_start + off)[0]
            if val in ITEM_ID_MAP:
                item = ITEM_ID_MAP[val]
                if item.get('tier', 0) >= 2:
                    items_found.append((off, val, item['name'], item['tier']))

        if items_found:
            print(f"\n  {player['name']} ({player['hero']}):")
            # Group by tier
            for tier in [3, 2]:
                tier_items = [x for x in items_found if x[3] == tier]
                if tier_items:
                    print(f"    Tier {tier}:")
                    for off, vid, vname, _ in tier_items:
                        print(f"      +0x{off:03X}: {vname} (ID {vid})")

    # ===== SUMMARY =====
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print("\nKey findings will be printed above. Look for:")
    print("  - Consistent deltas between item IDs and entity IDs")
    print("  - [XX 04 YY] headers that consistently map items to players")
    print("  - Fixed offsets within player blocks that hold item IDs")
    print("  - Credit records that might encode item purchases")


if __name__ == '__main__':
    main()
