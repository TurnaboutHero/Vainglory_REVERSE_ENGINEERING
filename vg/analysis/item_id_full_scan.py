#!/usr/bin/env python3
"""
Full scan of ALL replays for item acquire events [10 04 3D] with qty==1.
Finds all item IDs that actually appear as purchases (not ability upgrades).
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

def le_to_be(eid_le: int) -> int:
    return struct.unpack('>H', struct.pack('<H', eid_le))[0]

def scan_replay(replay_path: Path):
    """Scan a single replay for all qty==1 item acquire events."""
    # Parse to get player entity IDs
    try:
        parser = VGRParser(str(replay_path), detect_heroes=False, auto_truth=False)
        parsed = parser.parse()
    except Exception as e:
        return None, str(e)

    # Get player entity IDs (BE)
    valid_eids = set()
    eid_to_name = {}
    for team in ["left", "right"]:
        for p in parsed.get("teams", {}).get(team, []):
            eid_le = p.get("entity_id", 0)
            if eid_le:
                eid_be = le_to_be(eid_le)
                valid_eids.add(eid_be)
                eid_to_name[eid_be] = p.get("name", "?")

    # Load all frames
    frame_dir = replay_path.parent
    frame_name = replay_path.stem.rsplit('.', 1)[0]
    frame_files = list(frame_dir.glob(f"{frame_name}.*.vgr"))
    if not frame_files:
        return None, "no frames"

    frame_files.sort(key=lambda f: int(f.stem.split('.')[-1]) if f.stem.split('.')[-1].isdigit() else 0)
    all_data = b""
    for f in frame_files:
        all_data += f.read_bytes()

    # Scan for item acquire events
    items_per_player = defaultdict(Counter)  # eid -> Counter(item_id)
    all_item_ids = Counter()  # item_id -> total count

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
        items_per_player[eid][item_id] += 1
        all_item_ids[item_id] += 1

        pos += 3

    return {
        "replay": replay_path.name,
        "players": {eid_to_name.get(eid, f"eid_{eid}"): dict(counts) for eid, counts in items_per_player.items()},
        "all_ids": dict(all_item_ids),
    }, None


def main():
    # Find all replays
    replays = []
    for vgr in REPLAY_DIR.rglob("*.0.vgr"):
        if "__MACOSX" in str(vgr):
            continue
        replays.append(vgr)

    print(f"Found {len(replays)} replays")

    # Scan all
    global_item_counts = Counter()  # item_id -> total purchases across all replays
    global_item_buyers = defaultdict(int)  # item_id -> number of unique players who bought it
    global_item_matches = defaultdict(int)  # item_id -> number of matches where it appears

    errors = 0
    for i, rp in enumerate(sorted(replays)):
        result, err = scan_replay(rp)
        if err:
            errors += 1
            continue

        match_ids = set()
        for player_name, item_counts in result["players"].items():
            for item_id, count in item_counts.items():
                global_item_counts[item_id] += count
                global_item_buyers[item_id] += 1
                match_ids.add(item_id)

        for item_id in match_ids:
            global_item_matches[item_id] += 1

        if (i + 1) % 10 == 0:
            print(f"  Scanned {i+1}/{len(replays)}...")

    print(f"\nScanned {len(replays) - errors}/{len(replays)} replays successfully")
    print(f"\n{'='*80}")
    print(f"ALL qty==1 item IDs found (sorted by buyer count):")
    print(f"{'='*80}")
    print(f"{'ID':>6} {'Buyers':>7} {'Matches':>8} {'Purchases':>10} {'Mapped?':>8} {'Name':<30}")
    print(f"{'-'*6} {'-'*7} {'-'*8} {'-'*10} {'-'*8} {'-'*30}")

    for item_id, _ in sorted(global_item_buyers.items(), key=lambda x: -x[1]):
        mapped = item_id in ITEM_ID_MAP
        name = ITEM_ID_MAP[item_id]["name"] if mapped else "??? UNMAPPED ???"
        flag = "YES" if mapped else "NO"
        print(f"{item_id:>6} {global_item_buyers[item_id]:>7} {global_item_matches[item_id]:>8} "
              f"{global_item_counts[item_id]:>10} {flag:>8} {name:<30}")

    # Summary of unmapped
    unmapped = {iid for iid in global_item_buyers if iid not in ITEM_ID_MAP}
    if unmapped:
        print(f"\n{'='*80}")
        print(f"UNMAPPED IDs ({len(unmapped)}):")
        print(f"{'='*80}")
        for iid in sorted(unmapped):
            print(f"  ID {iid}: {global_item_buyers[iid]} buyers, {global_item_matches[iid]} matches, {global_item_counts[iid]} purchases")

    # Check low IDs that appear with qty==1
    low_ids = {iid for iid in global_item_buyers if iid < 28}
    if low_ids:
        print(f"\n{'='*80}")
        print(f"LOW IDs (0-27) with qty==1 ({len(low_ids)}):")
        print(f"{'='*80}")
        for iid in sorted(low_ids):
            name = ITEM_ID_MAP.get(iid, {}).get("name", "???")
            print(f"  ID {iid}: {global_item_buyers[iid]} buyers, {global_item_counts[iid]} purchases - currently mapped as '{name}'")
    else:
        print(f"\nNO low IDs (0-27) found with qty==1 - confirming they are ALL ability upgrades")

    # IDs > 255
    high_ids = {iid for iid in global_item_buyers if iid > 255}
    if high_ids:
        print(f"\n{'='*80}")
        print(f"HIGH IDs (>255) with qty==1 ({len(high_ids)}):")
        print(f"{'='*80}")
        for iid in sorted(high_ids):
            # Check if it might be a LE/BE encoding artifact
            lo = iid & 0xFF
            hi = (iid >> 8) & 0xFF
            swapped = (lo << 8) | hi
            note = ""
            if swapped in ITEM_ID_MAP:
                note = f" (byte-swapped = {swapped} = {ITEM_ID_MAP[swapped]['name']})"
            print(f"  ID {iid} (0x{iid:04X}): {global_item_buyers[iid]} buyers, "
                  f"{global_item_counts[iid]} purchases{note}")


if __name__ == "__main__":
    main()
