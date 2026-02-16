#!/usr/bin/env python3
"""
Item-to-Player Mapping Research v2
===================================
Focused investigation of the most promising patterns from v1:

Key findings from v1:
- Player blocks DO NOT contain dedicated item slots (values are sequential/shifted)
- [10 04 3D] at offset+10 shows item IDs with eid at offset+5 (purchase events?)
- [10 04 3C] at offset+10/20 shows item IDs
- [10 04 4B] at offset+10 shows item IDs
- Credit records [10 04 1D] with negative gold values (action=0x6) show item COSTS
  e.g. value=-600.0, action=0x6 => purchase for 600 gold
- [10 04 2B] at offset+20 has high volume (4566 hits) with 10 unique players

This script:
1. Examines [10 04 3D] as potential item buy/sell events
2. Examines credit records with negative values as purchase cost records
3. Tries to build per-player item inventories from detected events
4. Cross-validates against truth data (if available from result screenshots)

Usage:
    python -m vg.analysis.item_player_mapping_v2
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
ENTITY_ID_OFFSET = 0xA5
HERO_ID_OFFSET = 0x0A9
TEAM_OFFSET = 0xD5

# All item IDs by tier
T3_ITEMS = {k: v for k, v in ITEM_ID_MAP.items() if v.get('tier', 0) == 3}
T2_ITEMS = {k: v for k, v in ITEM_ID_MAP.items() if v.get('tier', 0) == 2}
T1_ITEMS = {k: v for k, v in ITEM_ID_MAP.items() if v.get('tier', 0) == 1}


def load_truth():
    truth_path = Path(__file__).parent.parent / "output" / "tournament_truth.json"
    with open(truth_path, 'r') as f:
        return json.load(f)


def load_frames(replay_file: str) -> List[Tuple[int, bytes]]:
    replay_path = Path(replay_file)
    frame_dir = replay_path.parent
    replay_name = replay_path.stem.rsplit('.', 1)[0]
    frames = list(frame_dir.glob(f"{replay_name}.*.vgr"))
    def frame_index(p):
        try: return int(p.stem.split('.')[-1])
        except: return 0
    frames.sort(key=frame_index)
    return [(frame_index(fp), fp.read_bytes()) for fp in frames]


def extract_players(data: bytes) -> List[Dict]:
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
            try: name = data[name_start:name_end].decode('ascii')
            except: pass
        if len(name) >= 3 and not name.startswith('GameMode') and name not in seen:
            seen.add(name)
            eid_le = eid_be = None
            if pos + ENTITY_ID_OFFSET + 2 <= len(data):
                eid_le = int.from_bytes(data[pos + ENTITY_ID_OFFSET:pos + ENTITY_ID_OFFSET + 2], 'little')
                eid_be = struct.unpack_from(">H", data, pos + ENTITY_ID_OFFSET)[0]
            team_id = data[pos + TEAM_OFFSET] if pos + TEAM_OFFSET < len(data) else None
            team = {1: "left", 2: "right"}.get(team_id, "unknown")
            hero_name = "Unknown"
            if pos + HERO_ID_OFFSET + 2 <= len(data):
                bhid = int.from_bytes(data[pos + HERO_ID_OFFSET:pos + HERO_ID_OFFSET + 2], 'little')
                hero_name = BINARY_HERO_ID_MAP.get(bhid, "Unknown")
            players.append({
                'name': name, 'entity_id_le': eid_le, 'entity_id_be': eid_be,
                'team': team, 'hero': hero_name, 'block_offset': pos,
            })
        search_start = pos + 1
    return players


def scan_10_04_3D_events(data: bytes, eid_map: Dict[int, str]) -> List[Dict]:
    """
    Scan for [10 04 3D] events.
    Structure observed: [10 04 3D] [00 00] [eid BE 2B] [00 00] [item_id LE 2B] [00 00 07]
    This looks like an item acquire/purchase event.
    """
    header = bytes([0x10, 0x04, 0x3D])
    results = []
    pos = 0
    while True:
        pos = data.find(header, pos)
        if pos == -1:
            break
        if pos + 14 > len(data):
            pos += 1
            continue

        # Check [00 00] after header
        if data[pos+3:pos+5] != b'\x00\x00':
            pos += 1
            continue

        eid = struct.unpack_from(">H", data, pos + 5)[0]
        if eid not in eid_map:
            pos += 1
            continue

        # Bytes 7-8: should be [00 00]
        # Bytes 9-10: potential item ID (LE)
        padding = data[pos+7:pos+9]
        val_at_9 = struct.unpack_from("<H", data, pos + 9)[0]

        # Also try offset 10
        val_at_10 = struct.unpack_from("<H", data, pos + 10)[0] if pos + 12 <= len(data) else 0

        # Check which one could be an item
        item_at_9 = ITEM_ID_MAP.get(val_at_9)
        item_at_10 = ITEM_ID_MAP.get(val_at_10)

        context = data[pos:min(pos+20, len(data))].hex()

        if item_at_9 or item_at_10:
            results.append({
                'offset': pos,
                'eid': eid,
                'player': eid_map[eid],
                'val_at_9': val_at_9,
                'item_at_9': item_at_9['name'] if item_at_9 else None,
                'val_at_10': val_at_10,
                'item_at_10': item_at_10['name'] if item_at_10 else None,
                'padding_7_8': padding.hex(),
                'context': context,
            })

        pos += 3
    return results


def scan_purchase_cost_records(data: bytes, eid_map: Dict[int, str]) -> List[Dict]:
    """
    Scan credit records [10 04 1D] with negative gold values (action=0x6).
    These appear to be item purchase cost records.
    Structure: [10 04 1D] [00 00] [eid BE] [gold f32 BE] [action=06]
    Followed potentially by item info.
    """
    header = bytes([0x10, 0x04, 0x1D])
    results = []
    pos = 0
    while True:
        pos = data.find(header, pos)
        if pos == -1:
            break
        if pos + 12 > len(data):
            pos += 1
            continue
        if data[pos+3:pos+5] != b'\x00\x00':
            pos += 1
            continue

        eid = struct.unpack_from(">H", data, pos + 5)[0]
        if eid not in eid_map:
            pos += 1
            continue

        value = struct.unpack_from(">f", data, pos + 7)[0]
        action = data[pos + 11]

        # Only interested in negative values (purchases) with action 0x06
        if value < 0 and action == 0x06:
            # Look for item-related records nearby
            # Check for [10 04 3D] within next ~30 bytes
            nearby_item = None
            for look_ahead in range(12, 40):
                if pos + look_ahead + 3 <= len(data):
                    if data[pos+look_ahead:pos+look_ahead+3] == bytes([0x10, 0x04, 0x3D]):
                        if pos + look_ahead + 12 <= len(data):
                            nearby_eid = struct.unpack_from(">H", data, pos + look_ahead + 5)[0]
                            if nearby_eid in eid_map:
                                # Check for item at offset+10 from the [10 04 3D]
                                item_val = struct.unpack_from("<H", data, pos + look_ahead + 10)[0]
                                if item_val in ITEM_ID_MAP:
                                    nearby_item = {
                                        'item_id': item_val,
                                        'item_name': ITEM_ID_MAP[item_val]['name'],
                                        'item_player': eid_map.get(nearby_eid, f'eid_{nearby_eid}'),
                                        'distance': look_ahead,
                                    }
                        break

            context = data[pos:min(pos+40, len(data))].hex()
            results.append({
                'offset': pos,
                'eid': eid,
                'player': eid_map[eid],
                'gold_cost': round(value, 1),
                'action': hex(action),
                'nearby_item': nearby_item,
                'context': context,
            })

        pos += 3
    return results


def scan_10_04_4B_events(data: bytes, eid_map: Dict[int, str]) -> List[Dict]:
    """
    Scan for [10 04 4B] events - potential item slot/inventory events.
    Structure: [10 04 4B] [00 00] [eid BE 2B] [00 00] [item_id LE 2B at +10] [00 01 00]
    """
    header = bytes([0x10, 0x04, 0x4B])
    results = []
    pos = 0
    while True:
        pos = data.find(header, pos)
        if pos == -1:
            break
        if pos + 14 > len(data):
            pos += 1
            continue
        if data[pos+3:pos+5] != b'\x00\x00':
            pos += 1
            continue

        eid = struct.unpack_from(">H", data, pos + 5)[0]
        if eid not in eid_map:
            pos += 1
            continue

        # Item at offset +10
        item_val = struct.unpack_from("<H", data, pos + 10)[0] if pos + 12 <= len(data) else 0
        item_info = ITEM_ID_MAP.get(item_val)

        context = data[pos:min(pos+18, len(data))].hex()

        results.append({
            'offset': pos,
            'eid': eid,
            'player': eid_map[eid],
            'item_val': item_val,
            'item_name': item_info['name'] if item_info else f'raw_{item_val}',
            'is_known_item': item_info is not None,
            'context': context,
        })

        pos += 3
    return results


def scan_10_04_3C_events(data: bytes, eid_map: Dict[int, str]) -> List[Dict]:
    """
    Scan for [10 04 3C] events - also looks like item-related.
    Offset+10 has item IDs for T2+ items.
    """
    header = bytes([0x10, 0x04, 0x3C])
    results = []
    pos = 0
    while True:
        pos = data.find(header, pos)
        if pos == -1:
            break
        if pos + 14 > len(data):
            pos += 1
            continue
        if data[pos+3:pos+5] != b'\x00\x00':
            pos += 1
            continue

        eid = struct.unpack_from(">H", data, pos + 5)[0]
        if eid not in eid_map:
            pos += 1
            continue

        # Try items at offset +10 (LE)
        item_val_10 = struct.unpack_from("<H", data, pos + 10)[0] if pos + 12 <= len(data) else 0
        item_info_10 = ITEM_ID_MAP.get(item_val_10)

        # Also try reading at +7 as uint32 to understand the structure
        val_7_10 = data[pos+7:pos+11].hex() if pos + 11 <= len(data) else "?"

        context = data[pos:min(pos+20, len(data))].hex()

        results.append({
            'offset': pos,
            'eid': eid,
            'player': eid_map[eid],
            'bytes_7_10': val_7_10,
            'item_val_10': item_val_10,
            'item_name_10': item_info_10['name'] if item_info_10 else f'raw_{item_val_10}',
            'is_known_item': item_info_10 is not None,
            'context': context,
        })

        pos += 3
    return results


def build_player_inventories(purchase_events: List[Dict], cost_events: List[Dict]) -> Dict[str, List]:
    """
    Try to build per-player item inventories from purchase and cost events.
    """
    inventories = defaultdict(list)

    # From [10 04 3D] events
    for ev in purchase_events:
        item_name = ev.get('item_at_10') or ev.get('item_at_9')
        item_id = ev.get('val_at_10') if ev.get('item_at_10') else ev.get('val_at_9')
        if item_name and item_id:
            tier = ITEM_ID_MAP.get(item_id, {}).get('tier', 0)
            inventories[ev['player']].append({
                'item_id': item_id,
                'item_name': item_name,
                'tier': tier,
                'source': '10_04_3D',
                'offset': ev['offset'],
            })

    # From cost events with nearby items
    for ev in cost_events:
        if ev.get('nearby_item'):
            ni = ev['nearby_item']
            tier = ITEM_ID_MAP.get(ni['item_id'], {}).get('tier', 0)
            inventories[ev['player']].append({
                'item_id': ni['item_id'],
                'item_name': ni['item_name'],
                'tier': tier,
                'source': 'cost_record',
                'gold_cost': ev['gold_cost'],
                'offset': ev['offset'],
            })

    return dict(inventories)


def main():
    print("=" * 80)
    print("ITEM-TO-PLAYER MAPPING RESEARCH v2")
    print("=" * 80)

    truth = load_truth()

    # Process first 3 matches for cross-validation
    for match_idx in range(min(3, len(truth['matches']))):
        match = truth['matches'][match_idx]
        replay_file = match['replay_file']
        print(f"\n{'#' * 80}")
        print(f"MATCH {match_idx + 1}: {match['replay_name'][:50]}...")
        print(f"{'#' * 80}")

        # Load frames
        frames = load_frames(replay_file)
        if not frames:
            print("  ERROR: No frames found!")
            continue
        print(f"  Loaded {len(frames)} frames")

        # Extract players
        frame0_data = frames[0][1]
        players = extract_players(frame0_data)
        eid_map = {p['entity_id_be']: p['name'] for p in players}
        eid_set = set(eid_map.keys())

        print(f"  Found {len(players)} players:")
        for p in players:
            truth_player = None
            for tname, tdata in match['players'].items():
                if p['name'] in tname or tname.split('_', 1)[-1] in p['name']:
                    truth_player = tdata
                    break
            gold_str = f" gold={truth_player['gold']}" if truth_player else ""
            print(f"    {p['name']:<20} {p['hero']:<15} eid=0x{p['entity_id_be']:04X} {p['team']}{gold_str}")

        # Concatenate all frame data
        all_data = b"".join(d for _, d in frames)
        print(f"  Total data: {len(all_data):,} bytes")

        # ===== ANALYSIS A: [10 04 3D] item acquire events =====
        print(f"\n  --- [10 04 3D] Item Acquire Events ---")
        events_3D = scan_10_04_3D_events(all_data, eid_map)
        print(f"  Found {len(events_3D)} events")

        if events_3D:
            # Group by player
            by_player = defaultdict(list)
            for ev in events_3D:
                by_player[ev['player']].append(ev)

            for pname in sorted(by_player.keys()):
                evs = by_player[pname]
                items_at_10 = [e for e in evs if e['item_at_10']]
                items_at_9 = [e for e in evs if e['item_at_9'] and not e['item_at_10']]
                print(f"\n    {pname}: {len(evs)} events")
                # Show unique items at offset+10
                unique_items_10 = Counter(e['item_at_10'] for e in items_at_10 if e['item_at_10'])
                if unique_items_10:
                    print(f"      Items at +10: {dict(unique_items_10.most_common(15))}")
                # Show structure of first few
                for e in evs[:3]:
                    print(f"      ctx={e['context']}  item@9={e['item_at_9']} item@10={e['item_at_10']}")

        # ===== ANALYSIS B: Purchase cost records =====
        print(f"\n  --- Purchase Cost Records (credit -gold, action=0x06) ---")
        cost_events = scan_purchase_cost_records(all_data, eid_map)
        print(f"  Found {len(cost_events)} purchase cost records")

        if cost_events:
            by_player = defaultdict(list)
            for ev in cost_events:
                by_player[ev['player']].append(ev)

            for pname in sorted(by_player.keys()):
                evs = by_player[pname]
                total_gold = sum(e['gold_cost'] for e in evs)
                with_items = [e for e in evs if e['nearby_item']]
                print(f"\n    {pname}: {len(evs)} purchases, total gold spent: {abs(total_gold):.0f}")
                if with_items:
                    print(f"      {len(with_items)} purchases have nearby item IDs:")
                    for e in with_items[:10]:
                        ni = e['nearby_item']
                        print(f"        {ni['item_name']:<25} cost={abs(e['gold_cost']):.0f}g "
                              f"(dist={ni['distance']})")

        # ===== ANALYSIS C: [10 04 4B] inventory events =====
        print(f"\n  --- [10 04 4B] Inventory Events ---")
        events_4B = scan_10_04_4B_events(all_data, eid_map)
        known_items_4B = [e for e in events_4B if e['is_known_item']]
        print(f"  Found {len(events_4B)} events, {len(known_items_4B)} with known items")

        if known_items_4B:
            by_player = defaultdict(list)
            for ev in known_items_4B:
                by_player[ev['player']].append(ev)

            for pname in sorted(by_player.keys()):
                evs = by_player[pname]
                unique = Counter(e['item_name'] for e in evs)
                print(f"    {pname}: {dict(unique.most_common(10))}")

        # ===== ANALYSIS D: [10 04 3C] events =====
        print(f"\n  --- [10 04 3C] Events ---")
        events_3C = scan_10_04_3C_events(all_data, eid_map)
        known_items_3C = [e for e in events_3C if e['is_known_item']]
        print(f"  Found {len(events_3C)} events, {len(known_items_3C)} with known items")

        if known_items_3C:
            by_player = defaultdict(list)
            for ev in known_items_3C:
                by_player[ev['player']].append(ev)

            for pname in sorted(by_player.keys()):
                evs = by_player[pname]
                unique = Counter(e['item_name_10'] for e in evs)
                print(f"    {pname}: {dict(unique.most_common(10))}")

        # ===== Build and display inventory =====
        print(f"\n  --- Reconstructed Per-Player Inventories ---")
        inventories = build_player_inventories(events_3D, cost_events)
        for pname in sorted(inventories.keys()):
            items = inventories[pname]
            # Deduplicate by item_id, keep first occurrence
            seen = set()
            unique_items = []
            for it in items:
                if it['item_id'] not in seen:
                    seen.add(it['item_id'])
                    unique_items.append(it)

            t3_items = [it for it in unique_items if it['tier'] == 3]
            t2_items = [it for it in unique_items if it['tier'] == 2]
            t1_items = [it for it in unique_items if it['tier'] == 1]

            hero = next((p['hero'] for p in players if p['name'] == pname), "?")
            print(f"\n    {pname} ({hero}):")
            if t3_items:
                print(f"      T3: {', '.join(it['item_name'] for it in t3_items)}")
            if t2_items:
                print(f"      T2: {', '.join(it['item_name'] for it in t2_items)}")
            if t1_items:
                print(f"      T1: {', '.join(it['item_name'] for it in t1_items)}")

    # ===== Cross-match validation: which event types are consistent? =====
    print(f"\n\n{'=' * 80}")
    print("CROSS-MATCH SUMMARY")
    print("=" * 80)
    print("\nThe [10 04 3D] header appears to be an item-related event.")
    print("The credit record [10 04 1D] with negative gold (action=0x06) shows item costs.")
    print("Look for patterns where the same item appears in both [10 04 3D] and cost records")
    print("for the same player.")


if __name__ == '__main__':
    main()
