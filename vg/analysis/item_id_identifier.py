#!/usr/bin/env python3
"""
Item ID Identifier - Map unknown replay item IDs to actual Vainglory items.
============================================================================

The replay [10 04 3D] acquire events use item IDs in the 201-254 range.
Crystal items (201-229) are already mapped. This script identifies the
remaining unknown IDs (204-254 gaps) as weapon/defense/utility items.

Strategy:
1. Proximity-based cost pairing: find [10 04 1D] cost events immediately
   before each [10 04 3D] acquire event for the same player
2. First-purchase cost analysis: the first buy of a T1 item = full price
3. Hero role correlation: WP carries buy weapon, captains buy defense
4. VG item price matching: cross-reference with known shop prices

Usage:
    python -m vg.analysis.item_id_identifier
"""

import sys
import struct
import json
import math
from pathlib import Path
from collections import defaultdict, Counter

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from vg.core.vgr_mapping import ITEM_ID_MAP, BINARY_HERO_ID_MAP

# Known VG item prices (total cost to buy outright)
# Source: Vainglory wiki / in-game shop
VG_ITEM_PRICES = {
    # Weapon T1
    "Weapon Blade": 300,
    "Book of Eulogies": 300,
    "Swift Shooter": 300,
    "Minion's Foot": 300,
    # Weapon T2
    "Heavy Steel": 1150,
    "Six Sins": 650,
    "Blazing Salvo": 700,
    "Lucky Strike": 900,
    "Piercing Spear": 900,
    "Barbed Needle": 800,
    # Weapon T3
    "Sorrowblade": 3100,
    "Serpent Mask": 2800,
    "Tornado Trigger": 2600,
    "Tyrant's Monocle": 2150,
    "Bonesaw": 2700,
    "Poisoned Shiv": 2250,
    "Breaking Point": 2600,
    "Tension Bow": 2150,
    "Spellsword": 2600,
    # Crystal T1
    "Crystal Bit": 300,
    "Energy Battery": 300,
    "Hourglass": 250,
    # Crystal T2
    "Eclipse Prism": 650,
    "Heavy Prism": 1150,
    "Piercing Shard": 900,
    "Chronograph": 800,
    "Void Battery": 700,
    # Crystal T3
    "Shatterglass": 3000,
    "Frostburn": 2600,
    "Eve of Harvest": 2600,
    "Broken Myth": 2150,
    "Clockwork": 2400,
    "Alternating Current": 2800,
    "Dragon's Eye": 2700,
    "Spellfire": 2400,
    "Aftershock": 2100,
    # Defense T1
    "Light Shield": 300,
    "Light Armor": 300,
    "Oakheart": 300,
    # Defense T2
    "Kinetic Shield": 800,
    "Coat of Plates": 800,
    "Dragonheart": 650,
    "Reflex Block": 700,
    # Defense T3
    "Aegis": 2100,
    "Metal Jacket": 2100,
    "Fountain of Renewal": 2300,
    "Crucible": 1900,
    "Atlas Pauldron": 1900,
    "Slumbering Husk": 1600,
    "Pulseweave": 1800,
    "Capacitor Plate": 1950,
    # Utility - Boots
    "Sprint Boots": 300,
    "Travel Boots": 500,
    "Journey Boots": 1900,
    "Halcyon Chargers": 1900,
    "War Treads": 2200,
    "Teleport Boots": 2500,
    # Utility - Vision
    "Flare": 25,
    "Scout Trap": 50,
    "Flare Gun": 300,
    "Contraption": 1800,
    "Superscout 2000": 600,
    # Utility - Other
    "Nullwave Gauntlet": 2050,
    "Echo": 2300,
    "Stormcrown": 2200,
}

# Hero role classification for correlation
HERO_ROLES = {
    # WP Carries (weapon buyers)
    "Kinetic": "wp_carry", "Gwen": "wp_carry", "Caine": "wp_carry",
    "Kestrel": "wp_carry", "Ringo": "wp_carry", "Silvernail": "wp_carry",
    "Kensei": "wp_carry", "Vox": "wp_carry", "Baron": "wp_carry",
    "SAW": "wp_carry", "Skye": "wp_carry",  # Skye can go WP or CP
    # CP Mages (crystal buyers)
    "Samuel": "cp_mage", "Skaarf": "cp_mage", "Celeste": "cp_mage",
    "Reza": "cp_mage", "Magnus": "cp_mage", "Malene": "cp_mage",
    "Varya": "cp_mage", "Warhawk": "cp_mage",
    # CP Assassins
    "Ishtar": "cp_assassin", "Anka": "cp_assassin",
    # Bruisers (mixed offense + defense)
    "Blackfeather": "bruiser", "Ylva": "bruiser", "Inara": "bruiser",
    "Ozo": "bruiser", "Tony": "bruiser", "Reim": "bruiser",
    "San Feng": "bruiser", "Kensei": "bruiser",
    # Captains (defense/utility buyers)
    "Lorelai": "captain", "Lyra": "captain", "Ardan": "captain",
    "Phinn": "captain", "Baptiste": "captain", "Catherine": "captain",
    "Grumpjaw": "captain", "Fortress": "captain", "Lance": "captain",
    "Churnwalker": "captain", "Flicker": "captain", "Grace": "captain",
    "Adagio": "captain", "Yates": "captain",
}

PLAYER_BLOCK_MARKER = bytes([0xDA, 0x03, 0xEE])
PLAYER_BLOCK_MARKER_ALT = bytes([0xE0, 0x03, 0xEE])
ENTITY_ID_OFFSET = 0xA5
HERO_ID_OFFSET = 0xA9
TEAM_OFFSET = 0xD5

ITEM_ACQUIRE_HEADER = bytes([0x10, 0x04, 0x3D])
CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])


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
            team_id = data[pos + TEAM_OFFSET] if pos + TEAM_OFFSET < len(data) else None
            team = {1: "left", 2: "right"}.get(team_id, "unknown")
            hero = "Unknown"
            if pos + HERO_ID_OFFSET + 2 <= len(data):
                bhid = int.from_bytes(data[pos + HERO_ID_OFFSET:pos + HERO_ID_OFFSET + 2], 'little')
                hero = BINARY_HERO_ID_MAP.get(bhid, "Unknown")
            players.append({'name': name, 'entity_id_be': eid_be, 'team': team, 'hero': hero})
        search_start = pos + 1
    return players


def scan_all_events(data, eid_set):
    """Scan both acquire and cost events, returning them with byte offsets."""
    acquires = []
    costs = []

    # Scan acquire events
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
        acquires.append({
            'offset': pos, 'eid': eid, 'item_id': item_id,
            'qty': qty, 'counter': counter, 'timestamp': ts,
        })
        pos += 3

    # Scan cost events (action=0x06, negative value)
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
            costs.append({
                'offset': pos, 'eid': eid, 'cost': round(abs(value)),
            })
        pos += 3

    return acquires, costs


def proximity_pair(acquires, costs):
    """
    Pair each acquire event with the nearest PRECEDING cost event for the
    same entity. The cost event should be within 500 bytes before the acquire.
    """
    # Sort costs by offset for binary search
    costs_by_eid = defaultdict(list)
    for c in costs:
        costs_by_eid[c['eid']].append(c)
    for eid in costs_by_eid:
        costs_by_eid[eid].sort(key=lambda x: x['offset'])

    pairs = []
    used_costs = set()  # track which cost offsets are already paired

    for acq in acquires:
        eid = acq['eid']
        acq_offset = acq['offset']
        eid_costs = costs_by_eid.get(eid, [])

        # Find the nearest preceding cost event within 500 bytes
        best = None
        best_dist = 501
        for c in reversed(eid_costs):
            if c['offset'] >= acq_offset:
                continue
            dist = acq_offset - c['offset']
            if dist > 500:
                break
            if c['offset'] not in used_costs and dist < best_dist:
                best = c
                best_dist = dist
                break  # take the closest one

        if best:
            used_costs.add(best['offset'])
            pairs.append({
                'eid': eid,
                'item_id': acq['item_id'],
                'qty': acq['qty'],
                'cost': best['cost'],
                'timestamp': acq['timestamp'],
                'counter': acq['counter'],
                'offset_dist': best_dist,
            })
        else:
            # No paired cost (could be free item or system event)
            pairs.append({
                'eid': eid,
                'item_id': acq['item_id'],
                'qty': acq['qty'],
                'cost': None,
                'timestamp': acq['timestamp'],
                'counter': acq['counter'],
                'offset_dist': None,
            })

    return pairs


def main():
    print("=" * 90)
    print("ITEM ID IDENTIFIER - Map Unknown Replay IDs to Vainglory Items")
    print("=" * 90)

    truth = load_truth()

    # Collect per-ID data across all matches
    id_data = defaultdict(lambda: {
        'costs': [],           # all paired costs
        'first_costs': [],     # first purchase cost per player per match
        'heroes': Counter(),
        'roles': Counter(),
        'qtys': Counter(),
        'timestamps': [],
        'total_count': 0,
        'matches_seen': set(),
    })

    for match_idx in range(min(8, len(truth['matches']))):
        match = truth['matches'][match_idx]
        replay_file = match['replay_file']
        frames = load_frames(replay_file)
        if not frames: continue

        players = extract_players(frames[0][1])
        eid_map = {p['entity_id_be']: p for p in players}
        eid_set = set(eid_map.keys())

        all_data = b"".join(d for _, d in frames)
        acquires, costs = scan_all_events(all_data, eid_set)
        pairs = proximity_pair(acquires, costs)

        # Track first purchase per player per item
        seen_per_player = defaultdict(set)  # eid -> set of item_ids already seen

        for pair in pairs:
            iid = pair['item_id']
            eid = pair['eid']
            player_info = eid_map.get(eid, {})
            hero = player_info.get('hero', 'Unknown')
            role = HERO_ROLES.get(hero, 'unknown')

            d = id_data[iid]
            d['total_count'] += 1
            d['heroes'][hero] += 1
            d['roles'][role] += 1
            d['qtys'][pair['qty']] += 1
            d['matches_seen'].add(match_idx)
            if pair['timestamp']:
                d['timestamps'].append(pair['timestamp'])
            if pair['cost'] is not None:
                d['costs'].append(pair['cost'])
                if iid not in seen_per_player[eid]:
                    d['first_costs'].append(pair['cost'])
                    seen_per_player[eid].add(iid)

    # Separate known vs unknown
    known_ids = sorted([iid for iid in id_data if iid in ITEM_ID_MAP])
    unknown_ids = sorted([iid for iid in id_data if iid not in ITEM_ID_MAP])

    # First, validate known items have correct costs
    print(f"\n{'=' * 90}")
    print("KNOWN ITEM COST VALIDATION (Crystal items)")
    print(f"{'=' * 90}")
    for iid in known_ids:
        info = ITEM_ID_MAP[iid]
        d = id_data[iid]
        if not d['first_costs']:
            continue
        first_costs = sorted(d['first_costs'])
        median_first = first_costs[len(first_costs)//2]
        expected = VG_ITEM_PRICES.get(info['name'], '?')
        match_str = "OK" if expected != '?' and abs(median_first - expected) < 50 else "MISMATCH"
        print(f"  ID {iid:>3d} {info['name']:<25} Expected: {expected:>5}g  "
              f"Median first: {median_first:>5}g  [{match_str}]  "
              f"Range: {min(first_costs)}-{max(first_costs)}")

    # Analyze unknown items
    print(f"\n{'=' * 90}")
    print("UNKNOWN ITEM IDENTIFICATION")
    print(f"{'=' * 90}")

    # Group by likely category based on hero roles
    wp_items = []  # primarily bought by WP carries
    cp_items = []  # primarily bought by CP mages
    def_items = []  # primarily bought by captains/tanks
    boot_items = []  # bought by everyone roughly equally
    ability_items = []  # qty=2 (ability upgrades)
    other_items = []

    for iid in unknown_ids:
        d = id_data[iid]
        total = d['total_count']
        if total < 2:
            continue

        # Classify by qty
        if d['qtys'].get(2, 0) > d['qtys'].get(1, 0):
            ability_items.append(iid)
            continue

        # Classify by role distribution
        wp_pct = d['roles'].get('wp_carry', 0) / total
        cp_pct = (d['roles'].get('cp_mage', 0) + d['roles'].get('cp_assassin', 0)) / total
        def_pct = d['roles'].get('captain', 0) / total
        bruiser_pct = d['roles'].get('bruiser', 0) / total

        if wp_pct > 0.5:
            wp_items.append(iid)
        elif cp_pct > 0.4:
            cp_items.append(iid)
        elif def_pct > 0.35:
            def_items.append(iid)
        elif def_pct + bruiser_pct > 0.4:
            def_items.append(iid)
        else:
            other_items.append(iid)

    def print_id_profile(iid, category_hint):
        d = id_data[iid]
        total = d['total_count']
        first_costs = sorted(d['first_costs']) if d['first_costs'] else []
        all_costs = sorted(d['costs']) if d['costs'] else []

        # Median first cost (most reliable for identifying the item)
        median_first = first_costs[len(first_costs)//2] if first_costs else None
        # Mode cost (most common)
        cost_counter = Counter(d['costs'])
        mode_cost = cost_counter.most_common(1)[0][0] if cost_counter else None
        # Min cost (could be upgrade cost)
        min_cost = min(all_costs) if all_costs else None

        # Average timestamp (for tier estimation)
        avg_ts = sum(d['timestamps']) / len(d['timestamps']) if d['timestamps'] else None

        # Top heroes
        top_heroes = d['heroes'].most_common(5)
        role_dist = d['roles'].most_common()

        # Try to match to VG items
        candidates = []
        if median_first and category_hint:
            for item_name, price in VG_ITEM_PRICES.items():
                if abs(median_first - price) <= 50:
                    candidates.append((item_name, price, abs(median_first - price)))
            # Also try min cost match (for T1 components)
            if min_cost and min_cost != median_first:
                for item_name, price in VG_ITEM_PRICES.items():
                    if abs(min_cost - price) <= 30:
                        already = any(c[0] == item_name for c in candidates)
                        if not already:
                            candidates.append((item_name, price, abs(min_cost - price)))
            candidates.sort(key=lambda x: x[2])

        print(f"\n  ID {iid:>3d} (0x{iid:04X}): {total} occurrences, "
              f"{len(d['matches_seen'])} matches")
        print(f"    Qty: {dict(d['qtys'])}")
        if first_costs:
            print(f"    First-purchase costs: median={median_first}g, "
                  f"range={min(first_costs)}-{max(first_costs)}g, n={len(first_costs)}")
        if mode_cost:
            print(f"    Mode cost: {mode_cost}g  Min cost: {min_cost}g")
        if avg_ts:
            tier_est = "T1" if avg_ts < 120 else "T2" if avg_ts < 400 else "T3"
            print(f"    Avg timestamp: {avg_ts:.0f}s → likely {tier_est}")
        print(f"    Heroes: {dict(top_heroes)}")
        print(f"    Roles: {dict(role_dist)}")
        if candidates:
            print(f"    CANDIDATES by cost match:")
            for name, price, diff in candidates[:5]:
                print(f"      {name}: {price}g (diff: {diff}g)")

    print(f"\n--- WEAPON ITEMS (bought mainly by WP carries) ---")
    for iid in sorted(wp_items):
        print_id_profile(iid, "weapon")

    print(f"\n--- CP-ADJACENT ITEMS (bought mainly by CP mages) ---")
    for iid in sorted(cp_items):
        print_id_profile(iid, "crystal")

    print(f"\n--- DEFENSE ITEMS (bought mainly by captains/tanks) ---")
    for iid in sorted(def_items):
        print_id_profile(iid, "defense")

    print(f"\n--- MIXED/UTILITY ITEMS (bought by everyone) ---")
    for iid in sorted(other_items):
        print_id_profile(iid, "utility")

    print(f"\n--- ABILITY/TALENT UPGRADES (qty=2) ---")
    for iid in sorted(ability_items):
        d = id_data[iid]
        print(f"  ID {iid:>3d}: {d['total_count']} occ, heroes={dict(d['heroes'].most_common(3))}")

    # Summary: build order analysis for a single player
    print(f"\n{'=' * 90}")
    print("SAMPLE BUILD ORDER (Match 1, WP carry Kestrel)")
    print(f"{'=' * 90}")

    match = truth['matches'][0]
    frames = load_frames(match['replay_file'])
    players = extract_players(frames[0][1])
    # Find Kestrel player
    kestrel = None
    for p in players:
        if p['hero'] == 'Kestrel':
            kestrel = p
            break
    if kestrel:
        eid_set = {kestrel['entity_id_be']}
        all_data = b"".join(d for _, d in frames)
        acquires, costs = scan_all_events(all_data, eid_set)
        pairs = proximity_pair(acquires, costs)

        print(f"  Player: {kestrel['name']} ({kestrel['hero']})")
        for i, pair in enumerate(pairs):
            iid = pair['item_id']
            name = ITEM_ID_MAP.get(iid, {}).get('name', f'?Unknown_{iid}')
            cost_str = f"{pair['cost']}g" if pair['cost'] else "free"
            ts_str = f"{pair['timestamp']:.0f}s" if pair['timestamp'] else "?"
            print(f"    {i+1:>2}. [{ts_str:>5}] ID {iid:>3d} {name:<25} "
                  f"qty={pair['qty']} cost={cost_str}")

    # Also show a captain build
    print(f"\n{'=' * 90}")
    print("SAMPLE BUILD ORDER (Match 1, Captain Lorelai/Grumpjaw)")
    print(f"{'=' * 90}")

    for p in players:
        if p['hero'] in ('Lorelai', 'Grumpjaw', 'Ardan', 'Lyra'):
            eid_set = {p['entity_id_be']}
            all_data = b"".join(d for _, d in frames)
            acquires, costs = scan_all_events(all_data, eid_set)
            pairs = proximity_pair(acquires, costs)

            print(f"\n  Player: {p['name']} ({p['hero']})")
            for i, pair in enumerate(pairs):
                iid = pair['item_id']
                name = ITEM_ID_MAP.get(iid, {}).get('name', f'?Unknown_{iid}')
                cost_str = f"{pair['cost']}g" if pair['cost'] else "free"
                ts_str = f"{pair['timestamp']:.0f}s" if pair['timestamp'] else "?"
                print(f"    {i+1:>2}. [{ts_str:>5}] ID {iid:>3d} {name:<25} "
                      f"qty={pair['qty']} cost={cost_str}")


if __name__ == '__main__':
    main()
