#!/usr/bin/env python3
"""
Item-to-Player Mapping Research v4 - Final
=============================================
Correct structure from v3 analysis:

[10 04 3D] structure (item acquire):
  [10 04 3D] [00 00] [eid BE 2B] [00 00] [count 1B] [item_id LE 2B] [00 00] [shop_counter BE 2B] [ts f32 BE]
  Offset +7,+8: always 00 00
  Offset +9: quantity/count byte (01, 02, etc.)
  Offset +10,+11: item ID as uint16 LE  <-- THIS IS THE ITEM
  Offset +12,+13: always 00 00
  Offset +14,+15: shop order counter (BE)
  Offset +16..+19: game timestamp (f32 BE)

[10 04 1D] with action=0x06 (purchase cost):
  [10 04 1D] [00 00] [eid BE 2B] [gold_cost f32 BE] [06]
  gold_cost is negative (debit)

[10 04 4B] structure (item acquired/equipped notification):
  [10 04 4B] [00 00] [eid BE 2B] [00 00 07] [item_id LE 2B] [00 01 00]
  Only fires for T2+ items

Purchase sequence: [10 04 1D action=6] -> [10 04 3D item_id]
  Gold is debited first, then item is added to inventory.

This script extracts complete per-player item builds.

Usage:
    python -m vg.analysis.item_player_mapping_v4
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
            eid_be = None
            if pos + ENTITY_ID_OFFSET + 2 <= len(data):
                eid_be = struct.unpack_from(">H", data, pos + ENTITY_ID_OFFSET)[0]
            team_id = data[pos + TEAM_OFFSET] if pos + TEAM_OFFSET < len(data) else None
            team = {1: "left", 2: "right"}.get(team_id, "unknown")
            hero_name = "Unknown"
            if pos + HERO_ID_OFFSET + 2 <= len(data):
                bhid = int.from_bytes(data[pos + HERO_ID_OFFSET:pos + HERO_ID_OFFSET + 2], 'little')
                hero_name = BINARY_HERO_ID_MAP.get(bhid, "Unknown")
            players.append({
                'name': name, 'entity_id_be': eid_be,
                'team': team, 'hero': hero_name,
            })
        search_start = pos + 1
    return players


def scan_item_acquire_events(data: bytes, eid_map: Dict[int, str]) -> List[Dict]:
    """
    Scan for [10 04 3D] item acquire events.
    Structure: [10 04 3D] [00 00] [eid BE] [00 00] [qty 1B] [item_id LE 2B] [00 00] [counter BE 2B] [ts f32 BE]
    Item ID at offset +10 as uint16 LE.
    """
    header = bytes([0x10, 0x04, 0x3D])
    results = []
    pos = 0
    while True:
        pos = data.find(header, pos)
        if pos == -1:
            break
        if pos + 20 > len(data):
            pos += 1
            continue
        if data[pos+3:pos+5] != b'\x00\x00':
            pos += 1
            continue

        eid = struct.unpack_from(">H", data, pos + 5)[0]
        if eid not in eid_map:
            pos += 1
            continue

        qty = data[pos + 9]
        item_id = struct.unpack_from("<H", data, pos + 10)[0]
        counter = struct.unpack_from(">H", data, pos + 14)[0]
        ts = struct.unpack_from(">f", data, pos + 16)[0]

        item_info = ITEM_ID_MAP.get(item_id)
        item_name = item_info['name'] if item_info else f'unknown_{item_id}'
        item_tier = item_info.get('tier', 0) if item_info else 0
        item_cat = item_info.get('category', '?') if item_info else '?'

        valid_ts = 0 < ts < 2000

        results.append({
            'offset': pos,
            'eid': eid,
            'player': eid_map[eid],
            'qty': qty,
            'item_id': item_id,
            'item_name': item_name,
            'item_tier': item_tier,
            'item_category': item_cat,
            'counter': counter,
            'timestamp': round(ts, 1) if valid_ts else None,
        })

        pos += 3
    return results


def scan_item_equip_events(data: bytes, eid_map: Dict[int, str]) -> List[Dict]:
    """
    Scan for [10 04 4B] item equipped/slot events.
    Structure: [10 04 4B] [00 00] [eid BE] [00 00 07] [item_id LE 2B] [00 01 00]
    Only fires for T2+ items when they enter an item slot.
    """
    header = bytes([0x10, 0x04, 0x4B])
    results = []
    pos = 0
    while True:
        pos = data.find(header, pos)
        if pos == -1:
            break
        if pos + 15 > len(data):
            pos += 1
            continue
        if data[pos+3:pos+5] != b'\x00\x00':
            pos += 1
            continue

        eid = struct.unpack_from(">H", data, pos + 5)[0]
        if eid not in eid_map:
            pos += 1
            continue

        # Bytes 7,8,9 should be 00 00 07
        if data[pos+7:pos+10] != b'\x00\x00\x07':
            pos += 1
            continue

        item_id = struct.unpack_from("<H", data, pos + 10)[0]
        item_info = ITEM_ID_MAP.get(item_id)

        if item_info:
            results.append({
                'offset': pos,
                'eid': eid,
                'player': eid_map[eid],
                'item_id': item_id,
                'item_name': item_info['name'],
                'item_tier': item_info.get('tier', 0),
                'item_category': item_info.get('category', '?'),
            })

        pos += 3
    return results


def scan_purchase_costs(data: bytes, eid_map: Dict[int, str]) -> List[Dict]:
    """
    Scan for [10 04 1D] credit records with action=0x06 (purchase cost).
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

        if action == 0x06 and value < 0:
            results.append({
                'offset': pos,
                'eid': eid,
                'player': eid_map[eid],
                'gold_cost': round(abs(value), 1),
            })

        pos += 3
    return results


def build_final_inventories(acquire_events: List[Dict], equip_events: List[Dict]) -> Dict[str, Dict]:
    """
    Build final per-player inventories.
    Use acquire events as primary, equip events as secondary validation.
    Filter out T1 components that get upgraded to T2/T3.
    """
    player_items = defaultdict(list)

    # Sort acquire events by timestamp
    sorted_events = sorted(acquire_events, key=lambda e: e.get('timestamp') or 0)

    for ev in sorted_events:
        player_items[ev['player']].append({
            'item_id': ev['item_id'],
            'item_name': ev['item_name'],
            'tier': ev['item_tier'],
            'category': ev['item_category'],
            'qty': ev['qty'],
            'timestamp': ev.get('timestamp'),
            'counter': ev.get('counter'),
        })

    # Build equipped items from [10 04 4B]
    equipped = defaultdict(set)
    for ev in equip_events:
        equipped[ev['player']].add((ev['item_id'], ev['item_name']))

    result = {}
    for player, items in player_items.items():
        # Deduplicate: keep last occurrence of each item_id
        seen = {}
        for it in items:
            seen[it['item_id']] = it

        # Separate by tier
        all_items = list(seen.values())
        t3 = [it for it in all_items if it['tier'] == 3]
        t2 = [it for it in all_items if it['tier'] == 2]
        t1 = [it for it in all_items if it['tier'] == 1]

        equip_set = equipped.get(player, set())

        result[player] = {
            'acquire_t3': t3,
            'acquire_t2': t2,
            'acquire_t1': t1,
            'equipped_items': sorted(equip_set),
            'total_items_acquired': len(all_items),
        }

    return result


def main():
    print("=" * 80)
    print("ITEM-TO-PLAYER MAPPING v4 - Final Build Extraction")
    print("=" * 80)

    truth = load_truth()

    all_match_results = []

    for match_idx in range(len(truth['matches'])):
        match = truth['matches'][match_idx]
        replay_file = match['replay_file']
        print(f"\n{'=' * 80}")
        print(f"MATCH {match_idx + 1}: {Path(replay_file).parent.parent.name}/{Path(replay_file).parent.name}")
        print(f"{'=' * 80}")

        frames = load_frames(replay_file)
        if not frames:
            print("  ERROR: No frames!")
            continue

        frame0_data = frames[0][1]
        players = extract_players(frame0_data)
        eid_map = {p['entity_id_be']: p['name'] for p in players}

        all_data = b"".join(d for _, d in frames)

        # Scan all event types
        acquire_events = scan_item_acquire_events(all_data, eid_map)
        equip_events = scan_item_equip_events(all_data, eid_map)
        cost_events = scan_purchase_costs(all_data, eid_map)

        # Build inventories
        inventories = build_final_inventories(acquire_events, equip_events)

        # Calculate total gold spent per player
        gold_spent = defaultdict(float)
        for ev in cost_events:
            gold_spent[ev['player']] += ev['gold_cost']

        # Print results
        print(f"  {len(frames)} frames, {len(players)} players")
        print(f"  Events: {len(acquire_events)} acquires, {len(equip_events)} equips, {len(cost_events)} purchases")

        match_result = {'match': match_idx + 1, 'players': {}}

        for p in players:
            pname = p['name']
            inv = inventories.get(pname, {})
            t3 = inv.get('acquire_t3', [])
            t2 = inv.get('acquire_t2', [])
            t1 = inv.get('acquire_t1', [])
            equipped = inv.get('equipped_items', [])
            spent = gold_spent.get(pname, 0)

            # Find truth data
            truth_gold = None
            for tname, tdata in match['players'].items():
                if pname in tname or tname.split('_', 1)[-1] in pname:
                    truth_gold = tdata.get('gold')
                    break

            gold_str = f" truth={truth_gold}" if truth_gold else ""
            print(f"\n  {pname} ({p['hero']}, {p['team']}) - spent {spent:.0f}g{gold_str}")

            if t3:
                t3_names = [it['item_name'] for it in sorted(t3, key=lambda x: x.get('timestamp') or 0)]
                print(f"    T3 acquired: {', '.join(t3_names)}")
            if t2:
                t2_names = [it['item_name'] for it in sorted(t2, key=lambda x: x.get('timestamp') or 0)]
                print(f"    T2 acquired: {', '.join(t2_names)}")
            if equipped:
                equip_names = [name for _, name in equipped]
                print(f"    Equipped (4B): {', '.join(equip_names)}")

            # Show timeline for this player
            player_acquires = [e for e in acquire_events if e['player'] == pname]
            player_acquires.sort(key=lambda e: e.get('counter', 0))
            if player_acquires:
                print(f"    Purchase timeline ({len(player_acquires)} items):")
                for ev in player_acquires:
                    ts_str = f" @{ev['timestamp']:.0f}s" if ev.get('timestamp') else ""
                    print(f"      #{ev['counter']:>3d}: {ev['item_name']:<25} "
                          f"T{ev['item_tier']} x{ev['qty']}{ts_str}")

            match_result['players'][pname] = {
                'hero': p['hero'],
                'team': p['team'],
                'gold_spent': round(spent),
                't3_items': [it['item_name'] for it in t3],
                't2_items': [it['item_name'] for it in t2],
                't1_items': [it['item_name'] for it in t1],
                'equipped_items': [name for _, name in equipped],
            }

        all_match_results.append(match_result)

    # Save results
    output_path = Path(__file__).parent.parent / "output" / "item_player_mapping.json"
    with open(output_path, 'w') as f:
        json.dump(all_match_results, f, indent=2, ensure_ascii=False)
    print(f"\n\nResults saved to {output_path}")

    # Print summary
    print(f"\n{'=' * 80}")
    print("SUMMARY - Item-to-Player Mapping Findings")
    print(f"{'=' * 80}")
    print("""
DISCOVERED EVENT STRUCTURES:

1. Item Acquire Event: [10 04 3D]
   [10 04 3D] [00 00] [eid BE 2B] [00 00] [qty 1B] [item_id LE 2B] [00 00] [counter BE 2B] [ts f32 BE]
   - eid: Player entity ID (big endian)
   - qty: Quantity (usually 01; consumables may be higher)
   - item_id: Item ID at offset+10, uint16 little endian, matches ITEM_ID_MAP
   - counter: Sequential shop purchase counter (big endian)
   - ts: Game timestamp (f32 big endian)

2. Item Equipped Event: [10 04 4B]
   [10 04 4B] [00 00] [eid BE 2B] [00 00 07] [item_id LE 2B] [00 01 00]
   - Fires when a T2+ item enters an equipment slot
   - Only shows crystal-path items (T2 crystal components + T3 crystal items)

3. Purchase Cost Event: [10 04 1D] action=0x06
   [10 04 1D] [00 00] [eid BE 2B] [gold_cost f32 BE] [06]
   - gold_cost is NEGATIVE (debit from player's gold)
   - Fires immediately before the [10 04 3D] acquire event

PURCHASE SEQUENCE:
   [10 04 1D] gold deduction (action=0x06) -> [10 04 3D] item added

This maps items to specific players with timestamps and gold costs.
""")


if __name__ == '__main__':
    main()
