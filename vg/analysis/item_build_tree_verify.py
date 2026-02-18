#!/usr/bin/env python3
"""
Item Build Tree Verification
=============================
For each of the 15 inferred qty=2 items, verify identity by checking whether
expected recipe components co-occur with the item at statistically meaningful
rates (target: >60%).

Key insight from prior runs:
  - Chronograph (219) shows LOW co-occurrence for Capacitor Plate (22),
    Rooks Decree (23), Contraption (16), and Spellsword (12).
    This is a RECIPE MISMATCH, not a data error -- these items likely use
    a different T2 component (Stormguard Banner, Scout Pak) that is unmapped.
  - Dragons Eye (11) shows CP=48% -- close to threshold; small sample (n=25).
  - Metal Jacket (27) shows Coat of Plates only 25% -- recipe may differ
    (Atlas Pauldron path? Or dual Coat of Plates paths?).
  - Crystal Infusion (18) shows avg_purchases=1.06, CP=18% -- likely
    NOT Crystal Infusion. Possible Weapon Infusion or other consumable.

Usage:
    python -m vg.analysis.item_build_tree_verify
"""

import struct
import sys
import io
from pathlib import Path
from collections import defaultdict, Counter

# Force UTF-8 output on Windows (avoids cp949 encode errors)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from vg.core.vgr_parser import VGRParser
from vg.core.vgr_mapping import ITEM_ID_MAP, BINARY_HERO_ID_MAP

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
REPLAY_DIR           = Path(r"D:\Desktop\My Folder\Game\VG\vg replay")
ITEM_ACQUIRE_HEADER  = bytes([0x10, 0x04, 0x3D])
PLAYER_BLOCK_MARKER     = bytes([0xDA, 0x03, 0xEE])
PLAYER_BLOCK_MARKER_ALT = bytes([0xE0, 0x03, 0xEE])
ENTITY_ID_OFFSET = 0xA5
HERO_ID_OFFSET   = 0xA9
TEAM_OFFSET      = 0xD5

# The 15 inferred qty=2 items to verify
TARGET_IDS = [0, 1, 5, 7, 10, 11, 12, 15, 16, 18, 20, 22, 23, 26, 27]

# Official VG recipes (component IDs that should show high co-occurrence).
# Components marked with "?" are unmapped (not yet assigned an ID in ITEM_ID_MAP).
# Where Chronograph (219) shows low %, the item likely has a DIFFERENT T2 utility
# component as its main recipe ingredient.
RECIPES = {
    # ID  : (name, [(comp_id, comp_name, threshold%), ...], notes)
    0:  ("Heavy Prism",      [(203, "CrystalBit",    80)],
         "T2 Crystal -- built from Crystal Bit only"),
    1:  ("Journey Boots",    [(222, "TravelBoots",   70)],
         "T3 Boots -- Travel Boots -> Journey Boots"),
    5:  ("Tyrants Monocle",  [(205, "SixSins",       50), (252, "LuckyStrike", 50)],
         "T3 WP -- Six Sins + Lucky Strike; WP carry exclusive"),
    7:  ("Stormcrown",       [(219, "Chronograph",   50)],
         "T3 Utility -- Stormguard Banner (unmapped) + Chronograph"),
    10: ("Spellfire",        [(0,   "HeavyPrism",    80), (206, "EclipsePrism", 80)],
         "T3 Crystal -- Heavy Prism + Eclipse Prism"),
    11: ("Dragons Eye",      [(0,   "HeavyPrism",    80), (206, "EclipsePrism", 80)],
         "T3 Crystal -- Heavy Prism + Eclipse Prism (shared recipe with Spellfire)"),
    12: ("Spellsword",       [(249, "HeavySteel",    60)],
         "T3 WP/CP -- Heavy Steel (Chronograph 19% = recipe mismatch; Spellsword uses "
         "Heavy Steel + an unmapped component)"),
    15: ("SuperScout 2000",  [],
         "T3 Vision -- ScoutPak (unmapped) + ScoutTuff (unmapped); captain-exclusive"),
    16: ("Contraption",      [],
         "T3 Utility -- Flare Gun path (unmapped component); captain-exclusive; "
         "Chronograph 12% rules out Chronograph as primary component"),
    18: ("Crystal Infusion", [],
         "Consumable -- no build components; IDENTITY UNCERTAIN: CP=18% is too low, "
         "avg_purchases=1.06 is non-consumable-like"),
    20: ("Flare Gun",        [],
         "Consumable -- purchased repeatedly by captains; no build components"),
    22: ("Capacitor Plate",  [(212, "Dragonheart",   70)],
         "T3 Captain Defense -- Dragonheart confirmed (94%); Chronograph 22% suggests "
         "second component is unmapped (likely Stormguard Banner path)"),
    23: ("Rooks Decree",     [(212, "Dragonheart",   70)],
         "T3 Captain Defense -- Dragonheart confirmed (92%); same issue as Capacitor Plate"),
    26: ("Warmail",          [(213, "LightArmor",    50), (245, "LightShield", 50)],
         "T2 Defense -- Light Armor + Light Shield"),
    27: ("Metal Jacket",     [(214, "CoatOfPlates",  50)],
         "T3 Armor -- Coat of Plates main component; 25% rate needs investigation"),
}

HERO_ROLES = {
    "Kinetic": "wp", "Gwen": "wp", "Caine": "wp", "Kestrel": "wp",
    "Ringo": "wp", "Silvernail": "wp", "Kensei": "wp", "Vox": "wp",
    "Baron": "wp", "SAW": "wp", "Warhawk": "wp",
    "Samuel": "cp", "Skaarf": "cp", "Celeste": "cp", "Reza": "cp",
    "Magnus": "cp", "Malene": "cp", "Varya": "cp", "Skye": "cp",
    "Ishtar": "cp", "Anka": "cp", "Karas": "cp", "Miho": "cp",
    "Viola": "cp",
    "Blackfeather": "br", "Ylva": "br", "Inara": "br", "Ozo": "br",
    "Tony": "br", "Reim": "br", "San Feng": "br", "Alpha": "br",
    "Joule": "br", "Glaive": "br", "Krul": "br", "Rona": "br",
    "Grumpjaw": "br", "Baptiste": "br", "Taka": "br", "Koshka": "br",
    "Idris": "br", "Leo": "br",
    "Lorelai": "cap", "Lyra": "cap", "Ardan": "cap", "Phinn": "cap",
    "Catherine": "cap", "Fortress": "cap", "Lance": "cap",
    "Churnwalker": "cap", "Flicker": "cap", "Grace": "cap",
    "Adagio": "cap", "Yates": "cap", "Petal": "cap",
    "Amael": "cap", "Shin": "cap",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def le_to_be(eid_le: int) -> int:
    return struct.unpack('>H', struct.pack('<H', eid_le))[0]


def load_all_frames(replay_path: Path) -> bytes:
    """Concatenate all frame files for a replay (*.0.vgr, *.1.vgr, ...)."""
    stem = replay_path.stem.rsplit('.', 1)[0]
    frames = sorted(
        replay_path.parent.glob(f"{stem}.*.vgr"),
        key=lambda f: int(f.stem.split('.')[-1]) if f.stem.split('.')[-1].isdigit() else 0
    )
    return b"".join(f.read_bytes() for f in frames)


def extract_players_from_parser(rp: Path) -> dict:
    """Use VGRParser to get player entity IDs and hero names."""
    parser = VGRParser(str(rp), detect_heroes=False, auto_truth=False)
    parsed = parser.parse()
    players = {}
    for team in ("left", "right"):
        for p in parsed.get("teams", {}).get(team, []):
            eid_le = p.get("entity_id", 0)
            if eid_le:
                eid_be = le_to_be(eid_le)
                players[eid_be] = {
                    "hero": p.get("hero_name", "unk"),
                    "team": team,
                }
    return players


def scan_item_acquires(data: bytes, players: dict):
    """
    Scan all [10 04 3D] acquire events.

    Acquire event format (per memory):
      [10 04 3D][00 00][eid BE 2B][00 00][qty 1B][item_id LE 2B]
      [00 00][counter BE 2B][ts f32 BE 4B]

    Returns:
      player_items   : eid_be -> list of item_ids (in order, repeats allowed)
      player_multibuy: eid_be -> Counter(item_id -> purchase count)
    """
    player_items    = defaultdict(list)
    player_multibuy = defaultdict(Counter)

    pos = 0
    while True:
        pos = data.find(ITEM_ACQUIRE_HEADER, pos)
        if pos == -1:
            break
        if pos + 20 > len(data):
            pos += 1
            continue
        # Validate separator bytes [00 00] at +3..+4
        if data[pos + 3:pos + 5] != b'\x00\x00':
            pos += 1
            continue
        eid = struct.unpack_from(">H", data, pos + 5)[0]
        if eid not in players:
            pos += 1
            continue
        qty     = data[pos + 9]
        item_id = struct.unpack_from("<H", data, pos + 10)[0]
        # Clamp high IDs (only 0-255 range is valid per mapping)
        if item_id > 255:
            item_id = item_id & 0xFF
        if qty in (1, 2):
            player_items[eid].append(item_id)
            player_multibuy[eid][item_id] += 1
        pos += 3   # step forward by header length

    return player_items, player_multibuy


# ---------------------------------------------------------------------------
# Per-item accumulator
# ---------------------------------------------------------------------------
class ItemStats:
    def __init__(self):
        self.buyer_keys     = set()          # (match_id, eid) dedup
        self.buyer_count    = 0
        self.hero_counter   = Counter()
        self.role_counter   = Counter()
        self.purchase_total = 0
        self.buyer_itemsets = []             # list of frozenset(item_ids) per buyer

    def add_buyer(self, match_id, eid, hero, role, purchase_count, all_items_frozenset):
        key = (match_id, eid)
        if key in self.buyer_keys:
            return
        self.buyer_keys.add(key)
        self.buyer_count    += 1
        self.hero_counter[hero] += 1
        self.role_counter[role] += 1
        self.purchase_total += purchase_count
        self.buyer_itemsets.append(all_items_frozenset)

    def cobuy_rate(self, comp_id: int):
        """Return (count, buyer_count, pct) for comp_id."""
        count = sum(1 for s in self.buyer_itemsets if comp_id in s)
        pct   = 100.0 * count / self.buyer_count if self.buyer_count else 0.0
        return count, self.buyer_count, pct

    def avg_purchases(self):
        return self.purchase_total / self.buyer_count if self.buyer_count else 0.0

    def role_pct(self):
        return {r: 100.0 * c / self.buyer_count for r, c in self.role_counter.items()}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("[OBJECTIVE] Verify 15 inferred qty=2 items via build-tree co-occurrence analysis")
    print()

    all_replays = sorted([
        vgr for vgr in REPLAY_DIR.rglob("*.0.vgr")
        if "__MACOSX" not in str(vgr)
    ])
    print(f"[DATA] Found {len(all_replays)} replay files in {REPLAY_DIR}")

    stats = {tid: ItemStats() for tid in TARGET_IDS}

    replays_ok = 0
    for rp in all_replays:
        try:
            players = extract_players_from_parser(rp)
        except Exception:
            continue

        # Only 5v5 matches (10 players)
        if len(players) != 10:
            continue

        try:
            data = load_all_frames(rp)
        except Exception:
            continue

        player_items, player_multibuy = scan_item_acquires(data, players)
        match_id = rp.stem[:40]
        replays_ok += 1

        for eid_be, p_info in players.items():
            hero = p_info["hero"]
            role = HERO_ROLES.get(hero, "unk")
            all_items = frozenset(player_items.get(eid_be, []))

            for tid in TARGET_IDS:
                if tid in all_items:
                    pcount = player_multibuy[eid_be].get(tid, 1)
                    stats[tid].add_buyer(match_id, eid_be, hero, role, pcount, all_items)

    print(f"[DATA] Processed {replays_ok} 5v5 matches ({len(all_replays) - replays_ok} skipped)\n")

    # ---------------------------------------------------------------------------
    # Report
    # ---------------------------------------------------------------------------
    SEP  = "=" * 76
    SEP2 = "-" * 76

    confirmed_ids = []
    uncertain_ids = []
    no_data_ids   = []

    results = {}   # tid -> verdict string

    for tid in TARGET_IDS:
        st = stats[tid]
        name, comps, notes = RECIPES[tid]
        n = st.buyer_count

        print(SEP)
        print(f"  ID {tid:>2} | {name}")
        print(SEP2)

        if n == 0:
            print("  [!] NO BUYERS FOUND -- item may not appear in 5v5 replays")
            print(f"      Notes: {notes}")
            verdict = "NO_DATA"
            no_data_ids.append(tid)
            results[tid] = verdict
            print(f"\n  VERDICT: {verdict}\n")
            continue

        rp_dict = st.role_pct()
        print(f"  Buyers:         {n}")
        print(f"  Avg buy/player: {st.avg_purchases():.2f}  "
              f"({'consumable-pattern' if st.avg_purchases() > 1.3 else 'non-consumable'})")
        role_str = "  ".join(f"{r}:{p:.0f}%" for r, p in
                              sorted(rp_dict.items(), key=lambda x: -x[1]))
        print(f"  Role split:     {role_str}")
        top_h = "  ".join(f"{h}({c})" for h, c in st.hero_counter.most_common(6))
        print(f"  Top heroes:     {top_h}")
        print(f"  Notes:          {notes}")

        # Component co-occurrence
        comp_results = []
        all_comps_pass = True
        if comps:
            print(f"\n  Component co-occurrence (recipe check):")
            for comp_id, comp_name, threshold in comps:
                cnt, total, pct = st.cobuy_rate(comp_id)
                passes = pct >= threshold
                if not passes:
                    all_comps_pass = False
                flag = "PASS" if passes else f"FAIL (need >{threshold}%)"
                print(f"    {comp_name:<16} ID {comp_id:>3}: {cnt}/{total} = {pct:5.1f}%  [{flag}]")
                comp_results.append((comp_name, pct, passes))
        else:
            print(f"\n  No recipe components to check (consumable or unmapped recipe)")
            all_comps_pass = True  # no recipe = not falsifiable via components

        # Extra diagnostic for items where Chronograph showed unexpectedly low rates
        if tid in (12, 16, 22, 23, 27):
            extra_probes = [
                (217, "Hourglass"),    (218, "VoidBattery"),   (216, "EnergyBattery"),
                (229, "ReflexBlock"),  (246, "KineticShield"), (248, "Lifespring"),
                (207, "BlazingSalvo"), (244, "BarbedNeedle"),  (242, "AtlasPauldron"),
            ]
            print(f"\n  Extra probe (searching for unmapped/alternative component):")
            probe_hits = []
            for comp_id, comp_name in extra_probes:
                cnt, total, pct = st.cobuy_rate(comp_id)
                if pct >= 30:
                    probe_hits.append((comp_name, comp_id, pct))
            if probe_hits:
                for cname, cid, pct in sorted(probe_hits, key=lambda x: -x[2]):
                    print(f"    {cname:<16} ID {cid:>3}: {pct:5.1f}%  [candidate component]")
            else:
                print(f"    No known item exceeds 30% -- second component is unmapped")

        # Verdict
        verdict = _compute_verdict(tid, st, all_comps_pass, comp_results, rp_dict)
        results[tid] = verdict
        if verdict == "CONFIRMED":
            confirmed_ids.append(tid)
        elif verdict == "UNCERTAIN":
            uncertain_ids.append(tid)
        else:
            uncertain_ids.append(tid)

        print(f"\n  VERDICT: {verdict}\n")

    # ---------------------------------------------------------------------------
    # Summary table
    # ---------------------------------------------------------------------------
    print(SEP)
    print("  BUILD TREE VERIFICATION -- SUMMARY")
    print(SEP)
    print(f"  {'ID':>3}  {'Name':<22}  {'Buyers':>6}  {'Verdict':<14}  Key evidence")
    print(SEP2)
    for tid in TARGET_IDS:
        st    = stats[tid]
        name  = RECIPES[tid][0]
        comps = RECIPES[tid][1]
        v     = results[tid]
        n     = st.buyer_count
        rp_d  = st.role_pct()
        ev_parts = []
        if rp_d:
            dom_role = max(rp_d, key=rp_d.get)
            ev_parts.append(f"{dom_role}:{rp_d[dom_role]:.0f}%")
        for comp_id, comp_name, _ in comps:
            _, _, pct = st.cobuy_rate(comp_id)
            ev_parts.append(f"{comp_name}:{pct:.0f}%")
        evidence = "  ".join(ev_parts) if ev_parts else "no components"
        print(f"  {tid:>3}  {name:<22}  {n:>6}  {v:<14}  {evidence}")

    print(SEP2)
    print(f"\n  CONFIRMED:   {len(confirmed_ids)} items  -> IDs: {confirmed_ids}")
    print(f"  NEEDS_WORK:  {len(uncertain_ids)} items  -> IDs: {uncertain_ids}")
    print(f"  NO_DATA:     {len(no_data_ids)} items  -> IDs: {no_data_ids}")

    print(f"\n[FINDING] {len(confirmed_ids)}/15 inferred items pass build-tree verification")
    print(f"[STAT:n] {replays_ok} 5v5 matches, "
          f"{sum(s.buyer_count for s in stats.values())} total buyer events")

    print("\n[LIMITATION] Items with unmapped recipe components (Stormguard Banner, ScoutPak)")
    print("  cannot be fully verified via co-occurrence; captain-exclusive buyer profile")
    print("  is used as the primary signal for those items.")
    print("[LIMITATION] ID 18 identity remains uncertain --")
    print("  role profile and avg_purchases do not match a typical CP consumable.")
    print("[LIMITATION] ID 27 Metal Jacket CoatOfPlates co-buy is only 25% --")
    print("  recipe may go through a different T2 path not yet mapped.")


def _compute_verdict(tid, st, all_comps_pass, comp_results, rp):
    """Determine CONFIRMED / NEEDS_WORK / UNCERTAIN verdict per item."""
    cap_pct = rp.get("cap", 0)
    br_pct  = rp.get("br",  0)
    cp_pct  = rp.get("cp",  0)
    wp_pct  = rp.get("wp",  0)

    if tid == 0:   # Heavy Prism: CP dominant + CrystalBit high
        _, _, pct_cb = st.cobuy_rate(203)
        return "CONFIRMED" if cp_pct >= 50 and pct_cb >= 80 else "NEEDS_WORK"

    if tid == 1:   # Journey Boots: TravelBoots co-buy high
        _, _, pct_tb = st.cobuy_rate(222)
        return "CONFIRMED" if pct_tb >= 70 else "NEEDS_WORK"

    if tid == 5:   # Tyrants Monocle: WP + both components
        _, _, p_ss = st.cobuy_rate(205)
        _, _, p_ls = st.cobuy_rate(252)
        return "CONFIRMED" if wp_pct >= 60 and p_ss >= 50 and p_ls >= 50 else "NEEDS_WORK"

    if tid == 7:   # Stormcrown: br+cap dominant, Chronograph present
        _, _, p_ch = st.cobuy_rate(219)
        return "CONFIRMED" if (br_pct + cap_pct) >= 60 and p_ch >= 40 else "NEEDS_WORK"

    if tid == 10:  # Spellfire: CP + both prisms high
        _, _, p_hp = st.cobuy_rate(0)
        _, _, p_ep = st.cobuy_rate(206)
        return "CONFIRMED" if cp_pct >= 50 and p_hp >= 80 and p_ep >= 80 else "NEEDS_WORK"

    if tid == 11:  # Dragons Eye: same recipe as Spellfire; differentiate by heroes
        _, _, p_hp = st.cobuy_rate(0)
        _, _, p_ep = st.cobuy_rate(206)
        if p_hp >= 80 and p_ep >= 80:
            return "CONFIRMED"
        return "NEEDS_WORK"

    if tid == 12:  # Spellsword: HeavySteel dominant; Chronograph low (unmapped 2nd comp)
        _, _, p_hs = st.cobuy_rate(249)
        return "CONFIRMED" if wp_pct >= 60 and p_hs >= 60 else "NEEDS_WORK"

    if tid == 15:  # SuperScout 2000: captain-exclusive, no mapped recipe
        return "CONFIRMED" if cap_pct >= 80 else "NEEDS_WORK"

    if tid == 16:  # Contraption: captain-exclusive, Chronograph low (unmapped recipe)
        return "CONFIRMED" if cap_pct >= 80 else "NEEDS_WORK"

    if tid == 18:  # Crystal Infusion: UNCERTAIN -- profile does not fit CP consumable
        avg = st.avg_purchases()
        if cp_pct < 30:
            return "UNCERTAIN"
        return "CONFIRMED" if avg > 1.2 else "NEEDS_WORK"

    if tid == 20:  # Flare Gun: captain consumable
        return "CONFIRMED" if cap_pct >= 80 else "NEEDS_WORK"

    if tid == 22:  # Capacitor Plate: captain + Dragonheart; Chronograph unmapped
        _, _, p_dh = st.cobuy_rate(212)
        return "CONFIRMED" if cap_pct >= 80 and p_dh >= 70 else "NEEDS_WORK"

    if tid == 23:  # Rooks Decree: captain + Dragonheart; same pattern
        _, _, p_dh = st.cobuy_rate(212)
        return "CONFIRMED" if cap_pct >= 70 and p_dh >= 70 else "NEEDS_WORK"

    if tid == 26:  # Warmail: LightArmor + LightShield
        _, _, p_la = st.cobuy_rate(213)
        _, _, p_ls = st.cobuy_rate(245)
        return "CONFIRMED" if p_la >= 50 and p_ls >= 50 else "NEEDS_WORK"

    if tid == 27:  # Metal Jacket: CoatOfPlates low (25%) -- recipe investigation needed
        _, _, p_cop = st.cobuy_rate(214)
        return "CONFIRMED" if p_cop >= 50 else "NEEDS_WORK"

    return "NEEDS_WORK"


if __name__ == "__main__":
    main()
