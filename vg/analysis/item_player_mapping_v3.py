#!/usr/bin/env python3
"""
Item-to-Player Mapping Research v3
===================================
Deep-dive into the [10 04 3D] structure and purchase cost records.

From v2 we know:
- [10 04 3D] [00 00] [eid BE] [00 00] [val LE 2B] [00 00] [counter?]... appears for items
  But the val at offset+10 contains item IDs that are mostly crystal-only (201-229)
  The val at offset+9 seems to contain different item IDs

This script:
1. Fully decodes the [10 04 3D] event structure
2. Analyzes the purchase cost [10 04 1D] action=0x06 + [10 04 3D] adjacency more carefully
3. Looks for weapon/defense/utility item IDs in the full event chain
4. Builds complete per-player inventories

Usage:
    python -m vg.analysis.item_player_mapping_v3
"""

import sys
import struct
import json
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Set, Tuple, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from vg.core.vgr_mapping import ITEM_ID_MAP, BINARY_HERO_ID_MAP

PLAYER_BLOCK_MARKER = bytes([0xDA, 0x03, 0xEE])
PLAYER_BLOCK_MARKER_ALT = bytes([0xE0, 0x03, 0xEE])
ENTITY_ID_OFFSET = 0xA5
HERO_ID_OFFSET = 0x0A9
TEAM_OFFSET = 0xD5

# Item price data for validation
ITEM_PRICES = {
    # T1 items
    101: 300, 102: 300, 103: 300, 104: 300,  # Weapon T1
    201: 300, 202: 300, 203: 300,              # Crystal T1
    301: 300, 302: 300, 303: 300,              # Defense T1
    401: 300,                                   # Boots T1
    411: 25, 412: 50,                           # Vision T1
    # T2 items (upgrade cost)
    111: 550, 112: 650, 113: 450, 114: 550, 115: 550, 116: 550,  # Weapon T2
    211: 550, 212: 650, 213: 550, 214: 750, 215: 600,            # Crystal T2
    311: 550, 312: 550, 313: 550, 314: 700,                      # Defense T2
    402: 500, 413: 300,                                            # Utility T2
    # T3 items (upgrade cost from T2)
    121: 900, 122: 900, 123: 700, 124: 700, 125: 800, 126: 650, 127: 800, 128: 700, 129: 700,
    221: 1200, 222: 700, 223: 700, 224: 750, 225: 800, 226: 700, 227: 700, 228: 700, 229: 700,
    321: 900, 322: 900, 323: 650, 324: 700, 325: 900, 326: 700, 327: 700, 328: 700,
    403: 600, 404: 700, 405: 700, 406: 600, 414: 600, 415: 600,
    421: 700, 422: 1200, 423: 700,
}


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


def decode_purchase_sequence(data: bytes, eid_map: Dict[int, str]) -> List[Dict]:
    """
    Scan for the purchase event SEQUENCE:
    [10 04 1D] [00 00] [eid BE] [gold_cost f32 BE] [06]  -- gold deduction
    ... possibly more [10 04 1D] records ...
    [10 04 3D] [00 00] [eid BE] [00 00] [item_id_or_slot LE 2B] ...  -- item added

    We scan for [10 04 1D] with action=0x06 (negative gold = purchase),
    then look ahead for the closest [10 04 3D] for the same player.
    """
    credit_header = bytes([0x10, 0x04, 0x1D])
    item_header = bytes([0x10, 0x04, 0x3D])

    purchases = []
    pos = 0
    while True:
        pos = data.find(credit_header, pos)
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

        if value >= 0 or action != 0x06:
            pos += 3
            continue

        gold_cost = abs(value)

        # Look for [10 04 3D] within next 50 bytes for same eid
        item_found = None
        for look in range(12, 50):
            check_pos = pos + look
            if check_pos + 14 > len(data):
                break
            if data[check_pos:check_pos+3] == item_header:
                if data[check_pos+3:check_pos+5] == b'\x00\x00':
                    item_eid = struct.unpack_from(">H", data, check_pos + 5)[0]
                    if item_eid == eid:
                        # Decode the [10 04 3D] payload
                        # Bytes structure: [10 04 3D] [00 00] [eid BE] [B7 B8] [item_le 2B] [B11 B12] ...
                        byte7 = data[check_pos+7] if check_pos+8 <= len(data) else 0
                        byte8 = data[check_pos+8] if check_pos+9 <= len(data) else 0
                        val_9_le = struct.unpack_from("<H", data, check_pos + 9)[0] if check_pos+11 <= len(data) else 0
                        val_10_le = struct.unpack_from("<H", data, check_pos + 10)[0] if check_pos+12 <= len(data) else 0

                        # The counter field at bytes 12-13 looks like a shop order counter (big endian)
                        counter = struct.unpack_from(">H", data, check_pos + 12)[0] if check_pos+14 <= len(data) else 0
                        # And there's a float after that
                        ts = struct.unpack_from(">f", data, check_pos + 14)[0] if check_pos+18 <= len(data) else 0

                        context = data[check_pos:min(check_pos+20, len(data))].hex()

                        item_found = {
                            'item_header_offset': check_pos,
                            'distance': look,
                            'byte7': byte7,
                            'byte8': byte8,
                            'val_9_le': val_9_le,
                            'val_10_le': val_10_le,
                            'item_at_9': ITEM_ID_MAP.get(val_9_le, {}).get('name'),
                            'item_at_10': ITEM_ID_MAP.get(val_10_le, {}).get('name'),
                            'counter': counter,
                            'timestamp': round(ts, 1) if 0 < ts < 2000 else None,
                            'context': context,
                        }
                        break

        purchases.append({
            'offset': pos,
            'eid': eid,
            'player': eid_map[eid],
            'gold_cost': round(gold_cost, 1),
            'item_info': item_found,
        })

        pos += 3

    return purchases


def scan_10_04_3D_full_structure(data: bytes, eid_map: Dict[int, str]) -> List[Dict]:
    """
    Fully decode [10 04 3D] events with all bytes analyzed.
    Structure hypothesis:
    [10 04 3D] [00 00] [eid BE 2B] [00 00] [val LE 2B at +9] [00 00] [counter BE 2B] [ts f32 BE]

    val at +9 seems to be uint16 LE. Let's check if it's an item ID or something else.
    Also decode bytes 7-8 which might be flags/slot info.
    """
    header = bytes([0x10, 0x04, 0x3D])
    results = []
    pos = 0
    while True:
        pos = data.find(header, pos)
        if pos == -1:
            break
        if pos + 18 > len(data):
            pos += 1
            continue
        if data[pos+3:pos+5] != b'\x00\x00':
            pos += 1
            continue

        eid = struct.unpack_from(">H", data, pos + 5)[0]
        if eid not in eid_map:
            pos += 1
            continue

        # Full decode
        b7 = data[pos+7]
        b8 = data[pos+8]
        val_9_10 = struct.unpack_from("<H", data, pos + 9)[0]  # LE
        b11 = data[pos+11]
        b12 = data[pos+12]
        counter = struct.unpack_from(">H", data, pos + 13)[0]
        ts_bytes = data[pos+15:pos+19]
        ts = struct.unpack_from(">f", data, pos + 15)[0] if pos + 19 <= len(data) else 0

        item_info = ITEM_ID_MAP.get(val_9_10)
        context = data[pos:pos+20].hex()

        results.append({
            'offset': pos,
            'eid': eid,
            'player': eid_map[eid],
            'b7_b8': f'{b7:02x} {b8:02x}',
            'val_9_10': val_9_10,
            'item_name': item_info['name'] if item_info else None,
            'item_tier': item_info.get('tier', 0) if item_info else 0,
            'b11_b12': f'{b11:02x} {b12:02x}',
            'counter': counter,
            'timestamp': round(ts, 1) if 0 < ts < 2000 else None,
            'context': context,
        })

        pos += 3

    return results


def scan_10_04_4B_full(data: bytes, eid_map: Dict[int, str]) -> List[Dict]:
    """
    Fully decode [10 04 4B] events.
    From v2: offset+10 consistently has item IDs (T2/T3 crystal items).
    """
    header = bytes([0x10, 0x04, 0x4B])
    results = []
    pos = 0
    while True:
        pos = data.find(header, pos)
        if pos == -1:
            break
        if pos + 18 > len(data):
            pos += 1
            continue
        if data[pos+3:pos+5] != b'\x00\x00':
            pos += 1
            continue

        eid = struct.unpack_from(">H", data, pos + 5)[0]
        if eid not in eid_map:
            pos += 1
            continue

        b7 = data[pos+7]
        b8 = data[pos+8]
        b9 = data[pos+9]
        val_10_11 = struct.unpack_from("<H", data, pos + 10)[0]
        b12 = data[pos+12]
        b13 = data[pos+13]
        b14 = data[pos+14]

        item_info = ITEM_ID_MAP.get(val_10_11)
        context = data[pos:pos+18].hex()

        results.append({
            'offset': pos,
            'eid': eid,
            'player': eid_map[eid],
            'b7': f'{b7:02x}',
            'b8': f'{b8:02x}',
            'b9': f'{b9:02x}',
            'val_10': val_10_11,
            'item_name': item_info['name'] if item_info else None,
            'b12_b13_b14': f'{b12:02x} {b13:02x} {b14:02x}',
            'context': context,
        })
        pos += 3

    return results


def build_purchase_timeline(purchases: List[Dict]) -> Dict[str, List]:
    """Build a timeline of item purchases per player."""
    timelines = defaultdict(list)

    for p in purchases:
        if p['item_info']:
            item_name = p['item_info']['item_at_10'] or p['item_info']['item_at_9']
            item_id = p['item_info']['val_10_le'] if p['item_info']['item_at_10'] else p['item_info']['val_9_le']
            ts = p['item_info'].get('timestamp')
        else:
            item_name = None
            item_id = None
            ts = None

        timelines[p['player']].append({
            'gold_cost': p['gold_cost'],
            'item_name': item_name,
            'item_id': item_id,
            'timestamp': ts,
        })

    return dict(timelines)


def check_gold_cost_vs_item_price(purchases: List[Dict]) -> List[Dict]:
    """Check if gold cost matches known item prices."""
    validated = []
    for p in purchases:
        if not p['item_info']:
            continue
        item_id = None
        item_name = None
        if p['item_info']['item_at_10']:
            item_id = p['item_info']['val_10_le']
            item_name = p['item_info']['item_at_10']
        elif p['item_info']['item_at_9']:
            item_id = p['item_info']['val_9_le']
            item_name = p['item_info']['item_at_9']

        if item_id and item_id in ITEM_PRICES:
            expected_price = ITEM_PRICES[item_id]
            actual_cost = p['gold_cost']
            match = abs(actual_cost - expected_price) < 50
            validated.append({
                'player': p['player'],
                'item': item_name,
                'item_id': item_id,
                'expected_price': expected_price,
                'actual_cost': actual_cost,
                'match': match,
            })
    return validated


def main():
    print("=" * 80)
    print("ITEM-TO-PLAYER MAPPING RESEARCH v3 - Deep Structure Analysis")
    print("=" * 80)

    truth = load_truth()

    for match_idx in range(min(3, len(truth['matches']))):
        match = truth['matches'][match_idx]
        replay_file = match['replay_file']
        print(f"\n{'#' * 80}")
        print(f"MATCH {match_idx + 1}")
        print(f"{'#' * 80}")

        frames = load_frames(replay_file)
        if not frames:
            print("  ERROR: No frames!")
            continue

        frame0_data = frames[0][1]
        players = extract_players(frame0_data)
        eid_map = {p['entity_id_be']: p['name'] for p in players}

        print(f"  {len(players)} players, {len(frames)} frames")
        for p in players:
            print(f"    {p['name']:<20} {p['hero']:<15} eid=0x{p['entity_id_be']:04X} {p['team']}")

        all_data = b"".join(d for _, d in frames)

        # ===== A: Full [10 04 3D] structure decode =====
        print(f"\n  --- [10 04 3D] Full Structure Decode ---")
        events_3D = scan_10_04_3D_full_structure(all_data, eid_map)
        print(f"  Found {len(events_3D)} events")

        # Analyze byte 7-8 patterns (could be slot/action)
        b7_b8_counts = Counter(e['b7_b8'] for e in events_3D)
        print(f"  Byte 7-8 patterns: {dict(b7_b8_counts.most_common(10))}")

        # Analyze b11_b12 patterns
        b11_b12_counts = Counter(e['b11_b12'] for e in events_3D)
        print(f"  Byte 11-12 patterns: {dict(b11_b12_counts.most_common(10))}")

        # Show all items found grouped by player
        by_player = defaultdict(list)
        for e in events_3D:
            by_player[e['player']].append(e)

        for pname in sorted(by_player.keys()):
            evs = by_player[pname]
            items = [(e['val_9_10'], e['item_name'], e['timestamp']) for e in evs if e['item_name']]
            print(f"\n    {pname}:")
            for val, name, ts in items:
                ts_str = f" @ {ts:.0f}s" if ts else ""
                print(f"      {name:<25} (ID {val}){ts_str}")
            # Show non-item values
            non_items = [(e['val_9_10'], e['b7_b8'], e['context']) for e in evs if not e['item_name']]
            if non_items:
                for val, bb, ctx in non_items[:3]:
                    print(f"      raw val={val} ({hex(val)}) bytes7_8={bb} ctx={ctx[:40]}")

        # ===== B: Purchase cost + item adjacency =====
        print(f"\n  --- Purchase Cost Records with Adjacent [10 04 3D] ---")
        purchases = decode_purchase_sequence(all_data, eid_map)
        with_items = [p for p in purchases if p['item_info']]
        print(f"  Total purchases: {len(purchases)}, with adjacent items: {len(with_items)}")

        # Validate gold costs
        validations = check_gold_cost_vs_item_price(purchases)
        if validations:
            matches = sum(1 for v in validations if v['match'])
            total = len(validations)
            print(f"  Gold cost validation: {matches}/{total} match known prices")
            for v in validations[:15]:
                status = "OK" if v['match'] else "MISMATCH"
                print(f"    {v['player']:<20} {v['item']:<25} cost={v['actual_cost']:.0f} "
                      f"expected={v['expected_price']} [{status}]")

        # Build purchase timeline
        timeline = build_purchase_timeline(purchases)
        print(f"\n  --- Purchase Timeline per Player ---")
        for pname in sorted(timeline.keys()):
            events = timeline[pname]
            total_gold = sum(e['gold_cost'] for e in events)
            named_items = [e for e in events if e['item_name']]
            unnamed = len(events) - len(named_items)

            # Find truth gold
            truth_gold = None
            for tname, tdata in match['players'].items():
                if pname in tname or tname.split('_', 1)[-1] in pname:
                    truth_gold = tdata.get('gold')
                    break

            gold_str = f" (truth gold: {truth_gold})" if truth_gold else ""
            print(f"\n    {pname}: spent {total_gold:.0f}g on {len(events)} purchases{gold_str}")
            for e in named_items:
                ts_str = f" @ {e['timestamp']:.0f}s" if e.get('timestamp') else ""
                print(f"      {e['item_name']:<25} cost={e['gold_cost']:.0f}g{ts_str}")
            if unnamed:
                unnamed_costs = [e['gold_cost'] for e in events if not e['item_name']]
                print(f"      + {unnamed} unnamed purchases ({', '.join(f'{c:.0f}g' for c in unnamed_costs[:10])})")

        # ===== C: [10 04 4B] full decode =====
        print(f"\n  --- [10 04 4B] Full Structure Decode ---")
        events_4B = scan_10_04_4B_full(all_data, eid_map)
        print(f"  Found {len(events_4B)} events")

        # Analyze byte patterns
        b7_counts = Counter(e['b7'] for e in events_4B)
        b8_counts = Counter(e['b8'] for e in events_4B)
        b9_counts = Counter(e['b9'] for e in events_4B)
        print(f"  b7: {dict(b7_counts.most_common(5))}")
        print(f"  b8: {dict(b8_counts.most_common(5))}")
        print(f"  b9: {dict(b9_counts.most_common(5))}")

        # Show items per player with byte context
        by_player_4B = defaultdict(list)
        for e in events_4B:
            if e['item_name']:
                by_player_4B[e['player']].append(e)

        for pname in sorted(by_player_4B.keys()):
            evs = by_player_4B[pname]
            hero = next((p['hero'] for p in players if p['name'] == pname), "?")
            print(f"\n    {pname} ({hero}):")
            for e in evs:
                print(f"      {e['item_name']:<25} b7={e['b7']} b8={e['b8']} "
                      f"b9={e['b9']} b12-14={e['b12_b13_b14']}")

    print(f"\n\n{'=' * 80}")
    print("CONCLUSIONS")
    print("=" * 80)
    print("""
Key structure findings:

[10 04 1D] [00 00] [eid BE] [gold f32 BE] [action byte]
  action=0x06: Item purchase (gold is negative = cost)
  This tells us WHO spent gold and HOW MUCH

[10 04 3D] [00 00] [eid BE] [00 00] [item_id LE 2B] [00 00] [counter BE] [ts f32 BE]
  Item acquire event. The item_id at offset+9 (LE) is the item acquired.
  This tells us WHO got WHAT item and WHEN

[10 04 4B] [00 00] [eid BE] [00 00] [?? 1B] [item_id LE 2B] [00 01 00]
  Possible inventory/slot update. Shows item currently in a slot.

The purchase pattern is:
  1. [10 04 1D] gold deduction (action=0x06)
  2. [10 04 3D] item added to inventory

By pairing these, we get per-player item purchases with timestamps and costs.
""")


if __name__ == '__main__':
    main()
