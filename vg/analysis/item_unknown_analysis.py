#!/usr/bin/env python3
"""
Analyze unknown/unmapped item IDs by examining buyer profiles.
For each unknown ID: who buys it, what hero, what other items, buy count, timing.
"""

import struct
from collections import Counter, defaultdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from vg.core.vgr_parser import VGRParser
from vg.core.vgr_mapping import ITEM_ID_MAP, BINARY_HERO_ID_MAP

ITEM_ACQUIRE_HEADER = bytes([0x10, 0x04, 0x3D])
REPLAY_DIR = Path(r"D:\Desktop\My Folder\Game\VG\vg replay")

# IDs to investigate
TARGET_IDS = {201, 207, 217, 225, 228, 233, 239, 252}

def le_to_be(eid_le):
    return struct.unpack('>H', struct.pack('<H', eid_le))[0]

def scan_replay(replay_path):
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

    # Scan all qty==1 items
    player_items = defaultdict(list)  # eid -> [(item_id, ts)]
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
        if qty != 1:
            pos += 3
            continue

        item_id = struct.unpack_from("<H", all_data, pos + 10)[0]
        if item_id > 255:
            item_id = item_id & 0xFF

        ts = 0
        if pos + 21 <= len(all_data):
            ts = struct.unpack_from(">f", all_data, pos + 17)[0]
            if ts < 0 or ts > 5000:
                ts = 0

        player_items[eid].append((item_id, ts))
        pos += 3

    return players, player_items, parsed.get("replay_name", replay_path.stem)


def main():
    replays = sorted([
        vgr for vgr in REPLAY_DIR.rglob("*.0.vgr")
        if "__MACOSX" not in str(vgr)
    ])
    print(f"Scanning {len(replays)} replays...\n")

    # Collect data per target ID
    # target_id -> list of {match, player, hero, team, count, timestamps, co_items}
    id_data = defaultdict(list)

    for rp in replays:
        result = scan_replay(rp)
        if not result:
            continue
        players, player_items, match_name = result

        for eid, items_list in player_items.items():
            pinfo = players.get(eid, {})
            hero = pinfo.get("hero", "?")
            name = pinfo.get("name", "?")
            team = pinfo.get("team", "?")

            # Get all item IDs and target IDs for this player
            all_ids = set(iid for iid, _ in items_list)
            target_in_build = all_ids & TARGET_IDS

            for tid in target_in_build:
                target_items = [(iid, ts) for iid, ts in items_list if iid == tid]
                co_items = all_ids - {tid}
                co_named = []
                for cid in sorted(co_items):
                    info = ITEM_ID_MAP.get(cid)
                    if info and cid >= 28:
                        co_named.append(f"{info['name']}({cid})")
                    elif cid in TARGET_IDS:
                        co_named.append(f"???({cid})")
                    else:
                        co_named.append(f"UNK({cid})")

                id_data[tid].append({
                    "match": match_name,
                    "player": name,
                    "hero": hero,
                    "team": team,
                    "count": len(target_items),
                    "timestamps": [round(ts, 1) for _, ts in target_items],
                    "co_items": co_named,
                    "co_ids": co_items,
                })

    # Report per target ID
    for tid in sorted(TARGET_IDS):
        entries = id_data.get(tid, [])
        current_name = ITEM_ID_MAP.get(tid, {}).get("name", "UNMAPPED")
        print(f"{'='*80}")
        print(f"ID {tid} - Currently: '{current_name}' - {len(entries)} buyers across replays")
        print(f"{'='*80}")

        if not entries:
            print("  (No buyers found)")
            continue

        # Hero distribution
        hero_counts = Counter(e["hero"] for e in entries)
        print(f"\n  Hero distribution ({len(hero_counts)} heroes):")
        for hero, cnt in hero_counts.most_common(10):
            print(f"    {hero:<15} {cnt:>3}x")

        # Buy count distribution
        count_dist = Counter(e["count"] for e in entries)
        print(f"\n  Buy count distribution:")
        for cnt, freq in sorted(count_dist.items()):
            print(f"    qty={cnt}: {freq} players")

        # Timing analysis
        all_ts = [ts for e in entries for ts in e["timestamps"] if ts > 0]
        if all_ts:
            avg_ts = sum(all_ts) / len(all_ts)
            min_ts = min(all_ts)
            max_ts = max(all_ts)
            print(f"\n  Timing: avg={avg_ts:.0f}s, min={min_ts:.0f}s, max={max_ts:.0f}s")

        # Co-occurring items (most common)
        co_counter = Counter()
        for e in entries:
            for cid in e["co_ids"]:
                co_counter[cid] += 1
        print(f"\n  Most common co-items (of {len(entries)} buyers):")
        for cid, cnt in co_counter.most_common(15):
            info = ITEM_ID_MAP.get(cid, {})
            name = info.get("name", "UNMAPPED") if cid >= 28 else f"LOW_{cid}"
            pct = cnt / len(entries) * 100
            print(f"    {cid:>5} {name:<25} {cnt:>3}/{len(entries)} ({pct:.0f}%)")

        # Sample builds (first 5)
        print(f"\n  Sample builds:")
        for e in entries[:5]:
            ts_str = ",".join(f"{t:.0f}s" for t in e["timestamps"])
            print(f"    {e['match'][:20]:20s} {e['player'][:12]:12s} {e['hero']:<12s} "
                  f"x{e['count']} @[{ts_str}]")
            # Show T3 items only
            t3_items = [ci for ci in e["co_items"]
                       if any(ITEM_ID_MAP.get(int(ci.split('(')[1].rstrip(')')), {}).get("tier", 0) >= 3
                              for _ in [0] if ci.split('(')[1].rstrip(')').isdigit())]
            if t3_items:
                print(f"      T3: {', '.join(t3_items[:6])}")

        print()


if __name__ == "__main__":
    main()
