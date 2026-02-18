#!/usr/bin/env python3
"""
item_narrowed_hunt.py - Targeted hunt for specific unmapped item IDs.

Uses build-chain constraints to narrow candidates:
  1. Minion's Foot  (300g T1 WP): buyers of Lucky Strike (252)
  2. Stormguard Banner (600g T2): buyers of Stormcrown (7)
  3. Scout items: IDs 233/239 captain profile analysis
  4. Shiversteel (1950g T3): buyers of both Dragonheart(212) + Blazing Salvo(207)
  5. Complete gap scan: every ID in 200-255 range not in ITEM_ID_MAP

Acquire event format (confirmed):
  [10 04 3D][00 00][eid BE 2B][00 00][qty 1B][item_id LE 2B][00 00][counter BE 2B][ts f32 BE 4B]
   0  1  2   3  4   5  6      7  8   9        10  11         12 13   14  15         16..19
"""

import struct
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from vg.core.vgr_parser import VGRParser
from vg.core.vgr_mapping import ITEM_ID_MAP, BINARY_HERO_ID_MAP, HERO_ID_MAP

REPLAY_DIR = Path(r"D:\Desktop\My Folder\Game\VG\vg replay")
ITEM_ACQUIRE_HEADER = bytes([0x10, 0x04, 0x3D])

HERO_ROLES = {info["name"]: info["role"] for info in HERO_ID_MAP.values()}

# Key IDs referenced in analysis
LUCKY_STRIKE   = 252
TORNADO_TRIGGER = 210
TYRANTS_MONOCLE = 5   # qty=2
STORMCROWN     = 7    # qty=2
DRAGONHEART    = 212
BLAZING_SALVO  = 207
OAKHEART       = 211

# Known 300g T1 WP IDs (to exclude from Minion's Foot candidates)
KNOWN_300G_WP = {202, 204, 243}

# System ID to skip
STARTER_IDS = {14}

def le_to_be(eid_le):
    return struct.unpack('>H', struct.pack('<H', eid_le))[0]


def hero_role(hero_name):
    return HERO_ROLES.get(hero_name, "?")


def load_replay_data(replay_path):
    """Load player info + concatenated frame bytes."""
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
                    "role": hero_role(p.get("hero_name", "?") or "?"),
                }

    stem_base = replay_path.stem.rsplit('.', 1)[0]
    frame_files = sorted(
        replay_path.parent.glob(f"{stem_base}.*.vgr"),
        key=lambda f: int(f.stem.split('.')[-1]) if f.stem.split('.')[-1].isdigit() else 0
    )
    all_data = b"".join(f.read_bytes() for f in frame_files)
    return players, all_data, replay_path.stem


def scan_acquire_events(players, all_data):
    """
    Scan [10 04 3D] headers and return per-player item purchase lists.
    Returns: dict eid -> list of (item_id, qty, ts)
    """
    events = defaultdict(list)
    pos = 0
    while True:
        pos = all_data.find(ITEM_ACQUIRE_HEADER, pos)
        if pos == -1:
            break
        if pos + 20 > len(all_data):
            pos += 1
            continue

        # Validate separator
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
        item_id = item_id_raw if item_id_raw <= 255 else (item_id_raw & 0xFF)

        ts = 0.0
        ts_raw = struct.unpack_from(">f", all_data, pos + 16)[0]
        if 0 < ts_raw < 6000:
            ts = ts_raw

        events[eid].append((item_id, qty, ts))
        pos += 3

    return events


def item_name(iid, qty=1):
    info = ITEM_ID_MAP.get(iid)
    if info:
        return f"{info['name']}[T{info.get('tier','?')}]"
    return f"ID{iid}???"


def role_pct(role_counts, total, role):
    return role_counts.get(role, 0) * 100 // total if total else 0


# =============================================================================
# Main analysis
# =============================================================================

def main():
    t0 = time.time()
    print("[OBJECTIVE] Targeted hunt for unmapped items using build-chain constraints")
    print(f"           Minion's Foot, Stormguard Banner, Scout items, Shiversteel, ID gap scan")
    print()

    replays = sorted([
        vgr for vgr in REPLAY_DIR.rglob("*.0.vgr")
        if "__MACOSX" not in str(vgr)
    ])

    print(f"[STAGE:begin:data_loading]")
    print(f"[DATA] Found {len(replays)} replays (.0.vgr files)")

    # -------------------------------------------------------------------------
    # Per-player item sets across ALL replays
    # player_records: list of dicts with player info + item sets
    # -------------------------------------------------------------------------
    player_records = []          # each entry = one player from one match
    all_qty1_counter = Counter() # global frequency: item_id -> total events
    all_qty2_counter = Counter()

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

        for eid, ev_list in events.items():
            pinfo = players.get(eid, {})
            qty1_items = [(iid, ts) for iid, qty, ts in ev_list if qty == 1]
            qty2_items = [(iid, ts) for iid, qty, ts in ev_list if qty == 2 and iid not in STARTER_IDS]

            qty1_ids = [iid for iid, _ in qty1_items]
            qty2_ids = [iid for iid, _ in qty2_items]

            for iid in qty1_ids:
                all_qty1_counter[iid] += 1
            for iid in qty2_ids:
                all_qty2_counter[iid] += 1

            player_records.append({
                "match": match_name,
                "player": pinfo.get("name", "?"),
                "hero": pinfo.get("hero", "?"),
                "role": pinfo.get("role", "?"),
                "qty1_ids": set(qty1_ids),          # unique item IDs bought
                "qty1_list": qty1_ids,               # with duplicates for count
                "qty2_ids": set(iid for iid in qty2_ids),
                "qty1_items": qty1_items,            # (iid, ts) pairs
                "qty2_items": qty2_items,
            })

    print(f"[DATA] Processed {processed}/{len(replays)} replays ({errors} errors)")
    print(f"[DATA] {len(player_records)} player records collected")
    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:data_loading]")

    # =========================================================================
    # ANALYSIS 1: Minion's Foot
    # 300g T1 WP that builds into Lucky Strike (252)
    # Lucky Strike builds into Tyrant's Monocle (ID 5 qty=2) and Tornado Trigger (210)
    # =========================================================================
    print(f"\n{'='*78}")
    print("  ANALYSIS 1: Minion's Foot (T1 WP 300g -> Lucky Strike 252)")
    print(f"{'='*78}")

    # Players who bought Lucky Strike (252) in qty=1
    ls_buyers = [r for r in player_records if LUCKY_STRIKE in r["qty1_ids"]]
    print(f"\n  Players who bought Lucky Strike (252): {len(ls_buyers)}")

    # Also include players who bought Tyrant's Monocle (qty=2) or Tornado Trigger (qty=1)
    tm_buyers = [r for r in player_records if TYRANTS_MONOCLE in r["qty2_ids"]]
    tt_buyers = [r for r in player_records if TORNADO_TRIGGER in r["qty1_ids"]]
    combined_wp_crit = set()
    for r in ls_buyers + tm_buyers + tt_buyers:
        combined_wp_crit.add((r["match"], r["player"]))

    print(f"  Players who bought Tyrant's Monocle (ID 5 qty=2): {len(tm_buyers)}")
    print(f"  Players who bought Tornado Trigger (210 qty=1): {len(tt_buyers)}")
    print(f"  Union (any of above): {len(combined_wp_crit)} player-matches")

    # What other qty=1 items do Lucky Strike buyers purchase?
    # We want 300g items (T1) not already known
    # Count which unmapped/unknown qty=1 IDs appear among LS buyers
    ls_co_items = Counter()
    for r in ls_buyers:
        for iid in r["qty1_ids"]:
            if iid != LUCKY_STRIKE:
                ls_co_items[iid] += 1

    print(f"\n  Co-buy frequencies among Lucky Strike buyers (top 20 qty=1 IDs):")
    print(f"  {'ID':>4}  {'Name':<30} {'Tier':>4}  {'Buyers':>6}  {'Pct':>5}  Notes")
    print(f"  {'-'*70}")
    n_ls = len(ls_buyers)
    for iid, cnt in ls_co_items.most_common(20):
        info = ITEM_ID_MAP.get(iid, {})
        name = info.get("name", "*** UNMAPPED ***")
        tier = info.get("tier", "?")
        status = info.get("status", "???")
        pct = cnt * 100 // n_ls
        flag = " <<< T1 CANDIDATE" if iid not in ITEM_ID_MAP and all_qty1_counter[iid] < 500 else ""
        flag = flag or (" <<< UNMAPPED" if iid not in ITEM_ID_MAP else "")
        print(f"  {iid:>4}  {name:<30} T{tier}  {cnt:>6}/{n_ls}  ({pct:>3}%)  {flag}")

    # Now identify candidates: present in >50% of LS buyers, NOT in known 300g set, NOT a T2+ item
    print(f"\n  Candidate filtering: must appear in >=40% of LS buyers AND not be a known ID")
    candidates_1 = []
    for iid, cnt in ls_co_items.items():
        pct = cnt * 100 // n_ls
        if pct >= 40 and iid not in ITEM_ID_MAP and iid not in {LUCKY_STRIKE}:
            candidates_1.append((iid, cnt, pct))
    candidates_1.sort(key=lambda x: -x[1])

    if candidates_1:
        print(f"\n  [FINDING] Minion's Foot CANDIDATES (unmapped, >=40% co-buy with LS):")
        for iid, cnt, pct in candidates_1:
            global_cnt = all_qty1_counter[iid]
            print(f"    ID {iid}: {cnt}/{n_ls} LS buyers ({pct}%), global events={global_cnt}")
            # Show hero distribution for this ID among ALL buyers
            buyers_of_id = [r for r in player_records if iid in r["qty1_ids"]]
            hero_dist = Counter(r["hero"] for r in buyers_of_id)
            role_dist = Counter(r["role"] for r in buyers_of_id)
            print(f"      Global buyers: {len(buyers_of_id)} | roles: {dict(role_dist)}")
            print(f"      Top heroes: {dict(hero_dist.most_common(6))}")
    else:
        print(f"  No unmapped IDs found at >=40% co-buy rate with Lucky Strike buyers")
        # Lower threshold and show what's there
        print(f"  (Showing all unmapped IDs co-bought by >=1 LS buyer:)")
        for iid, cnt in ls_co_items.most_common():
            if iid not in ITEM_ID_MAP:
                pct = cnt * 100 // n_ls
                print(f"    ID {iid}: {cnt}/{n_ls} ({pct}%)")

    # Additional: check if Weapon Blade (202) appears with LS buyers but something else is needed
    wb_with_ls = sum(1 for r in ls_buyers if 202 in r["qty1_ids"])
    ss_with_ls = sum(1 for r in ls_buyers if 204 in r["qty1_ids"])  # Swift Shooter
    boe_with_ls = sum(1 for r in ls_buyers if 243 in r["qty1_ids"])  # Book of Eulogies
    print(f"\n  Known T1 WP items among LS buyers:")
    print(f"    Weapon Blade (202): {wb_with_ls}/{n_ls} ({wb_with_ls*100//n_ls if n_ls else 0}%)")
    print(f"    Swift Shooter (204): {ss_with_ls}/{n_ls} ({ss_with_ls*100//n_ls if n_ls else 0}%)")
    print(f"    Book of Eulogies (243): {boe_with_ls}/{n_ls} ({boe_with_ls*100//n_ls if n_ls else 0}%)")

    # =========================================================================
    # ANALYSIS 2: Stormguard Banner
    # T2 600g jungle item that builds into Stormcrown (ID 7, qty=2)
    # Builds from Oakheart (211)
    # =========================================================================
    print(f"\n\n{'='*78}")
    print("  ANALYSIS 2: Stormguard Banner (T2 -> Stormcrown ID 7)")
    print(f"{'='*78}")

    sc_buyers = [r for r in player_records if STORMCROWN in r["qty2_ids"]]
    print(f"\n  Players who bought Stormcrown (ID 7 qty=2): {len(sc_buyers)}")

    # Co-buy frequencies among Stormcrown buyers
    sc_co_items = Counter()
    for r in sc_buyers:
        for iid in r["qty1_ids"]:
            sc_co_items[iid] += 1

    print(f"\n  Co-buy frequencies among Stormcrown buyers (qty=1 items, top 25):")
    print(f"  {'ID':>4}  {'Name':<30} {'Tier':>4}  {'Buyers':>6}  {'Pct':>5}  Notes")
    print(f"  {'-'*70}")
    n_sc = len(sc_buyers)
    for iid, cnt in sc_co_items.most_common(25):
        info = ITEM_ID_MAP.get(iid, {})
        name = info.get("name", "*** UNMAPPED ***")
        tier = info.get("tier", "?")
        pct = cnt * 100 // n_sc if n_sc else 0
        flag = " <<< UNMAPPED" if iid not in ITEM_ID_MAP else ""
        print(f"  {iid:>4}  {name:<30} T{tier}  {cnt:>6}/{n_sc}  ({pct:>3}%)  {flag}")

    # Unmapped IDs that appear with Stormcrown buyers
    print(f"\n  Unmapped IDs co-bought with Stormcrown buyers:")
    sc_candidates = []
    for iid, cnt in sc_co_items.items():
        if iid not in ITEM_ID_MAP:
            pct = cnt * 100 // n_sc if n_sc else 0
            sc_candidates.append((iid, cnt, pct))
    sc_candidates.sort(key=lambda x: -x[1])

    if sc_candidates:
        for iid, cnt, pct in sc_candidates:
            global_cnt = all_qty1_counter[iid]
            buyers_of_id = [r for r in player_records if iid in r["qty1_ids"]]
            role_dist = Counter(r["role"] for r in buyers_of_id)
            hero_dist = Counter(r["hero"] for r in buyers_of_id)
            print(f"  [FINDING] ID {iid}: {cnt}/{n_sc} SC buyers ({pct}%), global={global_cnt}")
            print(f"    Roles: {dict(role_dist)} | Heroes: {dict(hero_dist.most_common(5))}")
    else:
        print(f"  No unmapped qty=1 IDs found among Stormcrown buyers")

    # Oakheart co-buy check: SGB builds from Oakheart, so look for Oakheart buyers who also buy SC
    oak_and_sc = [r for r in player_records if OAKHEART in r["qty1_ids"] and STORMCROWN in r["qty2_ids"]]
    print(f"\n  Players with BOTH Oakheart(211) + Stormcrown(7): {len(oak_and_sc)}")
    if oak_and_sc:
        co_with_oak_sc = Counter()
        for r in oak_and_sc:
            for iid in r["qty1_ids"]:
                if iid not in {OAKHEART}:
                    co_with_oak_sc[iid] += 1
        print(f"  Unmapped co-items among Oakheart+Stormcrown buyers:")
        n_oas = len(oak_and_sc)
        for iid, cnt in co_with_oak_sc.most_common(20):
            if iid not in ITEM_ID_MAP:
                pct = cnt * 100 // n_oas
                print(f"    ID {iid}: {cnt}/{n_oas} ({pct}%)")

    # =========================================================================
    # ANALYSIS 3: Scout items (IDs 233, 239)
    # Vision consumables bought by captains
    # ScoutPak (500g), ScoutTuff (500g) - captain exclusives
    # Also check Hourglass (217) -> ScoutPak build path
    # =========================================================================
    print(f"\n\n{'='*78}")
    print("  ANALYSIS 3: Scout Items - IDs 233 and 239 captain profile")
    print(f"{'='*78}")

    for scout_id in [233, 239]:
        buyers = [r for r in player_records if scout_id in r["qty1_ids"]]
        print(f"\n  ID {scout_id} - Current mapping: {ITEM_ID_MAP.get(scout_id, {}).get('name', 'UNMAPPED')}")
        print(f"  Total buyers: {len(buyers)}")
        if not buyers:
            continue

        role_dist = Counter(r["role"] for r in buyers)
        hero_dist = Counter(r["hero"] for r in buyers)
        total = len(buyers)

        print(f"  Role distribution: {dict(role_dist)}")
        captain_pct = role_pct(role_dist, total, "Captain")
        print(f"  Captain %: {captain_pct}%")
        print(f"  Top heroes: {dict(hero_dist.most_common(10))}")

        # Purchase count per player (repeated buys = consumable)
        count_dist = Counter()
        for r in buyers:
            count = r["qty1_list"].count(scout_id)
            count_dist[count] += 1
        print(f"  Buys per player: {dict(sorted(count_dist.items()))}")

        # Timing analysis
        all_ts = []
        for r in player_records:
            for iid, ts in r["qty1_items"]:
                if iid == scout_id and ts > 0:
                    all_ts.append(ts)
        if all_ts:
            avg_ts = sum(all_ts) / len(all_ts)
            min_ts = min(all_ts)
            max_ts = max(all_ts)
            print(f"  Timing: avg={avg_ts:.0f}s, min={min_ts:.0f}s, max={max_ts:.0f}s")
            early = sum(1 for t in all_ts if t < 300)
            print(f"  Early buys (<5min): {early}/{len(all_ts)}")

        # Co-items
        co = Counter()
        for r in buyers:
            for iid in r["qty1_ids"]:
                if iid != scout_id:
                    co[iid] += 1
        print(f"  Top co-items:")
        for cid, cnt in co.most_common(10):
            info = ITEM_ID_MAP.get(cid, {})
            name = info.get("name", "UNMAPPED")
            pct = cnt * 100 // total
            print(f"    ID {cid:>3}: {name:<28} {cnt}/{total} ({pct}%)")

        # Check co-occurrence with ID 217 (Hourglass -> ScoutPak path)
        hourglass_cobuy = sum(1 for r in buyers if 217 in r["qty1_ids"])
        print(f"  Hourglass(217) co-buy: {hourglass_cobuy}/{total} ({hourglass_cobuy*100//total if total else 0}%)")
        scout_trap_cobuy = sum(1 for r in buyers if 225 in r["qty1_ids"])
        print(f"  Scout Trap(225) co-buy: {scout_trap_cobuy}/{total} ({scout_trap_cobuy*100//total if total else 0}%)")

    # Check for ANY unmapped ID with captain-exclusive pattern
    print(f"\n  Captain-exclusive unmapped IDs (>=60% captain buyers):")
    for iid in range(200, 256):
        if iid in ITEM_ID_MAP:
            continue
        if all_qty1_counter[iid] < 2:
            continue
        buyers_of_id = [r for r in player_records if iid in r["qty1_ids"]]
        if len(buyers_of_id) < 2:
            continue
        role_dist = Counter(r["role"] for r in buyers_of_id)
        total = len(buyers_of_id)
        cap_pct = role_pct(role_dist, total, "Captain")
        if cap_pct >= 60:
            hero_dist = Counter(r["hero"] for r in buyers_of_id)
            count_dist = Counter(r["qty1_list"].count(iid) for r in buyers_of_id)
            print(f"  ID {iid}: {total} buyers, Cap={cap_pct}% | {dict(hero_dist.most_common(5))} | buys/player: {dict(sorted(count_dist.items()))}")

    # =========================================================================
    # ANALYSIS 4: Shiversteel
    # T3 1950g defense: builds from Dragonheart(212) + Blazing Salvo(207)
    # =========================================================================
    print(f"\n\n{'='*78}")
    print("  ANALYSIS 4: Shiversteel (T3 -> Dragonheart 212 + Blazing Salvo 207)")
    print(f"{'='*78}")

    # Players with BOTH Dragonheart AND Blazing Salvo
    dh_and_bs = [r for r in player_records
                 if DRAGONHEART in r["qty1_ids"] and BLAZING_SALVO in r["qty1_ids"]]
    print(f"\n  Players with both Dragonheart(212) + Blazing Salvo(207): {len(dh_and_bs)}")

    if dh_and_bs:
        role_dist = Counter(r["role"] for r in dh_and_bs)
        hero_dist = Counter(r["hero"] for r in dh_and_bs)
        print(f"  Role distribution: {dict(role_dist)}")
        print(f"  Top heroes: {dict(hero_dist.most_common(10))}")

        # What qty=2 items do these players complete?
        qty2_counter = Counter()
        for r in dh_and_bs:
            for iid in r["qty2_ids"]:
                qty2_counter[iid] += 1

        n_dh = len(dh_and_bs)
        print(f"\n  qty=2 items completed by DH+BS buyers (top 10):")
        for iid, cnt in qty2_counter.most_common(10):
            info = ITEM_ID_MAP.get(iid, {})
            name = info.get("name", "*** UNMAPPED ***")
            pct = cnt * 100 // n_dh
            flag = " <<< UNMAPPED" if iid not in ITEM_ID_MAP else ""
            print(f"    ID {iid:>3}: {name:<30} {cnt}/{n_dh} ({pct}%){flag}")

        # Check unmapped qty=2 IDs among DH+BS buyers
        unmapped_qty2_dh = [(iid, cnt) for iid, cnt in qty2_counter.items()
                            if iid not in ITEM_ID_MAP and iid not in STARTER_IDS]
        if unmapped_qty2_dh:
            print(f"\n  [FINDING] Unmapped qty=2 IDs among DH+BS buyers (Shiversteel candidates):")
            for iid, cnt in sorted(unmapped_qty2_dh, key=lambda x: -x[1]):
                pct = cnt * 100 // n_dh
                buyers_of_id = [r for r in dh_and_bs if iid in r["qty2_ids"]]
                hero_dist2 = Counter(r["hero"] for r in buyers_of_id)
                print(f"    ID {iid} (qty=2): {cnt}/{n_dh} ({pct}%) | heroes: {dict(hero_dist2.most_common(5))}")
        else:
            print(f"\n  No unmapped qty=2 IDs found among DH+BS buyers")
            # Show what qty=2 they DO complete
            print(f"  Existing qty=2 completions:")
            for iid, cnt in qty2_counter.most_common(8):
                pct = cnt * 100 // n_dh
                info = ITEM_ID_MAP.get(iid, {})
                print(f"    ID {iid}: {info.get('name','?')} [{info.get('status','?')}] {cnt}/{n_dh} ({pct}%)")

        # Also check unmapped qty=1 co-items among DH+BS buyers
        co_qty1 = Counter()
        for r in dh_and_bs:
            for iid in r["qty1_ids"]:
                if iid not in {DRAGONHEART, BLAZING_SALVO}:
                    co_qty1[iid] += 1
        unmapped_co = [(iid, cnt) for iid, cnt in co_qty1.items() if iid not in ITEM_ID_MAP]
        if unmapped_co:
            print(f"\n  Unmapped qty=1 co-items among DH+BS buyers:")
            for iid, cnt in sorted(unmapped_co, key=lambda x: -x[1]):
                pct = cnt * 100 // n_dh
                print(f"    ID {iid}: {cnt}/{n_dh} ({pct}%)")

    # =========================================================================
    # ANALYSIS 5: Complete ID gap scan (200-255 range)
    # Every ID appearing in replays but NOT in ITEM_ID_MAP
    # =========================================================================
    print(f"\n\n{'='*78}")
    print("  ANALYSIS 5: Complete Gap Scan - All IDs in 200-255 not in ITEM_ID_MAP")
    print(f"{'='*78}")

    # Also check qty=2 IDs in 0-27
    print(f"\n  A) qty=2 IDs (0-27 range) not in ITEM_ID_MAP:")
    unmapped_qty2_ids = sorted(
        iid for iid in all_qty2_counter
        if iid in range(0, 28) and iid not in ITEM_ID_MAP and iid not in STARTER_IDS
    )
    if unmapped_qty2_ids:
        for iid in unmapped_qty2_ids:
            buyers_of_id = [r for r in player_records if iid in r["qty2_ids"]]
            role_dist = Counter(r["role"] for r in buyers_of_id)
            hero_dist = Counter(r["hero"] for r in buyers_of_id)
            global_cnt = all_qty2_counter[iid]
            print(f"  [FINDING] ID {iid} (qty=2): {len(buyers_of_id)} buyers, {global_cnt} events")
            print(f"    Roles: {dict(role_dist)}")
            print(f"    Heroes: {dict(hero_dist.most_common(8))}")
            # Co-items
            co = Counter()
            for r in buyers_of_id:
                for cid in r["qty1_ids"]:
                    co[cid] += 1
            print(f"    Top qty=1 co-items:")
            for cid, cnt in co.most_common(10):
                info = ITEM_ID_MAP.get(cid, {})
                name = info.get("name", "UNMAPPED")
                pct = cnt * 100 // len(buyers_of_id) if buyers_of_id else 0
                print(f"      ID {cid:>3}: {name:<28} {cnt}/{len(buyers_of_id)} ({pct}%)")
    else:
        print(f"  None found - all qty=2 IDs (0-27) are mapped or absent")

    print(f"\n  B) qty=1 IDs (200-255 range) not in ITEM_ID_MAP:")
    unmapped_qty1_ids = sorted(
        iid for iid in all_qty1_counter
        if iid in range(200, 256) and iid not in ITEM_ID_MAP
    )

    if unmapped_qty1_ids:
        print(f"  Found {len(unmapped_qty1_ids)} unmapped ID(s): {unmapped_qty1_ids}")
        print()
        for iid in unmapped_qty1_ids:
            buyers_of_id = [r for r in player_records if iid in r["qty1_ids"]]
            role_dist = Counter(r["role"] for r in buyers_of_id)
            hero_dist = Counter(r["hero"] for r in buyers_of_id)
            global_cnt = all_qty1_counter[iid]

            # Buys per player
            count_dist = Counter(r["qty1_list"].count(iid) for r in buyers_of_id)

            # Timing
            all_ts = [ts for r in player_records for iid2, ts in r["qty1_items"]
                      if iid2 == iid and ts > 0]
            avg_ts = sum(all_ts)/len(all_ts) if all_ts else 0

            print(f"  [FINDING] ID {iid} (qty=1): {len(buyers_of_id)} buyers, {global_cnt} total events")
            print(f"    Roles: {dict(role_dist)}")
            print(f"    Heroes: {dict(hero_dist.most_common(8))}")
            print(f"    Buys/player: {dict(sorted(count_dist.items()))}")
            print(f"    Avg timestamp: {avg_ts:.0f}s")

            # Co-items
            co = Counter()
            for r in buyers_of_id:
                for cid in r["qty1_ids"]:
                    if cid != iid:
                        co[cid] += 1
            n_b = len(buyers_of_id)
            print(f"    Top co-items (qty=1):")
            for cid, cnt in co.most_common(12):
                info = ITEM_ID_MAP.get(cid, {})
                name = info.get("name", "UNMAPPED")
                tier = info.get("tier", "?")
                pct = cnt * 100 // n_b if n_b else 0
                flag = " <<< UNMAPPED" if cid not in ITEM_ID_MAP else ""
                print(f"      ID {cid:>3}: {name:<28} T{tier} {cnt}/{n_b} ({pct}%){flag}")
            print()
    else:
        print(f"  None found - all qty=1 IDs (200-255) are already mapped")

    # =========================================================================
    # FREQUENCY TABLES: Complete view of all observed IDs
    # =========================================================================
    print(f"\n\n{'='*78}")
    print("  FREQUENCY TABLE: All qty=1 IDs (200-255) seen in replays")
    print(f"{'='*78}")
    print(f"  {'ID':>4}  {'Events':>7}  {'Mapped Name':<32}  {'Status'}")
    print(f"  {'-'*70}")
    for iid in range(200, 256):
        cnt = all_qty1_counter.get(iid, 0)
        if cnt == 0:
            continue
        info = ITEM_ID_MAP.get(iid, {})
        name = info.get("name", "*** UNMAPPED ***")
        status = info.get("status", "???")
        flag = " ***" if iid not in ITEM_ID_MAP else ""
        print(f"  {iid:>4}  {cnt:>7}  {name:<32}  {status}{flag}")

    print(f"\n{'='*78}")
    print("  FREQUENCY TABLE: All qty=2 IDs (0-27) seen in replays")
    print(f"{'='*78}")
    print(f"  {'ID':>4}  {'Events':>7}  {'Mapped Name':<32}  {'Status'}")
    print(f"  {'-'*70}")
    for iid in range(0, 28):
        cnt = all_qty2_counter.get(iid, 0)
        if cnt == 0:
            continue
        info = ITEM_ID_MAP.get(iid, {})
        name = info.get("name", "*** UNMAPPED ***")
        status = info.get("status", "???")
        flag = " ***" if iid not in ITEM_ID_MAP and iid not in STARTER_IDS else ""
        print(f"  {iid:>4}  {cnt:>7}  {name:<32}  {status}{flag}")

    # =========================================================================
    # FINAL SUMMARY
    # =========================================================================
    t1 = time.time()
    print(f"\n\n{'='*78}")
    print("  FINAL SUMMARY")
    print(f"{'='*78}")
    print(f"\n  qty=1 IDs seen but NOT mapped (200-255): {sorted(unmapped_qty1_ids)}")
    print(f"  qty=2 IDs seen but NOT mapped (0-27):    {sorted(unmapped_qty2_ids)}")
    print()
    print(f"  Total mapped IDs in ITEM_ID_MAP: {len(ITEM_ID_MAP)}")
    print(f"  Total qty=1 IDs observed:        {len(all_qty1_counter)}")
    print(f"  Total qty=2 IDs observed:        {len(all_qty2_counter)}")
    print(f"\n[STAT:elapsed] {t1-t0:.1f}s")
    print(f"[FINDING] Scan complete. See ANALYSIS sections above for per-candidate detail.")


if __name__ == "__main__":
    main()
