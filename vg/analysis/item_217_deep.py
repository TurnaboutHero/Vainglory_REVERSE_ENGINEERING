#!/usr/bin/env python3
"""
Deep analysis of item ID 217 - identity investigation.
Focus: jungler vs non-jungler split, purchase timing, gold cost inference.
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

# Hero role lookup
HERO_ROLES = {info["name"]: info["role"] for info in HERO_ID_MAP.values()}

# Jungler heroes in 5v5: Warriors + some Assassins typically jungle
# But "jungler" is a position, not just a role. We'll use SGB purchase as jungler indicator.


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
                    "team": team,
                    "role": HERO_ROLES.get(p.get("hero_name", ""), "?"),
                }

    stem_base = replay_path.stem.rsplit('.', 1)[0]
    frame_files = sorted(
        replay_path.parent.glob(f"{stem_base}.*.vgr"),
        key=lambda f: int(f.stem.split('.')[-1]) if f.stem.split('.')[-1].isdigit() else 0
    )
    all_data = b"".join(f.read_bytes() for f in frame_files)
    return players, all_data


def scan_items(players, all_data):
    """Get all item acquire events per player, sorted by timestamp."""
    events = defaultdict(list)  # eid -> [(item_id, qty, ts)]
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

        ts = 0.0
        if pos + 20 <= len(all_data):
            ts_raw = struct.unpack_from(">f", all_data, pos + 16)[0]
            if 0 < ts_raw < 6000:
                ts = ts_raw

        events[eid].append((item_id, qty, ts))
        pos += 3

    # Sort by timestamp
    for eid in events:
        events[eid].sort(key=lambda x: x[2])

    return events


def scan_gold_spending(players, all_data, target_eid, target_ts, window=5.0):
    """Find gold spending events (action=0x06, negative value) near a timestamp."""
    gold_events = []
    pos = 0
    while True:
        pos = all_data.find(CREDIT_HEADER, pos)
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

        if action == 0x06 and value < 0:
            # This is a gold deduction (purchase)
            # Find closest timestamp - check nearby [10 04 3D] for ts context
            gold_events.append((value, action, pos))

        pos += 3

    return gold_events


def main():
    replays = sorted([
        vgr for vgr in REPLAY_DIR.rglob("*.0.vgr")
        if "__MACOSX" not in str(vgr)
    ])

    print("=" * 80)
    print("ID 217 DEEP ANALYSIS - Jungler vs Non-jungler, Timing, Build Context")
    print("=" * 80)

    # Collect all ID 217 buyers
    buyers_217 = []  # list of dicts
    all_build_orders = []  # (hero, role, is_jungler, build_list)

    for rp in replays:
        result = load_replay(rp)
        if not result:
            continue
        players, all_data = result
        events = scan_items(players, all_data)

        for eid, ev_list in events.items():
            pinfo = players[eid]
            hero = pinfo["hero"]
            role = pinfo["role"]

            # Determine if this player is a jungler by SGB purchase
            has_sgb = any(iid == 219 for iid, q, t in ev_list)
            has_217 = any(iid == 217 and q == 1 for iid, q, t in ev_list)

            if has_217:
                # Get 217 purchase details
                ts_217_list = [t for iid, q, t in ev_list if iid == 217 and q == 1]
                ts_217 = ts_217_list[0] if ts_217_list else 0
                count_217 = len(ts_217_list)

                # Get full build order (first 10 items by time)
                build = []
                for iid, q, t in ev_list[:12]:
                    name = ITEM_ID_MAP.get(iid, {}).get("name", f"UNK_{iid}")
                    build.append(f"{name}@{t:.0f}s")

                # Get SGB timing if present
                sgb_ts = None
                for iid, q, t in ev_list:
                    if iid == 219:
                        sgb_ts = t
                        break

                # Position of 217 in build order
                pos_217 = None
                for i, (iid, q, t) in enumerate(ev_list):
                    if iid == 217 and q == 1:
                        pos_217 = i + 1
                        break

                buyers_217.append({
                    "match": rp.stem[:25],
                    "hero": hero,
                    "role": role,
                    "is_jungler": has_sgb,
                    "ts_217": ts_217,
                    "count_217": count_217,
                    "sgb_ts": sgb_ts,
                    "pos_217": pos_217,
                    "build": build[:10],
                    "all_ids": set(iid for iid, q, t in ev_list),
                })

    total = len(buyers_217)
    print(f"\nTotal ID 217 buyers: {total}")

    # ==========================================================================
    # 1. Jungler vs Non-jungler split
    # ==========================================================================
    junglers = [b for b in buyers_217 if b["is_jungler"]]
    non_junglers = [b for b in buyers_217 if not b["is_jungler"]]

    print(f"\n{'='*70}")
    print(f"1. JUNGLER (has SGB) vs NON-JUNGLER split")
    print(f"{'='*70}")
    print(f"  Junglers (has SGB 219): {len(junglers)} ({len(junglers)*100//total}%)")
    print(f"  Non-junglers (no SGB): {len(non_junglers)} ({len(non_junglers)*100//total}%)")

    for label, group in [("JUNGLERS", junglers), ("NON-JUNGLERS", non_junglers)]:
        if not group:
            continue
        print(f"\n  --- {label} ({len(group)} buyers) ---")

        # Hero distribution
        hero_counts = Counter(b["hero"] for b in group)
        print(f"  Heroes: {dict(hero_counts.most_common(10))}")

        # Role distribution
        role_counts = Counter(b["role"] for b in group)
        print(f"  Roles: {dict(role_counts.items())}")

        # Timing
        ts_list = [b["ts_217"] for b in group if b["ts_217"] > 0]
        if ts_list:
            ts_list.sort()
            avg_ts = sum(ts_list) / len(ts_list)
            med_ts = ts_list[len(ts_list) // 2]
            print(f"  Timing: avg={avg_ts:.0f}s, med={med_ts:.0f}s, min={min(ts_list):.0f}s, max={max(ts_list):.0f}s")

        # Build position
        pos_list = [b["pos_217"] for b in group if b["pos_217"]]
        if pos_list:
            avg_pos = sum(pos_list) / len(pos_list)
            print(f"  Build position: avg={avg_pos:.1f}, mode={Counter(pos_list).most_common(3)}")

        # Purchase count per player
        count_dist = Counter(b["count_217"] for b in group)
        print(f"  Purchases per player: {dict(sorted(count_dist.items()))}")

    # ==========================================================================
    # 2. SGB timing relative to 217
    # ==========================================================================
    print(f"\n{'='*70}")
    print(f"2. TIMING: ID 217 vs SGB (219) for junglers")
    print(f"{'='*70}")

    for b in junglers[:15]:
        sgb_rel = f"SGB@{b['sgb_ts']:.0f}s" if b['sgb_ts'] else "no SGB"
        order = "217 BEFORE SGB" if (b['sgb_ts'] and b['ts_217'] < b['sgb_ts']) else "217 AFTER SGB"
        dt = abs(b['ts_217'] - b['sgb_ts']) if b['sgb_ts'] else 0
        print(f"  {b['hero']:14s} {b['role']:9s} 217@{b['ts_217']:>6.0f}s  {sgb_rel:>14s}  {order}  dt={dt:.0f}s")

    before_count = sum(1 for b in junglers if b['sgb_ts'] and b['ts_217'] < b['sgb_ts'])
    after_count = sum(1 for b in junglers if b['sgb_ts'] and b['ts_217'] >= b['sgb_ts'])
    print(f"\n  Summary: 217 before SGB: {before_count}, 217 after SGB: {after_count}")

    # ==========================================================================
    # 3. Non-jungler build context (what do they build 217 into?)
    # ==========================================================================
    print(f"\n{'='*70}")
    print(f"3. NON-JUNGLER BUILDS (what do they buy 217 with?)")
    print(f"{'='*70}")

    # Co-items for non-junglers
    co_items = Counter()
    for b in non_junglers:
        for iid in b["all_ids"]:
            if iid != 217:
                co_items[iid] += 1

    print(f"\n  Top co-items for non-junglers ({len(non_junglers)} buyers):")
    for iid, cnt in co_items.most_common(20):
        name = ITEM_ID_MAP.get(iid, {}).get("name", f"UNK_{iid}")
        tier = ITEM_ID_MAP.get(iid, {}).get("tier", "?")
        pct = cnt * 100 // len(non_junglers) if non_junglers else 0
        print(f"    ID {iid:>3} {name:<28} T{tier}  {cnt:>3}/{len(non_junglers)} ({pct}%)")

    # ==========================================================================
    # 4. Sample builds (first 5 items for diverse players)
    # ==========================================================================
    print(f"\n{'='*70}")
    print(f"4. SAMPLE BUILD ORDERS")
    print(f"{'='*70}")

    print(f"\n  --- JUNGLER BUILDS (first 10) ---")
    for b in junglers[:10]:
        build_str = " -> ".join(b["build"][:7])
        print(f"  {b['hero']:14s} {b['role']:9s} | {build_str}")

    print(f"\n  --- NON-JUNGLER BUILDS (first 15) ---")
    for b in non_junglers[:15]:
        build_str = " -> ".join(b["build"][:7])
        print(f"  {b['hero']:14s} {b['role']:9s} | {build_str}")

    # ==========================================================================
    # 5. What items does 217 get replaced by? (items bought RIGHT AFTER 217)
    # ==========================================================================
    print(f"\n{'='*70}")
    print(f"5. ITEMS BOUGHT IMMEDIATELY AFTER 217")
    print(f"{'='*70}")

    next_item_counter = Counter()
    for b in buyers_217:
        # Find 217's position, then get next item
        if b["pos_217"] and b["pos_217"] < len(b["build"]):
            # Parse the next build entry
            next_entry = b["build"][b["pos_217"]]  # 0-indexed, pos_217 is 1-indexed
            next_name = next_entry.split("@")[0]
            next_item_counter[next_name] += 1

    print(f"\n  Item immediately after 217:")
    for name, cnt in next_item_counter.most_common(15):
        pct = cnt * 100 // total
        print(f"    {name:<28} {cnt:>3} ({pct}%)")

    # ==========================================================================
    # 6. Check: do players buy 217 MULTIPLE times?
    # ==========================================================================
    print(f"\n{'='*70}")
    print(f"6. REPEAT PURCHASE ANALYSIS")
    print(f"{'='*70}")
    multi_buyers = [b for b in buyers_217 if b["count_217"] > 1]
    print(f"  Single purchase: {total - len(multi_buyers)}")
    print(f"  Multiple purchases: {len(multi_buyers)}")
    if multi_buyers:
        for b in multi_buyers[:10]:
            print(f"    {b['hero']:14s} x{b['count_217']} purchases")

    # ==========================================================================
    # 7. Cross-check: players who DON'T buy 217 - what do they have instead?
    # ==========================================================================
    print(f"\n{'='*70}")
    print(f"7. IDENTITY HYPOTHESIS")
    print(f"{'='*70}")

    # Compile stats
    junglers_pct = len(junglers) * 100 // total if total else 0
    all_roles = Counter(b["role"] for b in buyers_217)
    all_ts = sorted(b["ts_217"] for b in buyers_217 if b["ts_217"] > 0)
    med_ts = all_ts[len(all_ts)//2] if all_ts else 0

    print(f"""
  Summary:
    - {total} buyers across all roles
    - {junglers_pct}% are junglers (SGB buyers)
    - Roles: {dict(all_roles.items())}
    - Median timing: {med_ts:.0f}s
    - Almost always single-purchase: {total - len(multi_buyers)}/{total}
    - Bought early in build order

  Remaining unmapped items (candidates):
    - Minion's Foot (여우발): Weapon T1, 300g. User said no relation to SGB
    - Eclipse Prism (일식 프리즘): Crystal T2, 650g
    - Void Battery (공허의 배터리): Crystal T2, 700g
    - Protector Contract (수호자의 계약서): Support T2, 600g
    - Ironguard Contract (경비대의 계약서): Old jungler item
    - Dragonblood Contract (용의 피 계약서): Aggressive support
    - Scout Cam (정찰 부표): Vision consumable
    - Teleport Boots (순간이동 신발): T3 boots
    - Minion Candy (미니언 사탕): Consumable
""")


if __name__ == "__main__":
    main()
