#!/usr/bin/env python3
"""
Hunt for the 14 missing items by:
1. Scanning ALL qty values in [10 04 3D] (not just 1 and 2)
2. Scanning [10 04 4B] (item equip header) for additional item data
3. Checking if item IDs appear in other event types
"""

import struct
from collections import Counter, defaultdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from vg.core.vgr_parser import VGRParser
from vg.core.vgr_mapping import ITEM_ID_MAP

ITEM_ACQUIRE_HEADER = bytes([0x10, 0x04, 0x3D])
ITEM_EQUIP_HEADER = bytes([0x10, 0x04, 0x4B])
REPLAY_DIR = Path(r"D:\Desktop\My Folder\Game\VG\vg replay")


def le_to_be(eid_le):
    return struct.unpack('>H', struct.pack('<H', eid_le))[0]


def get_player_eids(replay_path):
    """Get player entity IDs (BE) from replay."""
    try:
        parser = VGRParser(str(replay_path), detect_heroes=False, auto_truth=False)
        parsed = parser.parse()
    except:
        return set(), {}

    valid_eids = set()
    eid_to_name = {}
    for team in ["left", "right"]:
        for p in parsed.get("teams", {}).get(team, []):
            eid_le = p.get("entity_id", 0)
            if eid_le:
                eid_be = le_to_be(eid_le)
                valid_eids.add(eid_be)
                eid_to_name[eid_be] = (p.get("name", "?"), p.get("hero_name", "?"))
    return valid_eids, eid_to_name


def load_all_data(replay_path):
    """Load all frames into single bytes."""
    frame_dir = replay_path.parent
    frame_name = replay_path.stem.rsplit('.', 1)[0]
    frame_files = sorted(
        frame_dir.glob(f"{frame_name}.*.vgr"),
        key=lambda f: int(f.stem.split('.')[-1]) if f.stem.split('.')[-1].isdigit() else 0
    )
    return b"".join(f.read_bytes() for f in frame_files)


def scan_acquire_all_qty(all_data, valid_eids):
    """Scan [10 04 3D] for ALL qty values, not just 1."""
    qty_id_map = defaultdict(Counter)  # qty -> Counter(item_id)
    qty_count = Counter()  # qty -> total count

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
        if eid not in valid_eids:
            pos += 1
            continue

        qty = all_data[pos + 9]
        item_id = struct.unpack_from("<H", all_data, pos + 10)[0]
        if item_id > 255:
            item_id = item_id & 0xFF

        qty_id_map[qty][item_id] += 1
        qty_count[qty] += 1
        pos += 3

    return qty_count, qty_id_map


def scan_equip_header(all_data, valid_eids):
    """Scan [10 04 4B] for item equip events and dump structure."""
    events = []
    pos = 0
    while True:
        pos = all_data.find(ITEM_EQUIP_HEADER, pos)
        if pos == -1:
            break
        if pos + 20 > len(all_data):
            pos += 1
            continue
        if all_data[pos + 3:pos + 5] != b'\x00\x00':
            pos += 1
            continue

        eid = struct.unpack_from(">H", all_data, pos + 5)[0]
        if eid not in valid_eids:
            pos += 1
            continue

        # Dump nearby bytes for structure analysis
        raw = all_data[pos:pos+24]
        events.append((eid, raw))
        pos += 3

    return events


def main():
    replays = sorted([
        vgr for vgr in REPLAY_DIR.rglob("*.0.vgr")
        if "__MACOSX" not in str(vgr)
    ])

    # Use first 5 replays for detailed analysis
    print("=" * 80)
    print("PART 1: ALL qty values in [10 04 3D] acquire events")
    print("=" * 80)

    global_qty_count = Counter()
    global_qty_ids = defaultdict(Counter)

    for rp in replays[:10]:
        valid_eids, _ = get_player_eids(rp)
        if not valid_eids:
            continue
        all_data = load_all_data(rp)
        qty_count, qty_id_map = scan_acquire_all_qty(all_data, valid_eids)
        for qty, cnt in qty_count.items():
            global_qty_count[qty] += cnt
        for qty, id_counter in qty_id_map.items():
            for iid, cnt in id_counter.items():
                global_qty_ids[qty][iid] += cnt

    print(f"\nQty value distribution (10 replays):")
    for qty, cnt in sorted(global_qty_count.items()):
        print(f"  qty={qty}: {cnt} events")
        # Show unique IDs for this qty
        ids = global_qty_ids[qty]
        print(f"    IDs: {sorted(ids.keys())}")
        if qty not in (1, 2):
            print(f"    Details:")
            for iid, c in ids.most_common(20):
                mapped = ITEM_ID_MAP.get(iid, {}).get("name", "UNMAPPED")
                print(f"      ID {iid}: {c}x - {mapped}")

    # PART 2: Scan [10 04 4B] equip header
    print(f"\n{'='*80}")
    print("PART 2: [10 04 4B] equip header events")
    print("=" * 80)

    rp = replays[0]
    valid_eids, eid_names = get_player_eids(rp)
    all_data = load_all_data(rp)
    equip_events = scan_equip_header(all_data, valid_eids)

    print(f"\nTotal [10 04 4B] events: {len(equip_events)}")
    if equip_events:
        # Group by EID
        by_eid = defaultdict(list)
        for eid, raw in equip_events:
            by_eid[eid].append(raw)

        print(f"Events per player:")
        for eid in sorted(by_eid.keys()):
            name, hero = eid_names.get(eid, ("?", "?"))
            print(f"  {name} ({hero}): {len(by_eid[eid])} events")

        # Dump first few events to understand structure
        print(f"\nFirst 10 events (hex dump):")
        for eid, raw in equip_events[:10]:
            name, hero = eid_names.get(eid, ("?", "?"))
            hex_str = " ".join(f"{b:02X}" for b in raw)
            # Try to extract item_id at same offset as acquire
            if len(raw) >= 12:
                qty = raw[9]
                iid = struct.unpack_from("<H", raw, 10)[0]
                if iid > 255:
                    iid = iid & 0xFF
                mapped = ITEM_ID_MAP.get(iid, {}).get("name", f"UNK_{iid}")
                print(f"  [{name:12s}] qty={qty} iid={iid:>3} ({mapped:20s}) | {hex_str}")
            else:
                print(f"  [{name:12s}] {hex_str}")

    # PART 3: Look for items in qty=2 that could be T3 items
    print(f"\n{'='*80}")
    print("PART 3: qty=2 ID distribution (ability upgrades OR item mechanism?)")
    print("=" * 80)

    qty2_per_player = defaultdict(Counter)  # (name, hero) -> Counter(item_id)

    for rp in replays[:5]:
        valid_eids, eid_names = get_player_eids(rp)
        if not valid_eids:
            continue
        all_data = load_all_data(rp)

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
            if eid not in valid_eids:
                pos += 1
                continue

            qty = all_data[pos + 9]
            if qty == 2:
                item_id = struct.unpack_from("<H", all_data, pos + 10)[0]
                if item_id > 255:
                    item_id = item_id & 0xFF
                key = eid_names.get(eid, ("?", "?"))
                qty2_per_player[key][item_id] += 1
            pos += 3

    # Show qty=2 per player - if these are ability upgrades, each player should have similar counts
    print(f"\nqty=2 events per player (5 replays):")
    for (name, hero), ids in sorted(qty2_per_player.items(), key=lambda x: x[0][0])[:15]:
        total = sum(ids.values())
        unique = len(ids)
        id_list = sorted(ids.keys())
        print(f"  {name[:15]:15s} {hero:12s} total={total:>3} unique_ids={unique:>2} IDs={id_list}")


if __name__ == "__main__":
    main()
