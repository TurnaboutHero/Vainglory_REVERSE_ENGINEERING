#!/usr/bin/env python3
"""
Verify if qty=2 low IDs are actually items (not ability upgrades).
For each player: show qty=1 build + qty=2 IDs, check if qty=2 IDs
fill gaps in expected builds.
"""

import struct
from collections import Counter, defaultdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from vg.core.vgr_parser import VGRParser
from vg.core.vgr_mapping import ITEM_ID_MAP

ITEM_ACQUIRE_HEADER = bytes([0x10, 0x04, 0x3D])
REPLAY_DIR = Path(r"D:\Desktop\My Folder\Game\VG\vg replay")

# Hypothesized item names for low IDs (from previous mapping before qty filter)
LOW_ID_NAMES = {
    0: "Heavy Prism?", 1: "???", 5: "Tyrants Monocle?",
    7: "Stormcrown?", 8: "Weapon Infusion?", 10: "Spellfire?",
    11: "Dragons Eye?", 12: "Spellsword?", 13: "Slumbering Husk?",
    14: "UNIVERSAL (system?)", 15: "SuperScout 2000?",
    16: "Contraption?", 17: "Shiversteel?", 18: "Crystal Infusion?",
    19: "Unknown 19", 20: "Flare?", 21: "Pulseweave?",
    22: "Capacitor Plate?", 23: "Unknown 23", 24: "Blazing Salvo?",
    26: "Warmail?", 27: "Rooks Decree?",
}

def le_to_be(eid_le):
    return struct.unpack('>H', struct.pack('<H', eid_le))[0]


def analyze_match(replay_path):
    """Analyze one match: show qty=1 + qty=2 items per player."""
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
                    "hero": p.get("hero_name", "?"),
                    "team": team,
                }

    frame_dir = replay_path.parent
    frame_name = replay_path.stem.rsplit('.', 1)[0]
    frame_files = sorted(
        frame_dir.glob(f"{frame_name}.*.vgr"),
        key=lambda f: int(f.stem.split('.')[-1]) if f.stem.split('.')[-1].isdigit() else 0
    )
    all_data = b"".join(f.read_bytes() for f in frame_files)

    # Scan ALL acquire events
    qty1_items = defaultdict(set)  # eid -> set of item_ids (qty=1)
    qty2_items = defaultdict(set)  # eid -> set of item_ids (qty=2)
    qty2_counts = defaultdict(Counter)  # eid -> Counter(item_id) for qty=2

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
        item_id = struct.unpack_from("<H", all_data, pos + 10)[0]
        if item_id > 255:
            item_id = item_id & 0xFF

        if qty == 1:
            qty1_items[eid].add(item_id)
        elif qty == 2:
            qty2_items[eid].add(item_id)
            qty2_counts[eid][item_id] += 1

        pos += 3

    return players, qty1_items, qty2_items, qty2_counts


def main():
    replays = sorted([
        vgr for vgr in REPLAY_DIR.rglob("*.0.vgr")
        if "__MACOSX" not in str(vgr)
    ])

    # Analyze first 10 matches in detail
    # Track: for each low ID, which heroes buy it (via qty=2)?
    low_id_heroes = defaultdict(list)  # low_id -> [(hero, name, match)]
    id14_always = True  # Check if 14 is truly universal

    for rp in replays[:20]:
        result = analyze_match(rp)
        if not result:
            continue
        players, qty1_items, qty2_items, qty2_counts = result

        match_short = rp.stem[:30]
        print(f"\n{'='*90}")
        print(f"Match: {match_short}")
        print(f"{'='*90}")

        for eid in sorted(players.keys()):
            p = players[eid]
            name = p["name"][:15]
            hero = p["hero"]
            team = p["team"]

            # qty=1 items (named)
            q1_named = []
            for iid in sorted(qty1_items.get(eid, set())):
                info = ITEM_ID_MAP.get(iid)
                if info:
                    if info["tier"] >= 3:
                        q1_named.append(f"**{info['name']}**")
                    elif info["tier"] >= 2:
                        q1_named.append(info['name'])
                else:
                    q1_named.append(f"UNK_{iid}")

            # qty=2 items
            q2_list = []
            for iid in sorted(qty2_items.get(eid, set())):
                guess = LOW_ID_NAMES.get(iid, f"low_{iid}")
                cnt = qty2_counts[eid][iid]
                q2_list.append(f"{iid}({guess})x{cnt}")
                low_id_heroes[iid].append((hero, name, match_short))

            if 14 not in qty2_items.get(eid, set()):
                id14_always = False

            # Count T3 items from qty=1
            t3_count = sum(1 for iid in qty1_items.get(eid, set())
                          if ITEM_ID_MAP.get(iid, {}).get("tier", 0) >= 3)

            print(f"\n  {team:5s} {name:15s} {hero:12s} (T3 from qty=1: {t3_count})")
            print(f"    qty=1 T2+: {', '.join(q1_named[:8])}")
            print(f"    qty=2:     {', '.join(q2_list)}")

    # Summary: low ID hero distribution (excluding ID 14)
    print(f"\n\n{'='*90}")
    print("LOW ID → HERO DISTRIBUTION (qty=2, 20 replays)")
    print(f"{'='*90}")
    print(f"\nID 14 always present for all players: {id14_always}")

    for lid in sorted(low_id_heroes.keys()):
        if lid == 14:
            continue  # Skip universal ID
        heroes = [h for h, _, _ in low_id_heroes[lid]]
        hero_counts = Counter(heroes)
        total = len(heroes)
        guess = LOW_ID_NAMES.get(lid, "???")
        print(f"\n  ID {lid:>2} ({guess:20s}): {total} buyers")
        for hero, cnt in hero_counts.most_common(10):
            print(f"    {hero:<15s} {cnt:>3}x")


if __name__ == "__main__":
    main()
