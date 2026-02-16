#!/usr/bin/env python3
"""
Item Upgrade Tree Analyzer - Trace purchase sequences to identify items.
=========================================================================

Strategy: Track per-player purchase sequences and identify T1 → T2 → T3
upgrade chains. The acquire events fire for EACH upgrade step, and the
cost represents the upgrade cost (not total item value).

Key VG upgrade costs (from T1 component):
  Weapon T2: Heavy Steel=850, Six Sins=350, Blazing Salvo=400,
             Lucky Strike=600, Piercing Spear=600, Barbed Needle=500
  Crystal T2: Eclipse Prism=350, Heavy Prism=550+300, Piercing Shard=600,
              Chronograph=550, Void Battery=400
  Defense T2: Kinetic Shield=500, Coat of Plates=500, Dragonheart=350,
              Reflex Block=400
  Boots T2: Travel Boots=200 (from Sprint Boots 300)

Usage:
    python -m vg.analysis.item_upgrade_tree
"""

import sys
import struct
import json
import math
from pathlib import Path
from collections import defaultdict, Counter

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from vg.core.vgr_mapping import ITEM_ID_MAP, BINARY_HERO_ID_MAP

PLAYER_BLOCK_MARKER = bytes([0xDA, 0x03, 0xEE])
PLAYER_BLOCK_MARKER_ALT = bytes([0xE0, 0x03, 0xEE])
ENTITY_ID_OFFSET = 0xA5
HERO_ID_OFFSET = 0xA9
TEAM_OFFSET = 0xD5
ITEM_ACQUIRE_HEADER = bytes([0x10, 0x04, 0x3D])
CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])

HERO_ROLES = {
    "Kinetic": "wp", "Gwen": "wp", "Caine": "wp", "Kestrel": "wp",
    "Ringo": "wp", "Silvernail": "wp", "Kensei": "wp", "Vox": "wp",
    "Baron": "wp", "SAW": "wp",
    "Samuel": "cp", "Skaarf": "cp", "Celeste": "cp", "Reza": "cp",
    "Magnus": "cp", "Malene": "cp", "Varya": "cp", "Warhawk": "cp",
    "Skye": "cp", "Ishtar": "cp", "Anka": "cp",
    "Blackfeather": "br", "Ylva": "br", "Inara": "br", "Ozo": "br",
    "Tony": "br", "Reim": "br", "San Feng": "br",
    "Lorelai": "cap", "Lyra": "cap", "Ardan": "cap", "Phinn": "cap",
    "Baptiste": "cap", "Catherine": "cap", "Grumpjaw": "cap",
    "Fortress": "cap", "Lance": "cap", "Churnwalker": "cap",
    "Flicker": "cap", "Grace": "cap", "Adagio": "cap", "Yates": "cap",
}


def load_truth():
    truth_path = Path(__file__).parent.parent / "output" / "tournament_truth.json"
    with open(truth_path, 'r') as f:
        return json.load(f)


def load_frames(replay_file):
    replay_path = Path(replay_file)
    frame_dir = replay_path.parent
    replay_name = replay_path.stem.rsplit('.', 1)[0]
    frames = list(frame_dir.glob(f"{replay_name}.*.vgr"))
    def fi(p):
        try: return int(p.stem.split('.')[-1])
        except: return 0
    frames.sort(key=fi)
    return [(fi(fp), fp.read_bytes()) for fp in frames]


def extract_players(data):
    players = []
    seen = set()
    search_start = 0
    markers = (PLAYER_BLOCK_MARKER, PLAYER_BLOCK_MARKER_ALT)
    while True:
        pos = -1
        marker = None
        for c in markers:
            idx = data.find(c, search_start)
            if idx != -1 and (pos == -1 or idx < pos):
                pos = idx
                marker = c
        if pos == -1 or marker is None:
            break
        ns = pos + len(marker)
        ne = ns
        while ne < len(data) and ne < ns + 30:
            b = data[ne]
            if b < 32 or b > 126: break
            ne += 1
        name = ""
        if ne > ns:
            try: name = data[ns:ne].decode('ascii')
            except: pass
        if len(name) >= 3 and not name.startswith('GameMode') and name not in seen:
            seen.add(name)
            eid_be = struct.unpack_from(">H", data, pos + ENTITY_ID_OFFSET)[0] if pos + ENTITY_ID_OFFSET + 2 <= len(data) else None
            hero = "Unknown"
            if pos + HERO_ID_OFFSET + 2 <= len(data):
                bhid = int.from_bytes(data[pos + HERO_ID_OFFSET:pos + HERO_ID_OFFSET + 2], 'little')
                hero = BINARY_HERO_ID_MAP.get(bhid, "Unknown")
            players.append({'name': name, 'entity_id_be': eid_be, 'hero': hero,
                          'role': HERO_ROLES.get(hero, '?')})
        search_start = pos + 1
    return players


def scan_events_with_offset(data, eid_set):
    """Scan acquire and cost events, preserving byte offsets for pairing."""
    events = []  # (offset, type, eid, data_dict)

    # Acquire events
    pos = 0
    while True:
        pos = data.find(ITEM_ACQUIRE_HEADER, pos)
        if pos == -1: break
        if pos + 20 > len(data):
            pos += 1; continue
        if data[pos+3:pos+5] != b'\x00\x00':
            pos += 1; continue
        eid = struct.unpack_from(">H", data, pos + 5)[0]
        if eid not in eid_set:
            pos += 1; continue
        qty = data[pos + 9]
        item_id = struct.unpack_from("<H", data, pos + 10)[0]
        counter = struct.unpack_from(">H", data, pos + 14)[0]
        ts_raw = struct.unpack_from(">f", data, pos + 16)[0]
        ts = round(ts_raw, 1) if 0 < ts_raw < 2400 else None
        events.append((pos, 'acquire', eid, {
            'item_id': item_id, 'qty': qty, 'counter': counter, 'ts': ts
        }))
        pos += 3

    # Cost events
    pos = 0
    while True:
        pos = data.find(CREDIT_HEADER, pos)
        if pos == -1: break
        if pos + 12 > len(data):
            pos += 1; continue
        if data[pos+3:pos+5] != b'\x00\x00':
            pos += 1; continue
        eid = struct.unpack_from(">H", data, pos + 5)[0]
        if eid not in eid_set:
            pos += 3; continue
        value = struct.unpack_from(">f", data, pos + 7)[0]
        action = data[pos + 11]
        if action == 0x06 and not math.isnan(value) and value < 0:
            events.append((pos, 'cost', eid, {'cost': round(abs(value))}))
        pos += 3

    events.sort(key=lambda x: x[0])
    return events


def trace_player_builds(events, eid_map):
    """
    For each player, trace the purchase sequence with costs.
    Pair each acquire event with the nearest preceding cost event.
    """
    builds = {}  # player_name -> list of (item_id, cost, ts, qty)

    # Group events by player
    player_events = defaultdict(list)
    for offset, etype, eid, data in events:
        pinfo = eid_map.get(eid)
        if pinfo:
            player_events[pinfo['name']].append((offset, etype, data))

    for player_name, pevents in player_events.items():
        build = []
        last_cost = None
        for offset, etype, data in pevents:
            if etype == 'cost':
                last_cost = data['cost']
            elif etype == 'acquire':
                cost = last_cost
                last_cost = None  # consume the cost
                build.append({
                    'item_id': data['item_id'],
                    'cost': cost,
                    'ts': data.get('ts'),
                    'qty': data['qty'],
                })
        builds[player_name] = build
    return builds


def analyze_transitions(all_builds, player_info_map):
    """
    Analyze item transition patterns: which items follow which items.
    This reveals upgrade trees.
    """
    # Track: for each item_id, what items are bought AFTER it (within 3 steps)
    transitions = defaultdict(Counter)  # item_id -> Counter of next item_ids

    # Track: pairs of consecutive shop-item purchases (excluding qty=2 abilities)
    for player_name, build in all_builds.items():
        shop_items = [b for b in build if b['qty'] == 1 and b['item_id'] >= 200]
        for i in range(len(shop_items) - 1):
            curr = shop_items[i]['item_id']
            next_item = shop_items[i + 1]['item_id']
            transitions[curr][next_item] += 1

    return transitions


def main():
    print("=" * 90)
    print("ITEM UPGRADE TREE ANALYZER")
    print("=" * 90)

    truth = load_truth()

    all_builds = {}
    player_info = {}

    for match_idx in range(min(8, len(truth['matches']))):
        match = truth['matches'][match_idx]
        frames = load_frames(match['replay_file'])
        if not frames: continue

        players = extract_players(frames[0][1])
        eid_map = {p['entity_id_be']: p for p in players}
        eid_set = set(eid_map.keys())

        all_data = b"".join(d for _, d in frames)
        events = scan_events_with_offset(all_data, eid_set)
        builds = trace_player_builds(events, eid_map)

        for pname, build in builds.items():
            key = f"M{match_idx+1}_{pname}"
            all_builds[key] = build
            pinfo = next((p for p in players if p['name'] == pname), None)
            if pinfo:
                player_info[key] = pinfo

    # Analyze all WP carry builds
    print(f"\n{'=' * 90}")
    print("WP CARRY COMPLETE BUILD ORDERS (shop items only)")
    print(f"{'=' * 90}")

    for key in sorted(all_builds.keys()):
        pinfo = player_info.get(key, {})
        if pinfo.get('role') != 'wp':
            continue
        build = all_builds[key]
        shop_items = [b for b in build if b['qty'] == 1 and b['item_id'] >= 200]
        if len(shop_items) < 3:
            continue

        print(f"\n  {key} ({pinfo.get('hero', '?')}):")
        for i, item in enumerate(shop_items):
            iid = item['item_id']
            name = ITEM_ID_MAP.get(iid, {}).get('name', f'??_{iid}')
            known = "  " if iid in ITEM_ID_MAP else "* "
            cost = f"{item['cost']}g" if item['cost'] else "free"
            ts = f"{item['ts']:.0f}s" if item['ts'] else "?"
            print(f"    {known}{i+1:>2}. ID {iid:>3d} {name:<25} cost={cost:<8} ts={ts}")

    # Analyze captain builds
    print(f"\n{'=' * 90}")
    print("CAPTAIN COMPLETE BUILD ORDERS (shop items only)")
    print(f"{'=' * 90}")

    for key in sorted(all_builds.keys()):
        pinfo = player_info.get(key, {})
        if pinfo.get('role') != 'cap':
            continue
        build = all_builds[key]
        shop_items = [b for b in build if b['qty'] == 1 and b['item_id'] >= 200]
        if len(shop_items) < 3:
            continue

        print(f"\n  {key} ({pinfo.get('hero', '?')}):")
        for i, item in enumerate(shop_items):
            iid = item['item_id']
            name = ITEM_ID_MAP.get(iid, {}).get('name', f'??_{iid}')
            known = "  " if iid in ITEM_ID_MAP else "* "
            cost = f"{item['cost']}g" if item['cost'] else "free"
            ts = f"{item['ts']:.0f}s" if item['ts'] else "?"
            print(f"    {known}{i+1:>2}. ID {iid:>3d} {name:<25} cost={cost:<8} ts={ts}")

    # Item ID frequency by role
    print(f"\n{'=' * 90}")
    print("ITEM ID × HERO ROLE MATRIX (shop items, qty=1 only)")
    print(f"{'=' * 90}")

    role_counts = defaultdict(lambda: Counter())  # item_id -> {role: count}
    cost_data = defaultdict(list)

    for key, build in all_builds.items():
        pinfo = player_info.get(key, {})
        role = pinfo.get('role', '?')
        for item in build:
            if item['qty'] == 1 and item['item_id'] >= 200:
                iid = item['item_id']
                role_counts[iid][role] += 1
                if item['cost'] is not None:
                    cost_data[iid].append(item['cost'])

    # Print matrix sorted by ID
    print(f"\n  {'ID':>4s} {'Name':<20s} {'WP':>4s} {'CP':>4s} {'BR':>4s} {'CAP':>4s} "
          f"{'Total':>5s}  {'MinCost':>7s} {'ModeCost':>8s} {'Category':>10s}")
    print(f"  {'─'*4} {'─'*20} {'─'*4} {'─'*4} {'─'*4} {'─'*4} {'─'*5}  {'─'*7} {'─'*8} {'─'*10}")

    for iid in sorted(role_counts.keys()):
        rc = role_counts[iid]
        total = sum(rc.values())
        if total < 3:
            continue

        name = ITEM_ID_MAP.get(iid, {}).get('name', f'??_{iid}')
        costs = cost_data.get(iid, [])
        min_cost = min(costs) if costs else 0
        mode_cost = Counter(costs).most_common(1)[0][0] if costs else 0

        # Categorize
        wp_pct = rc.get('wp', 0) / total
        cp_pct = rc.get('cp', 0) / total
        cap_pct = rc.get('cap', 0) / total
        br_pct = rc.get('br', 0) / total

        if wp_pct > 0.6:
            cat = "WEAPON"
        elif cp_pct > 0.5:
            cat = "CRYSTAL"
        elif cap_pct > 0.5:
            cat = "DEFENSE"
        elif cap_pct + br_pct > 0.5:
            cat = "DEF/UTL"
        elif wp_pct + cp_pct + br_pct + cap_pct < 0.6:
            cat = "UTILITY"
        else:
            cat = "MIXED"

        in_map = "  " if iid in ITEM_ID_MAP else "* "
        print(f"  {in_map}{iid:>3d} {name:<20s} {rc.get('wp',0):>4d} {rc.get('cp',0):>4d} "
              f"{rc.get('br',0):>4d} {rc.get('cap',0):>4d} {total:>5d}  "
              f"{min_cost:>7d} {mode_cost:>8d} {cat:>10s}")

    # Transition analysis
    print(f"\n{'=' * 90}")
    print("COMMON ITEM TRANSITIONS (A → B, count >= 3)")
    print(f"{'=' * 90}")

    transitions = analyze_transitions(all_builds, player_info)
    for src_id in sorted(transitions.keys()):
        src_name = ITEM_ID_MAP.get(src_id, {}).get('name', f'??_{src_id}')
        top_transitions = transitions[src_id].most_common(5)
        if not any(c >= 3 for _, c in top_transitions):
            continue
        print(f"\n  ID {src_id:>3d} ({src_name}) →")
        for dst_id, count in top_transitions:
            if count < 3:
                break
            dst_name = ITEM_ID_MAP.get(dst_id, {}).get('name', f'??_{dst_id}')
            print(f"    → ID {dst_id:>3d} ({dst_name}): {count} times")

    # Cost-based tier classification
    print(f"\n{'=' * 90}")
    print("ITEM TIER CLASSIFICATION BY COST")
    print(f"{'=' * 90}")

    tiers = {"T1 (≤350g)": [], "T2 (351-900g)": [], "T3 (>900g)": []}
    for iid in sorted(role_counts.keys()):
        costs = cost_data.get(iid, [])
        if not costs:
            continue
        mode_cost = Counter(costs).most_common(1)[0][0]
        rc = role_counts[iid]
        total = sum(rc.values())
        if total < 3:
            continue

        name = ITEM_ID_MAP.get(iid, {}).get('name', f'??_{iid}')
        entry = f"ID {iid:>3d} ({name}, mode={mode_cost}g, n={total})"

        if mode_cost <= 350:
            tiers["T1 (≤350g)"].append(entry)
        elif mode_cost <= 900:
            tiers["T2 (351-900g)"].append(entry)
        else:
            tiers["T3 (>900g)"].append(entry)

    for tier_name, items in tiers.items():
        print(f"\n  {tier_name}:")
        for item in items:
            print(f"    {item}")


if __name__ == '__main__':
    main()
