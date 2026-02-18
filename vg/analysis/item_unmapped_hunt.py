#!/usr/bin/env python3
"""
item_unmapped_hunt.py - Comprehensive scan for unmapped item IDs.

Scans ALL 56 replays for:
  - qty=2 IDs in 0-27 range (especially 3, 19, 24 and any new ones)
  - qty=1 IDs in 200-255 range (especially 217, 233, 239 and any new ones)

For each unmapped ID: buyer count, hero distribution, role pattern,
timing, co-purchased items, purchase frequency per player.

Output: detailed per-ID report + best-guess identity.
"""

import struct
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from vg.core.vgr_parser import VGRParser
from vg.core.vgr_mapping import ITEM_ID_MAP, BINARY_HERO_ID_MAP, HERO_ID_MAP

ITEM_ACQUIRE_HEADER = bytes([0x10, 0x04, 0x3D])
REPLAY_DIR = Path(r"D:\Desktop\My Folder\Game\VG\vg replay")

# Currently mapped IDs (skip these in "new discovery" scan)
MAPPED_IDS_QTY2 = set(ITEM_ID_MAP.keys()) & set(range(0, 28))  # 0-27
MAPPED_IDS_QTY1 = set(ITEM_ID_MAP.keys()) & set(range(200, 256))  # 200-255

# System/starter IDs to ignore
STARTER_IDS_QTY2 = {14}  # universal system event

# Hero role lookup from HERO_ID_MAP
HERO_ROLES = {info["name"]: info["role"] for info in HERO_ID_MAP.values()}
CAPTAIN_HEROES = {name for name, role in HERO_ROLES.items() if role == "Captain"}
WARRIOR_HEROES = {name for name, role in HERO_ROLES.items() if role == "Warrior"}
MAGE_HEROES    = {name for name, role in HERO_ROLES.items() if role == "Mage"}
SNIPER_HEROES  = {name for name, role in HERO_ROLES.items() if role == "Sniper"}
ASSASSIN_HEROES= {name for name, role in HERO_ROLES.items() if role == "Assassin"}


def le_to_be(eid_le):
    return struct.unpack('>H', struct.pack('<H', eid_le))[0]


def hero_role(hero_name):
    return HERO_ROLES.get(hero_name, "?")


def load_replay_data(replay_path):
    """Load player info + all frame bytes for a replay."""
    try:
        parser = VGRParser(str(replay_path), detect_heroes=False, auto_truth=False)
        parsed = parser.parse()
    except Exception as e:
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
                }

    # Load all frames
    stem_base = replay_path.stem.rsplit('.', 1)[0]
    frame_files = sorted(
        replay_path.parent.glob(f"{stem_base}.*.vgr"),
        key=lambda f: int(f.stem.split('.')[-1]) if f.stem.split('.')[-1].isdigit() else 0
    )
    all_data = b"".join(f.read_bytes() for f in frame_files)
    match_name = replay_path.stem

    return players, all_data, match_name


def scan_acquire_events(players, all_data):
    """
    Scan [10 04 3D] events and extract:
      - per player: list of (item_id, qty, ts) tuples
    Event structure (confirmed):
      [10 04 3D][00 00][eid BE 2B][00 00][qty 1B][item_id LE 2B][00 00][counter BE 2B][ts f32 BE]
      offsets from header start:
        +3,+4 = 00 00
        +5,+6 = eid BE
        +7,+8 = 00 00  (separator)
        +9    = qty
        +10,+11 = item_id LE
        +12,+13 = 00 00
        +14,+15 = counter BE
        +16,+17,+18,+19 = NOPE -- let's check offset carefully

    Actual confirmed structure from memory notes:
      [10 04 3D][00 00][eid BE][00 00][qty][item_id LE][00 00][counter BE][ts f32 BE]
       0  1  2   3  4   5  6   7  8   9    10  11      12 13   14  15     16..19
    """
    events = defaultdict(list)  # eid -> [(item_id, qty, ts)]

    pos = 0
    while True:
        pos = all_data.find(ITEM_ACQUIRE_HEADER, pos)
        if pos == -1:
            break

        # Need at least 20 bytes after header start
        if pos + 20 > len(all_data):
            pos += 1
            continue

        # Validate separator bytes
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

        item_id_raw = struct.unpack_from("<H", all_data, pos + 10)[0]
        # Clip to 8-bit if high byte is noise
        item_id = item_id_raw if item_id_raw <= 255 else (item_id_raw & 0xFF)

        # Timestamp at offset +16 (f32 BE) - from notes
        ts = 0.0
        if pos + 20 <= len(all_data):
            ts_raw = struct.unpack_from(">f", all_data, pos + 16)[0]
            if 0 < ts_raw < 6000:
                ts = ts_raw

        events[eid].append((item_id, qty, ts))
        pos += 3

    return events


def analyze_all_replays():
    """Scan all replays and collect per-ID statistics."""
    replays = sorted([
        vgr for vgr in REPLAY_DIR.rglob("*.0.vgr")
        if "__MACOSX" not in str(vgr)
    ])
    print(f"[STAGE:begin:data_loading]")
    print(f"Found {len(replays)} replays to scan")

    # Data stores
    # qty2_data[item_id] -> list of buyer records
    # qty1_data[item_id] -> list of buyer records
    qty2_data = defaultdict(list)
    qty1_data = defaultdict(list)

    # Also track ALL seen IDs to find new ones
    all_qty2_ids = Counter()
    all_qty1_ids = Counter()

    errors = 0
    processed = 0

    for rp in replays:
        result = load_replay_data(rp)
        if not result:
            errors += 1
            continue

        players, all_data, match_name = result
        events = scan_acquire_events(players, all_data)
        processed += 1

        # Build per-player item set for co-item analysis
        # player_items[eid] -> {'qty1': set(ids), 'qty2': set(ids)}
        player_item_sets = defaultdict(lambda: {'qty1': [], 'qty2': []})
        for eid, ev_list in events.items():
            for (item_id, qty, ts) in ev_list:
                if qty == 1:
                    player_item_sets[eid]['qty1'].append((item_id, ts))
                elif qty == 2:
                    player_item_sets[eid]['qty2'].append((item_id, ts))

        # Aggregate ID counts
        for eid, sets in player_item_sets.items():
            for (iid, ts) in sets['qty1']:
                all_qty1_ids[iid] += 1
            for (iid, ts) in sets['qty2']:
                all_qty2_ids[iid] += 1

        # For each player, record buyer info for unmapped IDs
        for eid, sets in player_item_sets.items():
            pinfo = players.get(eid, {})
            hero = pinfo.get("hero", "?")
            pname = pinfo.get("name", "?")
            role = hero_role(hero)

            # All qty1 ids this player bought (as a set for co-item lookup)
            qty1_ids_set = set(iid for iid, _ in sets['qty1'])
            qty2_ids_set = set(iid for iid, _ in sets['qty2'])

            # qty=2 records
            qty2_by_id = defaultdict(list)
            for (iid, ts) in sets['qty2']:
                qty2_by_id[iid].append(ts)

            for iid, ts_list in qty2_by_id.items():
                if iid in STARTER_IDS_QTY2:
                    continue
                qty2_data[iid].append({
                    "match": match_name,
                    "player": pname,
                    "hero": hero,
                    "role": role,
                    "count": len(ts_list),
                    "timestamps": [round(t, 1) for t in ts_list],
                    "co_qty1_ids": qty1_ids_set - {iid},
                    "co_qty2_ids": qty2_ids_set - {iid},
                })

            # qty=1 records - only track unknown/interesting ones
            qty1_by_id = defaultdict(list)
            for (iid, ts) in sets['qty1']:
                qty1_by_id[iid].append(ts)

            for iid, ts_list in qty1_by_id.items():
                if iid not in ITEM_ID_MAP or ITEM_ID_MAP[iid].get("status") == "unknown":
                    qty1_data[iid].append({
                        "match": match_name,
                        "player": pname,
                        "hero": hero,
                        "role": role,
                        "count": len(ts_list),
                        "timestamps": [round(t, 1) for t in ts_list],
                        "co_qty1_ids": qty1_ids_set - {iid},
                    })

    print(f"Processed {processed}/{len(replays)} replays ({errors} errors)")
    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:data_loading]")

    return qty2_data, qty1_data, all_qty2_ids, all_qty1_ids


def format_item_name(iid, qty=1):
    """Get item name from mapping or label as unknown."""
    if qty == 2 and iid in range(0, 28):
        info = ITEM_ID_MAP.get(iid)
        if info:
            return f"{info['name']} ({info['status']})"
        return "UNMAPPED"
    info = ITEM_ID_MAP.get(iid)
    if info:
        return f"{info['name']} [{info.get('tier','?')}] ({info['status']})"
    return "UNMAPPED"


def role_breakdown(entries):
    """Return role percentage string."""
    role_counts = Counter(e["role"] for e in entries)
    total = sum(role_counts.values())
    parts = []
    for role in ["Captain", "Warrior", "Mage", "Sniper", "Assassin", "?"]:
        cnt = role_counts.get(role, 0)
        if cnt:
            parts.append(f"{role}:{cnt}({cnt*100//total}%)")
    return ", ".join(parts)


def print_id_report(iid, entries, qty, all_ids_counter):
    """Print detailed report for one item ID."""
    current = ITEM_ID_MAP.get(iid, {})
    status = current.get("status", "UNMAPPED")
    current_name = current.get("name", "UNMAPPED")
    total_buyers = len(entries)
    global_count = all_ids_counter[iid]

    print(f"\n{'='*78}")
    print(f"  ID {iid} (qty={qty}) | Current: '{current_name}' [{status}]")
    print(f"  Buyers: {total_buyers} players | Total acquire events: {global_count}")
    print(f"{'='*78}")

    if not entries:
        print("  (No buyers found)")
        return

    # Hero distribution
    hero_counts = Counter(e["hero"] for e in entries)
    print(f"\n  Hero distribution ({len(hero_counts)} unique heroes):")
    for hero, cnt in hero_counts.most_common(15):
        role = hero_role(hero)
        pct = cnt * 100 // total_buyers
        bar = '#' * (cnt * 20 // max(hero_counts.values()))
        print(f"    {hero:<16} {role:<9} {cnt:>3}x ({pct:>2}%) {bar}")

    # Role breakdown
    print(f"\n  Role pattern: {role_breakdown(entries)}")

    # Buy count (how many times same player buys this ID)
    count_dist = Counter(e["count"] for e in entries)
    print(f"\n  Buys per player: {dict(sorted(count_dist.items()))}")

    # Timing
    all_ts = [ts for e in entries for ts in e["timestamps"] if ts > 0]
    if all_ts:
        avg_ts = sum(all_ts) / len(all_ts)
        min_ts = min(all_ts)
        max_ts = max(all_ts)
        med_ts = sorted(all_ts)[len(all_ts)//2]
        print(f"  Timing (s): avg={avg_ts:.0f}, med={med_ts:.0f}, min={min_ts:.0f}, max={max_ts:.0f}")
        # Early/late split
        early = sum(1 for t in all_ts if t < 300)
        late  = sum(1 for t in all_ts if t >= 900)
        print(f"  Early(<5min): {early}, Mid(5-15min): {len(all_ts)-early-late}, Late(>15min): {late}")

    # Co-item analysis (qty=1 co-items, most common)
    if qty == 2:
        co_counter = Counter()
        for e in entries:
            for cid in e.get("co_qty1_ids", set()):
                co_counter[cid] += 1
        print(f"\n  Most common qty=1 co-items (top 12):")
        for cid, cnt in co_counter.most_common(12):
            info = ITEM_ID_MAP.get(cid, {})
            name = info.get("name", "UNMAPPED")
            tier = info.get("tier", "?")
            pct = cnt * 100 // total_buyers
            print(f"    ID {cid:>3}: {name:<28} T{tier}  {cnt:>3}/{total_buyers} ({pct}%)")

        # Co qty=2 items
        co2_counter = Counter()
        for e in entries:
            for cid in e.get("co_qty2_ids", set()):
                if cid != 14:
                    co2_counter[cid] += 1
        if co2_counter:
            print(f"\n  Co qty=2 items:")
            for cid, cnt in co2_counter.most_common(8):
                info = ITEM_ID_MAP.get(cid, {})
                name = info.get("name", "UNMAPPED")
                pct = cnt * 100 // total_buyers
                print(f"    ID {cid:>3}: {name:<28} {cnt:>3}/{total_buyers} ({pct}%)")
    else:
        co_counter = Counter()
        for e in entries:
            for cid in e.get("co_qty1_ids", set()):
                co_counter[cid] += 1
        print(f"\n  Most common co-items (top 12):")
        for cid, cnt in co_counter.most_common(12):
            info = ITEM_ID_MAP.get(cid, {})
            name = info.get("name", "UNMAPPED")
            tier = info.get("tier", "?")
            pct = cnt * 100 // total_buyers
            print(f"    ID {cid:>3}: {name:<28} T{tier}  {cnt:>3}/{total_buyers} ({pct}%)")

    # Sample records (first 8)
    print(f"\n  Sample buyers (up to 8):")
    for e in entries[:8]:
        ts_str = ", ".join(f"{t:.0f}s" for t in e["timestamps"][:5])
        print(f"    {e['match'][:22]:22s} | {e['player'][:12]:12s} | {e['hero']:<14} | "
              f"x{e['count']} @ [{ts_str}]")


def discover_new_ids(all_qty2_ids, all_qty1_ids, qty2_data, qty1_data):
    """Find IDs that appear but are not in ITEM_ID_MAP at all."""
    print(f"\n{'='*78}")
    print("  NEW ID DISCOVERY - IDs not in ITEM_ID_MAP at all")
    print(f"{'='*78}")

    # qty=2 range 0-27
    known_qty2 = set(ITEM_ID_MAP.keys()) & set(range(0, 28))
    known_qty2.add(14)  # system
    new_qty2 = {iid for iid in all_qty2_ids if iid in range(0, 28) and iid not in known_qty2}
    print(f"\n  NEW qty=2 IDs (0-27 range, not in mapping): {sorted(new_qty2)}")
    for iid in sorted(new_qty2):
        cnt = all_qty2_ids[iid]
        buyers = qty2_data.get(iid, [])
        hero_dist = Counter(e["hero"] for e in buyers)
        print(f"    ID {iid}: {cnt} total events, {len(buyers)} buyers | heroes: "
              f"{dict(hero_dist.most_common(5))}")

    # qty=1 range 200-255
    known_qty1 = set(ITEM_ID_MAP.keys()) & set(range(200, 256))
    new_qty1 = {iid for iid in all_qty1_ids if iid in range(200, 256) and iid not in known_qty1}
    print(f"\n  NEW qty=1 IDs (200-255 range, not in mapping): {sorted(new_qty1)}")
    for iid in sorted(new_qty1):
        cnt = all_qty1_ids[iid]
        buyers = qty1_data.get(iid, [])
        hero_dist = Counter(e["hero"] for e in buyers)
        timing = []
        for e in buyers:
            timing.extend(e["timestamps"])
        avg_t = sum(timing)/len(timing) if timing else 0
        print(f"    ID {iid}: {cnt} events, {len(buyers)} buyers, avg_ts={avg_t:.0f}s | "
              f"heroes: {dict(hero_dist.most_common(5))}")

    # Also check for qty=2 IDs outside 0-27 (unusual)
    out_of_range_qty2 = {iid for iid in all_qty2_ids if iid not in range(0, 28)}
    if out_of_range_qty2:
        print(f"\n  qty=2 IDs OUTSIDE 0-27 range (unusual): {sorted(out_of_range_qty2)}")
        for iid in sorted(out_of_range_qty2):
            cnt = all_qty2_ids[iid]
            print(f"    ID {iid}: {cnt} events")


def print_summary_table(all_qty2_ids, all_qty1_ids):
    """Print frequency table of all observed IDs."""
    print(f"\n{'='*78}")
    print("  FREQUENCY TABLE - All observed qty=2 IDs (0-27 range)")
    print(f"{'='*78}")
    print(f"  {'ID':>4} {'Events':>7}  {'Mapped Name':<30} {'Status'}")
    print(f"  {'-'*65}")
    for iid in range(0, 28):
        cnt = all_qty2_ids.get(iid, 0)
        if cnt == 0:
            continue
        info = ITEM_ID_MAP.get(iid, {})
        name = info.get("name", "** UNMAPPED **")
        status = info.get("status", "???")
        marker = "***" if iid not in ITEM_ID_MAP and iid != 14 else ""
        print(f"  {iid:>4} {cnt:>7}  {name:<30} {status} {marker}")

    print(f"\n{'='*78}")
    print("  FREQUENCY TABLE - All observed qty=1 IDs (200-255 range)")
    print(f"{'='*78}")
    print(f"  {'ID':>4} {'Events':>7}  {'Mapped Name':<30} {'Status'}")
    print(f"  {'-'*65}")
    for iid in range(200, 256):
        cnt = all_qty1_ids.get(iid, 0)
        if cnt == 0:
            continue
        info = ITEM_ID_MAP.get(iid, {})
        name = info.get("name", "** UNMAPPED **")
        status = info.get("status", "???")
        marker = "***" if iid not in ITEM_ID_MAP else ""
        print(f"  {iid:>4} {cnt:>7}  {name:<30} {status} {marker}")


def main():
    t0 = time.time()
    print("[OBJECTIVE] Hunt unmapped item IDs in 56 Vainglory replays")
    print("           Focus: qty=2 IDs 3,19,24 and qty=1 IDs 217,233,239")
    print("           Also discover any NEW IDs not previously seen")
    print()

    qty2_data, qty1_data, all_qty2_ids, all_qty1_ids = analyze_all_replays()

    # Print summary frequency tables
    print_summary_table(all_qty2_ids, all_qty1_ids)

    # =========================================================================
    # Discover new IDs
    # =========================================================================
    discover_new_ids(all_qty2_ids, all_qty1_ids, qty2_data, qty1_data)

    # =========================================================================
    # Detailed reports for priority unmapped IDs
    # =========================================================================
    print(f"\n\n{'#'*78}")
    print("  DETAILED REPORTS: qty=2 UNMAPPED IDs")
    print(f"{'#'*78}")

    # All qty=2 IDs not in mapping (excluding system 14)
    unmapped_qty2 = sorted(
        iid for iid in all_qty2_ids
        if iid in range(0, 28)
        and iid not in ITEM_ID_MAP
        and iid != 14
    )
    # Also include known-but-status=unknown if any in qty2
    for iid in unmapped_qty2:
        print_id_report(iid, qty2_data.get(iid, []), qty=2, all_ids_counter=all_qty2_ids)

    # Also print the 3 priority qty=2 IDs even if mapped (for context)
    priority_qty2 = [3, 19, 24]
    for iid in priority_qty2:
        if iid in ITEM_ID_MAP:
            print(f"\n  [Already mapped: ID {iid} = {ITEM_ID_MAP[iid]['name']}]")
        elif iid not in unmapped_qty2 and all_qty2_ids.get(iid, 0) > 0:
            print_id_report(iid, qty2_data.get(iid, []), qty=2, all_ids_counter=all_qty2_ids)
        elif all_qty2_ids.get(iid, 0) == 0:
            print(f"\n  ID {iid}: 0 events found across all replays")

    print(f"\n\n{'#'*78}")
    print("  DETAILED REPORTS: qty=1 UNMAPPED IDs (status=unknown)")
    print(f"{'#'*78}")

    # IDs with status=unknown
    unknown_qty1 = [217, 233, 239]
    for iid in unknown_qty1:
        print_id_report(iid, qty1_data.get(iid, []), qty=1, all_ids_counter=all_qty1_ids)

    # Any other qty=1 IDs not in mapping at all (200-255)
    new_unmapped_qty1 = sorted(
        iid for iid in all_qty1_ids
        if iid in range(200, 256) and iid not in ITEM_ID_MAP
    )
    if new_unmapped_qty1:
        print(f"\n\n{'#'*78}")
        print("  DETAILED REPORTS: NEW qty=1 IDs (not in mapping)")
        print(f"{'#'*78}")
        for iid in new_unmapped_qty1:
            print_id_report(iid, qty1_data.get(iid, []), qty=1, all_ids_counter=all_qty1_ids)

    # =========================================================================
    # Final identification guesses
    # =========================================================================
    t1 = time.time()
    print(f"\n\n{'#'*78}")
    print("  IDENTIFICATION SUMMARY & BEST GUESSES")
    print(f"{'#'*78}")
    print("""
Known VG items NOT yet mapped (candidates for unmapped IDs):
  Consumables: Healing Flask, Minion Candy, Crystal Infusion, Weapon Infusion,
               Scout Trap (x), Flare (x), Scout Cam, ScoutPak, ScoutTuff
  Utility:     Teleport Boots, Eclipse Prism, Void Battery
  Contracts:   Protector Contract, Ironguard Contract, Dragonblood Contract

qty=2 ID mapping context:
  Captains-only -> vision/utility item
  Mixed carries -> common T3 item
  Consumable behavior -> repeated buys, any role
""")

    # Print per-ID guess based on data
    print("  Per-ID best guesses (based on analysis above):")
    print()

    for iid in sorted(set(unmapped_qty2) | set(priority_qty2)):
        entries = qty2_data.get(iid, [])
        if not entries and iid in ITEM_ID_MAP:
            print(f"  ID {iid:>2} (qty=2): {ITEM_ID_MAP[iid]['name']} [already mapped]")
            continue
        if not entries:
            print(f"  ID {iid:>2} (qty=2): NO DATA (0 buyers)")
            continue
        hero_counts = Counter(e["hero"] for e in entries)
        role_counts = Counter(e["role"] for e in entries)
        n = len(entries)
        cap_pct = role_counts.get("Captain", 0) * 100 // n
        war_pct = role_counts.get("Warrior", 0) * 100 // n
        mag_pct = role_counts.get("Mage", 0) * 100 // n
        sni_pct = role_counts.get("Sniper", 0) * 100 // n
        all_ts = [ts for e in entries for ts in e["timestamps"] if ts > 0]
        avg_ts = sum(all_ts)/len(all_ts) if all_ts else 0
        max_count = max(e["count"] for e in entries)
        print(f"  ID {iid:>2} (qty=2): n={n} buyers | Cap={cap_pct}% War={war_pct}% "
              f"Mag={mag_pct}% Sni={sni_pct}% | avg_ts={avg_ts:.0f}s | max_per_player={max_count}")
        print(f"           Top heroes: {dict(hero_counts.most_common(4))}")

    print()
    for iid in unknown_qty1 + new_unmapped_qty1:
        entries = qty1_data.get(iid, [])
        if not entries:
            print(f"  ID {iid:>3} (qty=1): NO DATA (0 buyers)")
            continue
        hero_counts = Counter(e["hero"] for e in entries)
        role_counts = Counter(e["role"] for e in entries)
        n = len(entries)
        cap_pct = role_counts.get("Captain", 0) * 100 // n
        all_ts = [ts for e in entries for ts in e["timestamps"] if ts > 0]
        avg_ts = sum(all_ts)/len(all_ts) if all_ts else 0
        max_count = max(e["count"] for e in entries)
        print(f"  ID {iid:>3} (qty=1): n={n} buyers | Cap={cap_pct}% | avg_ts={avg_ts:.0f}s "
              f"| max_per_player={max_count}")
        print(f"           Top heroes: {dict(hero_counts.most_common(4))}")

    print(f"\n[STAT:elapsed] {t1-t0:.1f}s")
    print(f"\n[FINDING] Scan complete. See reports above for per-ID details.")


if __name__ == "__main__":
    main()
