#!/usr/bin/env python3
"""
Item-to-Player Mapping Research v5 - Unknown Item ID Catalog
=============================================================
Catalogs all unknown item IDs found in [10 04 3D] events and tries to identify them.

Known unknowns from v4 analysis:
  IDs 0-27: likely ability/talent upgrades (qty=2 suggests they come in pairs)
  IDs 206-250: likely boots, consumables, vision items, or shop-exclusive IDs

This script:
1. Collects all unknown item IDs across all matches
2. Analyzes their frequency, quantity, and timing
3. Tries to identify them based on cost and context

Usage:
    python -m vg.analysis.item_player_mapping_v5
"""

import sys
import struct
import json
from pathlib import Path
from collections import defaultdict, Counter

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


def scan_acquire_events(data, eid_map):
    header = bytes([0x10, 0x04, 0x3D])
    results = []
    pos = 0
    while True:
        pos = data.find(header, pos)
        if pos == -1: break
        if pos + 20 > len(data):
            pos += 1; continue
        if data[pos+3:pos+5] != b'\x00\x00':
            pos += 1; continue
        eid = struct.unpack_from(">H", data, pos + 5)[0]
        if eid not in eid_map:
            pos += 1; continue

        qty = data[pos + 9]
        item_id = struct.unpack_from("<H", data, pos + 10)[0]
        counter = struct.unpack_from(">H", data, pos + 14)[0]
        ts = struct.unpack_from(">f", data, pos + 16)[0]

        results.append({
            'eid': eid, 'player': eid_map[eid],
            'qty': qty, 'item_id': item_id,
            'counter': counter,
            'timestamp': round(ts, 1) if 0 < ts < 2000 else None,
        })
        pos += 3
    return results


def scan_purchase_costs(data, eid_map):
    header = bytes([0x10, 0x04, 0x1D])
    results = []
    pos = 0
    while True:
        pos = data.find(header, pos)
        if pos == -1: break
        if pos + 12 > len(data):
            pos += 1; continue
        if data[pos+3:pos+5] != b'\x00\x00':
            pos += 1; continue
        eid = struct.unpack_from(">H", data, pos + 5)[0]
        if eid not in eid_map:
            pos += 1; continue
        value = struct.unpack_from(">f", data, pos + 7)[0]
        action = data[pos + 11]
        if action == 0x06 and value < 0:
            results.append({
                'offset': pos, 'eid': eid, 'player': eid_map[eid],
                'gold_cost': round(abs(value), 1),
            })
        pos += 3
    return results


def pair_costs_with_acquires(cost_events, acquire_events):
    """
    Pair each cost event with the next acquire event for the same player.
    They should appear in order: cost first, then acquire.
    """
    # Group by player
    costs_by_player = defaultdict(list)
    acquires_by_player = defaultdict(list)
    for e in cost_events:
        costs_by_player[e['player']].append(e)
    for e in acquire_events:
        acquires_by_player[e['player']].append(e)

    pairs = []
    for player in costs_by_player:
        costs = sorted(costs_by_player[player], key=lambda x: x['offset'])
        acquires = sorted(acquires_by_player.get(player, []), key=lambda x: x.get('counter', 0))

        # Match 1:1 in order
        for i, cost in enumerate(costs):
            if i < len(acquires):
                pairs.append({
                    'player': player,
                    'gold_cost': cost['gold_cost'],
                    'item_id': acquires[i]['item_id'],
                    'qty': acquires[i]['qty'],
                    'timestamp': acquires[i].get('timestamp'),
                    'counter': acquires[i].get('counter'),
                })
    return pairs


def main():
    print("=" * 80)
    print("ITEM-TO-PLAYER MAPPING v5 - Unknown Item Catalog")
    print("=" * 80)

    truth = load_truth()

    # Collect unknown IDs across all matches
    all_unknown_ids = Counter()  # id -> count
    unknown_contexts = defaultdict(list)  # id -> list of {qty, cost, player, hero, ts}
    all_known_items = Counter()
    total_acquires = 0

    for match_idx in range(min(8, len(truth['matches']))):  # skip match 9 (incomplete)
        match = truth['matches'][match_idx]
        replay_file = match['replay_file']

        frames = load_frames(replay_file)
        if not frames: continue

        players = extract_players(frames[0][1])
        eid_map = {p['entity_id_be']: p['name'] for p in players}
        hero_map = {p['name']: p['hero'] for p in players}

        all_data = b"".join(d for _, d in frames)
        acquires = scan_acquire_events(all_data, eid_map)
        costs = scan_purchase_costs(all_data, eid_map)

        # Pair costs with acquires
        pairs = pair_costs_with_acquires(costs, acquires)

        total_acquires += len(acquires)

        for ev in acquires:
            iid = ev['item_id']
            if iid not in ITEM_ID_MAP:
                all_unknown_ids[iid] += 1
                unknown_contexts[iid].append({
                    'qty': ev['qty'],
                    'player': ev['player'],
                    'hero': hero_map.get(ev['player'], '?'),
                    'ts': ev.get('timestamp'),
                    'match': match_idx + 1,
                })
            else:
                all_known_items[iid] += 1

        # Also collect cost-paired data
        for pair in pairs:
            iid = pair['item_id']
            if iid not in ITEM_ID_MAP:
                # Find existing context entry and add cost
                for ctx in unknown_contexts[iid]:
                    if ctx['player'] == pair['player'] and ctx['match'] == match_idx + 1:
                        ctx['cost'] = pair['gold_cost']
                        break

    # Print results
    print(f"\nTotal acquire events across 8 matches: {total_acquires}")
    print(f"Known items: {sum(all_known_items.values())} ({len(all_known_items)} unique)")
    print(f"Unknown items: {sum(all_unknown_ids.values())} ({len(all_unknown_ids)} unique)")

    # Separate unknowns by ranges
    print(f"\n{'=' * 80}")
    print("UNKNOWN ITEM IDs - Sorted by frequency")
    print(f"{'=' * 80}")

    for iid, count in all_unknown_ids.most_common():
        contexts = unknown_contexts[iid]
        qtys = Counter(c['qty'] for c in contexts)
        costs = [c.get('cost', 0) for c in contexts if c.get('cost')]
        avg_cost = sum(costs) / len(costs) if costs else 0
        cost_range = f"{min(costs):.0f}-{max(costs):.0f}" if costs else "?"
        heroes = Counter(c['hero'] for c in contexts)

        # Try to guess what it is based on cost and frequency
        guess = ""
        if avg_cost > 0:
            if 20 <= avg_cost <= 30:
                guess = "[likely Flare]"
            elif 40 <= avg_cost <= 60:
                guess = "[likely Scout Trap]"
            elif avg_cost == 300:
                guess = "[likely T1 component]"
            elif 400 <= avg_cost <= 600:
                guess = "[likely T2 upgrade or boots]"
            elif 600 <= avg_cost <= 900:
                guess = "[likely T3 upgrade]"
            elif 1000 <= avg_cost:
                guess = "[likely expensive T3]"

        if qtys.get(2, 0) > qtys.get(1, 0):
            guess = "[likely ability/talent - qty=2]"

        print(f"\n  ID {iid:>3d} (0x{iid:04X}): {count} occurrences")
        print(f"    Qty distribution: {dict(qtys)}")
        print(f"    Avg cost: {avg_cost:.0f}g  Range: {cost_range}")
        print(f"    Heroes: {dict(heroes.most_common(5))}")
        if guess:
            print(f"    Guess: {guess}")

    # Print known item summary
    print(f"\n{'=' * 80}")
    print("KNOWN ITEMS - Successfully mapped")
    print(f"{'=' * 80}")

    for iid, count in sorted(all_known_items.items()):
        info = ITEM_ID_MAP[iid]
        print(f"  ID {iid:>3d}: {info['name']:<25} T{info['tier']} {info['category']:<10} x{count}")

    # Per-player final builds (T3 only) for validation
    print(f"\n{'=' * 80}")
    print("PER-PLAYER FINAL T3 BUILDS (Matches 1-8)")
    print(f"{'=' * 80}")

    for match_idx in range(min(8, len(truth['matches']))):
        match = truth['matches'][match_idx]
        replay_file = match['replay_file']

        frames = load_frames(replay_file)
        if not frames: continue

        players = extract_players(frames[0][1])
        eid_map = {p['entity_id_be']: p['name'] for p in players}

        all_data = b"".join(d for _, d in frames)
        acquires = scan_acquire_events(all_data, eid_map)

        print(f"\n  Match {match_idx + 1}:")
        by_player = defaultdict(list)
        for ev in acquires:
            if ev['item_id'] in ITEM_ID_MAP and ITEM_ID_MAP[ev['item_id']].get('tier', 0) >= 3:
                by_player[ev['player']].append(ITEM_ID_MAP[ev['item_id']]['name'])

        for p in players:
            items = by_player.get(p['name'], [])
            if items:
                print(f"    {p['name']:<20} ({p['hero']:<15}): {', '.join(items)}")
            else:
                print(f"    {p['name']:<20} ({p['hero']:<15}): [no T3 items]")


if __name__ == '__main__':
    main()
