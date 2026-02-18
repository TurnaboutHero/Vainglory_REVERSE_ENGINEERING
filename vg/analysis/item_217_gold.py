#!/usr/bin/env python3
"""
Track gold spending near ID 217 acquire events to determine item price.
Also check if top-tier direct purchase generates intermediate item events.
"""

import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from vg.core.vgr_parser import VGRParser
from vg.core.vgr_mapping import ITEM_ID_MAP, HERO_ID_MAP

ITEM_ACQUIRE_HEADER = bytes([0x10, 0x04, 0x3D])
CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])
REPLAY_DIR = Path(r"D:\Desktop\My Folder\Game\VG\vg replay")

HERO_ROLES = {info["name"]: info["role"] for info in HERO_ID_MAP.values()}


def le_to_be(eid_le):
    return struct.unpack('>H', struct.pack('<H', eid_le))[0]


def load_replay(replay_path):
    try:
        parser = VGRParser(str(replay_path), detect_heroes=False, auto_truth=False)
        parsed = parser.parse()
    except:
        return None
    players = {}
    for team in ["left", "right"]:
        for p in parsed.get("teams", {}).get(team, []):
            eid_le = p.get("entity_id", 0)
            if eid_le:
                eid_be = le_to_be(eid_le)
                players[eid_be] = {
                    "name": p.get("name", "?"),
                    "hero": p.get("hero_name", "?") or "?",
                    "role": HERO_ROLES.get(p.get("hero_name", ""), "?"),
                }
    stem_base = replay_path.stem.rsplit('.', 1)[0]
    frame_files = sorted(
        replay_path.parent.glob(f"{stem_base}.*.vgr"),
        key=lambda f: int(f.stem.split('.')[-1]) if f.stem.split('.')[-1].isdigit() else 0
    )
    all_data = b"".join(f.read_bytes() for f in frame_files)
    return players, all_data


def find_gold_near_acquire(all_data, acquire_pos, target_eid, search_range=300):
    """
    Find [10 04 1D] gold spending events (action=0x06, value<0) for target_eid
    within search_range bytes BEFORE and AFTER the acquire position.
    """
    gold_events = []

    start = max(0, acquire_pos - search_range)
    end = min(len(all_data), acquire_pos + search_range)

    pos = start
    while pos < end:
        pos = all_data.find(CREDIT_HEADER, pos, end)
        if pos == -1:
            break
        if pos + 13 > len(all_data):
            pos += 1
            continue
        if all_data[pos + 3:pos + 5] != b'\x00\x00':
            pos += 1
            continue

        eid = struct.unpack_from(">H", all_data, pos + 5)[0]
        if eid != target_eid:
            pos += 1
            continue

        value = struct.unpack_from(">f", all_data, pos + 7)[0]
        action = all_data[pos + 11]
        sell_flag = all_data[pos + 12] if pos + 13 <= len(all_data) else 0

        offset_from_acquire = pos - acquire_pos
        gold_events.append({
            "value": value,
            "action": action,
            "sell_flag": sell_flag,
            "offset": offset_from_acquire,
            "pos": pos,
        })
        pos += 3

    return gold_events


def scan_acquire_with_positions(all_data, players):
    """Scan [10 04 3D] events and return positions + data."""
    events = []  # list of (pos, eid, qty, item_id, counter)
    pos = 0
    while True:
        pos = all_data.find(ITEM_ACQUIRE_HEADER, pos)
        if pos == -1:
            break
        if pos + 20 > len(all_data):
            pos += 1
            continue
        if all_data[pos + 3:pos + 5] != b'\x00\x00':
            pos += 1
            continue

        eid = struct.unpack_from(">H", all_data, pos + 5)[0]
        if eid not in players:
            pos += 1
            continue

        qty = all_data[pos + 9]
        if qty not in (1, 2):
            pos += 1
            continue

        item_id = struct.unpack_from("<H", all_data, pos + 10)[0]
        if item_id > 255:
            item_id = item_id & 0xFF

        counter = struct.unpack_from(">H", all_data, pos + 14)[0]

        events.append({
            "pos": pos,
            "eid": eid,
            "qty": qty,
            "item_id": item_id,
            "counter": counter,
        })
        pos += 3

    return events


def main():
    replays = sorted([
        vgr for vgr in REPLAY_DIR.rglob("*.0.vgr")
        if "__MACOSX" not in str(vgr)
    ])

    print("=" * 80)
    print("ID 217 GOLD TRACKING - Determine item price from gold deductions")
    print("=" * 80)

    # Collect gold deductions near 217 purchases
    gold_for_217 = []  # list of (hero, gold_amount, action, offset)

    # Also check: when buying T3 directly, do intermediate items appear?
    # Look at Stormcrown (qty=2 ID 7) buyers - do they always have SGB (219)?
    stormcrown_buyers = []

    for rp in replays:
        result = load_replay(rp)
        if not result:
            continue
        players, all_data = result

        acquire_events = scan_acquire_with_positions(all_data, players)

        # Group by eid
        by_eid = defaultdict(list)
        for ev in acquire_events:
            by_eid[ev["eid"]].append(ev)

        for ev in acquire_events:
            # Track 217 gold spending
            if ev["item_id"] == 217 and ev["qty"] == 1:
                pinfo = players[ev["eid"]]
                gold_events = find_gold_near_acquire(all_data, ev["pos"], ev["eid"], search_range=200)

                # Find the gold deduction closest to the acquire event (action=0x06, value<0)
                purchases = [g for g in gold_events if g["action"] == 0x06 and g["value"] < 0 and g["sell_flag"] == 0]

                if purchases:
                    # Closest by absolute offset
                    closest = min(purchases, key=lambda g: abs(g["offset"]))
                    gold_for_217.append({
                        "hero": pinfo["hero"],
                        "role": pinfo["role"],
                        "gold": closest["value"],
                        "offset": closest["offset"],
                        "all_purchases": [(g["value"], g["offset"]) for g in purchases],
                    })
                else:
                    gold_for_217.append({
                        "hero": pinfo["hero"],
                        "role": pinfo["role"],
                        "gold": None,
                        "offset": None,
                        "all_purchases": [],
                    })

            # Track Stormcrown buyers
            if ev["item_id"] == 7 and ev["qty"] == 2:
                pinfo = players[ev["eid"]]
                player_items = set(e["item_id"] for e in by_eid[ev["eid"]])
                stormcrown_buyers.append({
                    "hero": pinfo["hero"],
                    "has_sgb": 219 in player_items,
                    "has_chronograph": 218 in player_items,
                    "has_oakheart": 212 in player_items,
                    "has_217": 217 in player_items,
                    "has_hourglass": 216 in player_items,
                    "items": sorted(player_items),
                })

    # ==========================================================================
    # 1. Gold deduction analysis for 217
    # ==========================================================================
    print(f"\n{'='*70}")
    print(f"1. GOLD DEDUCTIONS near ID 217 purchase ({len(gold_for_217)} events)")
    print(f"{'='*70}")

    found = [g for g in gold_for_217 if g["gold"] is not None]
    not_found = [g for g in gold_for_217 if g["gold"] is None]

    print(f"  Found gold deduction: {len(found)}")
    print(f"  No deduction found: {len(not_found)}")

    if found:
        gold_values = [abs(g["gold"]) for g in found]
        gold_counter = Counter(int(round(v)) for v in gold_values)

        print(f"\n  Gold amounts (rounded):")
        for amount, cnt in gold_counter.most_common(20):
            pct = cnt * 100 // len(found)
            bar = '#' * (cnt * 30 // max(gold_counter.values()))
            print(f"    {amount:>6}g: {cnt:>3}x ({pct:>2}%) {bar}")

        print(f"\n  Stats: avg={sum(gold_values)/len(gold_values):.0f}g, "
              f"med={sorted(gold_values)[len(gold_values)//2]:.0f}g, "
              f"min={min(gold_values):.0f}g, max={max(gold_values):.0f}g")

        # Sample details
        print(f"\n  Sample (first 20):")
        for g in found[:20]:
            all_purch = " | ".join(f"{v:.0f}g@{o}" for v, o in g["all_purchases"][:5])
            print(f"    {g['hero']:14s} {g['role']:9s} closest={g['gold']:.0f}g "
                  f"offset={g['offset']:>4}  all=[{all_purch}]")

    # ==========================================================================
    # 2. Stormcrown direct purchase analysis
    # ==========================================================================
    print(f"\n{'='*70}")
    print(f"2. STORMCROWN (ID 7, qty=2) BUYERS - Component check")
    print(f"{'='*70}")
    print(f"  Total Stormcrown buyers: {len(stormcrown_buyers)}")

    if stormcrown_buyers:
        has_sgb = sum(1 for b in stormcrown_buyers if b["has_sgb"])
        has_chrono = sum(1 for b in stormcrown_buyers if b["has_chronograph"])
        has_oak = sum(1 for b in stormcrown_buyers if b["has_oakheart"])
        has_217 = sum(1 for b in stormcrown_buyers if b["has_217"])
        has_hg = sum(1 for b in stormcrown_buyers if b["has_hourglass"])

        print(f"  Has SGB (219):        {has_sgb}/{len(stormcrown_buyers)} ({has_sgb*100//len(stormcrown_buyers)}%)")
        print(f"  Has Chronograph (218): {has_chrono}/{len(stormcrown_buyers)} ({has_chrono*100//len(stormcrown_buyers)}%)")
        print(f"  Has Oakheart (212):    {has_oak}/{len(stormcrown_buyers)} ({has_oak*100//len(stormcrown_buyers)}%)")
        print(f"  Has ID 217:            {has_217}/{len(stormcrown_buyers)} ({has_217*100//len(stormcrown_buyers)}%)")
        print(f"  Has Hourglass (216):   {has_hg}/{len(stormcrown_buyers)} ({has_hg*100//len(stormcrown_buyers)}%)")

        # Check: anyone has Stormcrown but NOT SGB?
        no_sgb = [b for b in stormcrown_buyers if not b["has_sgb"]]
        print(f"\n  Stormcrown WITHOUT SGB: {len(no_sgb)}")
        for b in no_sgb[:10]:
            print(f"    {b['hero']:14s} has_217={b['has_217']} has_oak={b['has_oakheart']} "
                  f"has_chrono={b['has_chronograph']}")

        # Check: anyone has Stormcrown with 217 but without Oakheart?
        has_217_no_oak = [b for b in stormcrown_buyers if b["has_217"] and not b["has_oakheart"]]
        print(f"\n  Stormcrown + 217 but NO Oakheart: {len(has_217_no_oak)}")
        for b in has_217_no_oak[:10]:
            print(f"    {b['hero']:14s} has_sgb={b['has_sgb']}")

    # ==========================================================================
    # 3. Check ALL gold deductions for 217 buyers (not just closest)
    # ==========================================================================
    print(f"\n{'='*70}")
    print(f"3. ALL gold deductions within ±200B of 217 acquire")
    print(f"{'='*70}")

    # Show full deduction context for first 10 217 purchases
    count = 0
    for rp in replays[:15]:
        result = load_replay(rp)
        if not result:
            continue
        players, all_data = result
        acquire_events = scan_acquire_with_positions(all_data, players)

        for ev in acquire_events:
            if ev["item_id"] == 217 and ev["qty"] == 1 and count < 15:
                pinfo = players[ev["eid"]]
                gold_events = find_gold_near_acquire(all_data, ev["pos"], ev["eid"], search_range=200)

                # Also find nearby acquire events for context
                nearby_acquires = []
                for ev2 in acquire_events:
                    if ev2["eid"] == ev["eid"] and abs(ev2["pos"] - ev["pos"]) < 200 and ev2["pos"] != ev["pos"]:
                        name = ITEM_ID_MAP.get(ev2["item_id"], {}).get("name", f"UNK_{ev2['item_id']}")
                        nearby_acquires.append((ev2["pos"] - ev["pos"], ev2["item_id"], name, ev2["qty"]))

                print(f"\n  [{pinfo['hero']:12s}] 217 acquire at byte {ev['pos']}, counter={ev['counter']}")

                # Show nearby acquires (before and after)
                all_nearby = sorted(nearby_acquires, key=lambda x: x[0])
                for off, iid, name, q in all_nearby:
                    marker = ">>>" if off > 0 else "<<<"
                    print(f"    {marker} {off:>+5}B: [{name}] (ID {iid}, qty={q})")

                # Show gold events
                for g in sorted(gold_events, key=lambda x: x["offset"]):
                    action_name = {0x06: "gold", 0x08: "passive", 0x0E: "minion", 0x0F: "minion$"}.get(g["action"], f"0x{g['action']:02X}")
                    sell = " SELL" if g["sell_flag"] == 1 else ""
                    marker = "$$$" if g["action"] == 0x06 and g["value"] < 0 and g["sell_flag"] == 0 else "   "
                    print(f"    {marker} {g['offset']:>+5}B: {g['value']:>+8.0f}g  action={action_name}{sell}")

                count += 1


if __name__ == "__main__":
    main()
