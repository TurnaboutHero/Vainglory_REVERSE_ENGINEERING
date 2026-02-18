#!/usr/bin/env python3
"""
Cross-reference truth item data with raw detected item IDs.
For each player in truth data:
  1. Get truth items (names)
  2. Get ALL raw qty==1 item IDs from replay
  3. Find truth items with no matching ID in our mapping
  4. Find raw IDs with no matching truth item
  5. Correlate to discover real item ID mappings
"""

import json
import struct
from collections import Counter, defaultdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from vg.core.vgr_parser import VGRParser
from vg.core.vgr_mapping import ITEM_ID_MAP

ITEM_ACQUIRE_HEADER = bytes([0x10, 0x04, 0x3D])
REPLAY_DIR = Path(r"D:\Desktop\My Folder\Game\VG\vg replay")
TRUTH_PATH = Path(r"D:\Documents\GitHub\VG_REVERSE_ENGINEERING\vg\output\tournament_truth.json")

# Reverse map: item name -> set of known IDs
NAME_TO_IDS = defaultdict(set)
for iid, info in ITEM_ID_MAP.items():
    if iid < 28:
        continue  # Skip low IDs (ability upgrades)
    NAME_TO_IDS[info["name"].lower()].add(iid)

def le_to_be(eid_le: int) -> int:
    return struct.unpack('>H', struct.pack('<H', eid_le))[0]

def get_raw_items(replay_path: Path):
    """Get raw qty==1 item IDs per player from replay."""
    try:
        parser = VGRParser(str(replay_path), detect_heroes=False, auto_truth=False)
        parsed = parser.parse()
    except Exception as e:
        return None, str(e)

    # Get player entity IDs
    players = {}  # name -> eid_be
    eid_to_name = {}
    for team in ["left", "right"]:
        for p in parsed.get("teams", {}).get(team, []):
            eid_le = p.get("entity_id", 0)
            if eid_le:
                eid_be = le_to_be(eid_le)
                name = p.get("name", "?")
                players[name] = eid_be
                eid_to_name[eid_be] = name

    valid_eids = set(eid_to_name.keys())

    # Load all frames
    frame_dir = replay_path.parent
    frame_name = replay_path.stem.rsplit('.', 1)[0]
    frame_files = list(frame_dir.glob(f"{frame_name}.*.vgr"))
    if not frame_files:
        return None, "no frames"

    frame_files.sort(key=lambda f: int(f.stem.split('.')[-1]) if f.stem.split('.')[-1].isdigit() else 0)
    all_data = b"".join(f.read_bytes() for f in frame_files)

    # Scan item acquire events (qty==1 only)
    player_items = defaultdict(set)  # player_name -> set of item_ids
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
        if qty != 1:
            pos += 3
            continue

        item_id = struct.unpack_from("<H", all_data, pos + 10)[0]
        # Normalize high IDs (65505→225, 65519→239)
        if item_id > 255:
            item_id = item_id & 0xFF

        player_name = eid_to_name[eid]
        player_items[player_name].add(item_id)
        pos += 3

    return dict(player_items), None


def main():
    # Load truth data
    with open(TRUTH_PATH, 'r', encoding='utf-8') as f:
        truth_data = json.load(f)

    # Find replay files
    replay_map = {}
    for vgr in REPLAY_DIR.rglob("*.0.vgr"):
        if "__MACOSX" in str(vgr):
            continue
        name = vgr.stem.rsplit('.', 1)[0]
        replay_map[name] = vgr

    # Track unmapped items and orphan IDs
    # truth_item -> Counter(raw_ids present when this truth item is present)
    truth_item_to_raw_ids = defaultdict(Counter)
    # raw_id -> Counter(truth_items present when this raw_id is present)
    raw_id_to_truth_items = defaultdict(Counter)
    # Count of times each truth item appears
    truth_item_count = Counter()
    # Count of times each raw_id appears
    raw_id_count = Counter()

    matches_processed = 0
    for match in truth_data.get("matches", []):
        replay_name = match.get("replay_name", "")
        if replay_name not in replay_map:
            continue

        player_items, err = get_raw_items(replay_map[replay_name])
        if err or not player_items:
            continue

        matches_processed += 1
        truth_players = match.get("players", {})

        for player_name, truth_info in truth_players.items():
            truth_items = set()
            for item_name in truth_info.get("items", []):
                # Normalize truth item name
                norm = item_name.strip()
                truth_items.add(norm)

            raw_ids = player_items.get(player_name, set())

            # Map known raw IDs to truth names
            mapped_names = set()
            mapped_ids = set()
            for rid in raw_ids:
                info = ITEM_ID_MAP.get(rid)
                if info and rid >= 28:  # Only 200+ range
                    mapped_names.add(info["name"])
                    mapped_ids.add(rid)

            # Truth items NOT matched by any mapped ID
            unmatched_truth = truth_items - mapped_names
            # Raw IDs NOT matched to any truth item
            unmatched_ids = raw_ids - mapped_ids

            # For each unmatched truth item, record which unmatched IDs are present
            for ti in unmatched_truth:
                truth_item_count[ti] += 1
                for rid in unmatched_ids:
                    truth_item_to_raw_ids[ti][rid] += 1

            # For each unmatched ID, record which unmatched truth items are present
            for rid in unmatched_ids:
                raw_id_count[rid] += 1
                for ti in unmatched_truth:
                    raw_id_to_truth_items[rid][ti] += 1

    print(f"Processed {matches_processed} truth matches")
    print()

    # ========== Report: Truth items with no mapped ID ==========
    print(f"{'='*80}")
    print(f"TRUTH ITEMS NOT FOUND IN MAPPING (appear in truth but no mapped ID):")
    print(f"{'='*80}")
    for item, count in sorted(truth_item_count.items(), key=lambda x: -x[1]):
        print(f"\n  '{item}' ({count} players)")
        top_ids = truth_item_to_raw_ids[item].most_common(10)
        for rid, co_count in top_ids:
            pct = co_count / count * 100
            id_info = ITEM_ID_MAP.get(rid, {}).get("name", "UNMAPPED")
            print(f"    ID {rid:>5} co-occurs {co_count}/{count} ({pct:.0f}%) - currently: {id_info}")

    # ========== Report: Raw IDs with no truth match ==========
    print(f"\n{'='*80}")
    print(f"RAW IDs NOT MATCHED TO TRUTH (appear in replay but no truth item):")
    print(f"{'='*80}")
    for rid, count in sorted(raw_id_count.items(), key=lambda x: -x[1]):
        print(f"\n  ID {rid} ({count} players)")
        top_items = raw_id_to_truth_items[rid].most_common(10)
        for item, co_count in top_items:
            pct = co_count / count * 100
            print(f"    '{item}' co-occurs {co_count}/{count} ({pct:.0f}%)")


if __name__ == "__main__":
    main()
