#!/usr/bin/env python3
"""
Item Remaining Verification - Build Tree Co-buy Analysis
=========================================================
For each inferred/tentative item ID, verify identity by checking:
  1. Buyer count and role distribution
  2. Multi-buy count (consumable indicator)
  3. Component co-buy rates (recipe validation)
  4. CONFIRMED / NEEDS_REVIEW verdict

Target IDs:
  qty=2 inferred: 0,1,5,7,10,11,12,15,16,18,20,22,23,26,27
  tentative:      215, 225, 228

Usage:
    python -m vg.analysis.item_remaining_verify
"""

import sys
import struct
from pathlib import Path
from collections import defaultdict, Counter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from vg.core.vgr_parser import VGRParser
from vg.core.vgr_mapping import ITEM_ID_MAP

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ITEM_ACQUIRE_HEADER = bytes([0x10, 0x04, 0x3D])
REPLAY_DIR = Path(r"D:\Desktop\My Folder\Game\VG\vg replay")

PLAYER_BLOCK_MARKER     = bytes([0xDA, 0x03, 0xEE])
PLAYER_BLOCK_MARKER_ALT = bytes([0xE0, 0x03, 0xEE])
ENTITY_ID_OFFSET = 0xA5
HERO_ID_OFFSET   = 0xA9
TEAM_OFFSET      = 0xD5

# IDs to investigate (inferred + tentative)
TARGET_IDS = [0, 1, 5, 7, 10, 11, 12, 15, 16, 18, 20, 22, 23, 26, 27,
              215, 225, 228]

# Expected recipes: target_id -> list of component IDs that should show high co-buy %
EXPECTED_RECIPES = {
    0:   [203],                # Heavy Prism <- Crystal Bit
    1:   [222],                # Journey Boots <- Travel Boots only
    5:   [205, 252],           # Tyrants Monocle <- Six Sins + Lucky Strike
    7:   [219],                # Stormcrown <- Chronograph (+ Stormguard Banner unmapped)
    10:  [0, 206],             # Spellfire <- Heavy Prism + Eclipse Prism
    11:  [0, 206],             # Dragons Eye <- Heavy Prism + Eclipse Prism
    12:  [249, 219],           # Spellsword <- Heavy Steel + Chronograph
    15:  [],                   # SuperScout 2000 - captain vision; no standard recipe
    16:  [219],                # Contraption <- Chronograph (+ Flare Gun unmapped)
    18:  [],                   # Crystal Infusion - consumable; no components
    20:  [],                   # Flare Gun - consumable; no components
    22:  [212, 219],           # Capacitor Plate <- Dragonheart + Chronograph
    23:  [212, 219],           # Rooks Decree <- Dragonheart + Chronograph
    26:  [213, 245],           # Warmail <- Light Armor + Light Shield
    27:  [214],                # Metal Jacket <- Coat of Plates
    215: [214],                # Light Armor variant? check Coat of Plates co-buy
    225: [],                   # Scout Trap - consumable
    228: [213],                # Coat of Plates variant? check Light Armor co-buy
}

# Hero-role lookup (from existing scripts)
HERO_ROLES = {
    "Kinetic": "wp", "Gwen": "wp", "Caine": "wp", "Kestrel": "wp",
    "Ringo": "wp", "Silvernail": "wp", "Kensei": "wp", "Vox": "wp",
    "Baron": "wp", "SAW": "wp", "Warhawk": "wp",
    "Samuel": "cp", "Skaarf": "cp", "Celeste": "cp", "Reza": "cp",
    "Magnus": "cp", "Malene": "cp", "Varya": "cp",
    "Skye": "cp", "Ishtar": "cp", "Anka": "cp",
    "Blackfeather": "br", "Ylva": "br", "Inara": "br", "Ozo": "br",
    "Tony": "br", "Reim": "br", "San Feng": "br", "Alpha": "br",
    "Joule": "br", "Glaive": "br", "Krul": "br", "Rona": "br",
    "Grumpjaw": "br", "Baptiste": "br", "Taka": "br", "Koshka": "br",
    "Lorelai": "cap", "Lyra": "cap", "Ardan": "cap", "Phinn": "cap",
    "Catherine": "cap", "Fortress": "cap", "Lance": "cap",
    "Churnwalker": "cap", "Flicker": "cap", "Grace": "cap",
    "Adagio": "cap", "Yates": "cap", "Petal": "cap",
    "Idris": "br", "Ozo": "br", "Leo": "br",
    "Miho": "cp", "Shin": "cap", "Amael": "cap", "Karas": "cp",
    "Viola": "cp",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def le_to_be(eid_le: int) -> int:
    return struct.unpack('>H', struct.pack('<H', eid_le))[0]


def load_all_frames(replay_path: Path) -> bytes:
    stem = replay_path.stem.rsplit('.', 1)[0]
    frames = sorted(
        replay_path.parent.glob(f"{stem}.*.vgr"),
        key=lambda f: (int(f.stem.split('.')[-1])
                       if f.stem.split('.')[-1].isdigit() else 0)
    )
    return b"".join(f.read_bytes() for f in frames)


def extract_players(data: bytes) -> dict:
    """Return {eid_be: {hero, team}} from player blocks."""
    players = {}
    seen_eids = set()
    from vg.core.vgr_mapping import BINARY_HERO_ID_MAP
    for marker in (PLAYER_BLOCK_MARKER, PLAYER_BLOCK_MARKER_ALT):
        pos = 0
        while True:
            pos = data.find(marker, pos)
            if pos == -1:
                break
            block_start = pos
            eid_pos = block_start + ENTITY_ID_OFFSET
            if eid_pos + 2 > len(data):
                pos += 1
                continue
            eid_le = struct.unpack_from('<H', data, eid_pos)[0]
            if eid_le == 0 or eid_le in seen_eids:
                pos += 1
                continue
            hero_pos = block_start + HERO_ID_OFFSET
            if hero_pos + 2 > len(data):
                pos += 1
                continue
            hero_id = struct.unpack_from('<H', data, hero_pos)[0]
            hero_name = BINARY_HERO_ID_MAP.get(hero_id, f"unk_{hero_id:04X}")
            team_pos = block_start + TEAM_OFFSET
            team = data[team_pos] if team_pos < len(data) else 0
            eid_be = le_to_be(eid_le)
            seen_eids.add(eid_le)
            players[eid_be] = {"hero": hero_name, "team": team}
            pos += 1
    return players


def scan_items(data: bytes, players: dict):
    """
    Scan all acquire events.
    Returns per-player item lists and multi-buy counts.
    player_items:  eid_be -> list of item_ids (in purchase order, with repeats)
    player_multibuy: eid_be -> Counter(item_id -> total purchases)
    """
    player_items   = defaultdict(list)
    player_multibuy = defaultdict(Counter)

    pos = 0
    while True:
        pos = data.find(ITEM_ACQUIRE_HEADER, pos)
        if pos == -1:
            break
        if pos + 20 > len(data):
            pos += 1
            continue
        if data[pos + 3:pos + 5] != b'\x00\x00':
            pos += 1
            continue
        eid = struct.unpack_from(">H", data, pos + 5)[0]
        if eid not in players:
            pos += 1
            continue
        qty     = data[pos + 9]
        item_id = struct.unpack_from("<H", data, pos + 10)[0]
        if item_id > 255:
            item_id = item_id & 0xFF
        if qty in (1, 2):
            player_items[eid].append(item_id)
            player_multibuy[eid][item_id] += 1
        pos += 3

    return player_items, player_multibuy


# ---------------------------------------------------------------------------
# Per-item statistics accumulator
# ---------------------------------------------------------------------------
class ItemStats:
    def __init__(self):
        # buyers: set of (match_id, eid)
        self.buyer_keys   = []          # list of (match_id, eid)
        self.hero_counter = Counter()
        self.role_counter = Counter()
        self.multibuy_total = 0         # sum of purchase counts across all buyers
        self.buyer_count  = 0
        # co-buy: for each component, how many buyers also bought it
        self.component_cobuys = defaultdict(int)  # comp_id -> # buyers who also bought it
        # all items each buyer purchased (for computing co-buy)
        self.buyer_all_items = []       # list of set(item_ids) per buyer

    def add_buyer(self, match_id, eid, hero, role, purchase_count, all_items_set):
        key = (match_id, eid)
        if key in self.buyer_keys:
            return  # deduplicate within match
        self.buyer_keys.append(key)
        self.buyer_count += 1
        self.hero_counter[hero] += 1
        self.role_counter[role] += 1
        self.multibuy_total += purchase_count
        self.buyer_all_items.append(all_items_set)

    def compute_cobuys(self, component_ids):
        results = {}
        for comp in component_ids:
            count = sum(1 for s in self.buyer_all_items if comp in s)
            results[comp] = (count, self.buyer_count,
                             100.0 * count / self.buyer_count if self.buyer_count else 0)
        return results

    def avg_purchases(self):
        return self.multibuy_total / self.buyer_count if self.buyer_count else 0


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------
def main():
    # Find all 5v5 replays (base frames only)
    all_replays = sorted([
        vgr for vgr in REPLAY_DIR.rglob("*.0.vgr")
        if "__MACOSX" not in str(vgr)
    ])
    print(f"Found {len(all_replays)} replay files")

    # Filter to 5v5 (skip Blitz/Practice by checking team sizes)
    # We'll analyse all and count 5v5 by player count
    stats = {tid: ItemStats() for tid in TARGET_IDS}

    replays_processed = 0
    for rp in all_replays:
        try:
            # Quick hero parse for player identification
            parser = VGRParser(str(rp), detect_heroes=False, auto_truth=False)
            parsed = parser.parse()
        except Exception as e:
            continue

        # Build player eid_be -> hero mapping from parser output
        parser_players = {}
        player_count = 0
        for team in ("left", "right"):
            for p in parsed.get("teams", {}).get(team, []):
                eid_le = p.get("entity_id", 0)
                if eid_le:
                    eid_be = le_to_be(eid_le)
                    parser_players[eid_be] = {
                        "hero": p.get("hero_name", "unk"),
                        "team": team,
                    }
                    player_count += 1

        # Only process 5v5 matches (10 players)
        if player_count != 10:
            continue

        # Load binary data
        try:
            data = load_all_frames(rp)
        except Exception:
            continue

        # Scan items
        player_items, player_multibuy = scan_items(data, parser_players)

        match_id = rp.stem[:40]
        replays_processed += 1

        # For each player, accumulate stats for each target ID they bought
        for eid_be, p_info in parser_players.items():
            hero = p_info["hero"]
            role = HERO_ROLES.get(hero, "unk")
            all_items = set(player_items.get(eid_be, []))

            for tid in TARGET_IDS:
                if tid in all_items:
                    purchase_count = player_multibuy[eid_be].get(tid, 1)
                    stats[tid].add_buyer(match_id, eid_be, hero, role,
                                         purchase_count, all_items)

    print(f"Processed {replays_processed} 5v5 matches\n")

    # ---------------------------------------------------------------------------
    # Print verdicts
    # ---------------------------------------------------------------------------
    # Item name lookup (inferred)
    INFERRED_NAMES = {
        0: "Heavy Prism (Crystal T2, 1050g)",
        1: "Journey Boots (Utility T3, 1700g)",
        5: "Tyrants Monocle (Weapon T3, 2750g)",
        7: "Stormcrown (Utility T3, 2000g)",
        10: "Spellfire (Crystal T3, 2700g)",
        11: "Dragons Eye (Crystal T3, 3000g)",
        12: "Spellsword (Weapon T3, 2800g)",
        15: "SuperScout 2000 (Utility T3, 2000g)",
        16: "Contraption (Utility T3, 2100g)",
        18: "Crystal Infusion (Consumable, 500g)",
        20: "Flare Gun (Consumable, 50g)",
        22: "Capacitor Plate (Defense T3, 2100g)",
        23: "Rooks Decree (Defense T3, 2200g)",
        26: "Warmail (Defense T2, 800g)",
        27: "Metal Jacket (Defense T3, 2000g)",
        215: "Light Armor variant (Defense T1)",
        225: "Scout Trap (Consumable)",
        228: "Coat of Plates variant (Defense T2)",
    }

    COMPONENT_NAMES = {
        0: "HeavyPrism", 203: "CrystalBit", 206: "EclipsePrism",
        205: "SixSins", 252: "LuckyStrike", 207: "BlazingSalvo",
        249: "HeavySteel", 250: "PiercingSpear", 244: "BarbedNeedle",
        219: "Chronograph", 218: "VoidBattery", 216: "EnergyBattery",
        217: "Hourglass", 212: "Dragonheart", 248: "Lifespring",
        229: "ReflexBlock", 211: "Oakheart", 214: "CoatOfPlates",
        246: "KineticShield", 213: "LightArmor", 245: "LightShield",
        222: "TravelBoots", 221: "SprintBoots",
    }

    sep = "=" * 80

    for tid in TARGET_IDS:
        st = stats[tid]
        n = st.buyer_count
        expected_name = INFERRED_NAMES.get(tid, f"ID {tid}")
        components = EXPECTED_RECIPES.get(tid, [])

        print(sep)
        print(f"ID {tid:>3}  |  {expected_name}")
        print(sep)

        if n == 0:
            print("  [!] NO BUYERS FOUND in dataset")
            print("  VERDICT: NEEDS_REVIEW (no data)\n")
            continue

        # Buyer count
        print(f"  Buyers:        {n}")
        print(f"  Avg purchases: {st.avg_purchases():.2f}  "
              f"({'consumable' if st.avg_purchases() > 1.3 else 'non-consumable'})")

        # Role distribution
        role_pct = {r: 100.0 * c / n for r, c in st.role_counter.items()}
        role_str = "  ".join(f"{r}:{pct:.0f}%" for r, pct in
                              sorted(role_pct.items(), key=lambda x: -x[1]))
        print(f"  Roles:         {role_str}")

        # Top heroes
        top_heroes = st.hero_counter.most_common(6)
        hero_str = "  ".join(f"{h}({c})" for h, c in top_heroes)
        print(f"  Top heroes:    {hero_str}")

        # Component co-buy rates
        if components:
            cobuys = st.compute_cobuys(components)
            print(f"  Component co-buy rates (recipe check):")
            all_match = True
            for comp_id, (cnt, total, pct) in cobuys.items():
                cname = COMPONENT_NAMES.get(comp_id, f"ID{comp_id}")
                flag = "OK" if pct >= 50 else "LOW"
                if pct < 50:
                    all_match = False
                print(f"    {cname:16s} (ID {comp_id:3d}): {cnt}/{total} = {pct:.0f}%  [{flag}]")
        else:
            all_match = True  # no recipe to check (consumable)

        # Verdict logic
        consumable_flag = (st.avg_purchases() > 1.3)
        role_dominant   = max(role_pct.values()) if role_pct else 0

        # Item-specific verdicts
        verdict = "NEEDS_REVIEW"
        reason  = ""

        if tid == 0:   # Heavy Prism: all CP, Crystal Bit co-buy high
            cb = st.compute_cobuys([203])
            pct_cb = cb[203][2]
            cp_pct = role_pct.get("cp", 0)
            if cp_pct >= 60 and pct_cb >= 60:
                verdict = "CONFIRMED"
                reason  = f"CP-dominant ({cp_pct:.0f}%), CrystalBit co-buy {pct_cb:.0f}%"
            else:
                reason  = f"CP={cp_pct:.0f}%, CrystalBit={pct_cb:.0f}%"

        elif tid == 1:  # Journey Boots: melee/br heavy, Travel Boots
            cb = st.compute_cobuys([222])
            pct_tb = cb[222][2]
            br_pct  = role_pct.get("br", 0) + role_pct.get("cap", 0)
            wp_pct  = role_pct.get("wp", 0)
            if pct_tb >= 60:
                verdict = "CONFIRMED"
                reason  = f"TravelBoots co-buy {pct_tb:.0f}%, melee+cap={br_pct:.0f}%"
            else:
                reason  = f"TravelBoots co-buy only {pct_tb:.0f}%"

        elif tid == 5:  # Tyrants Monocle: WP, Six Sins + Lucky Strike
            cb = st.compute_cobuys([205, 252])
            p_ss = cb[205][2]; p_ls = cb[252][2]
            wp_pct = role_pct.get("wp", 0)
            if wp_pct >= 60 and p_ss >= 40 and p_ls >= 40:
                verdict = "CONFIRMED"
                reason  = f"WP {wp_pct:.0f}%, SixSins {p_ss:.0f}%, LuckyStrike {p_ls:.0f}%"
            else:
                reason  = f"WP={wp_pct:.0f}%, SixSins={p_ss:.0f}%, LuckyStrike={p_ls:.0f}%"

        elif tid == 7:  # Stormcrown: junglers/br, Chronograph
            cb = st.compute_cobuys([219])
            p_ch = cb[219][2]
            br_pct = role_pct.get("br", 0) + role_pct.get("cap", 0)
            if p_ch >= 50 and br_pct >= 40:
                verdict = "CONFIRMED"
                reason  = f"Chronograph {p_ch:.0f}%, br+cap {br_pct:.0f}%"
            else:
                reason  = f"Chronograph={p_ch:.0f}%, br+cap={br_pct:.0f}%"

        elif tid == 10:  # Spellfire: CP, Heavy Prism + Eclipse Prism
            cb = st.compute_cobuys([0, 206])
            p_hp = cb[0][2]; p_ep = cb[206][2]
            cp_pct = role_pct.get("cp", 0)
            if cp_pct >= 50 and p_ep >= 50:
                verdict = "CONFIRMED"
                reason  = f"CP {cp_pct:.0f}%, EclipsePrism {p_ep:.0f}%, HeavyPrism {p_hp:.0f}%"
            else:
                reason  = f"CP={cp_pct:.0f}%, HeavyPrism={p_hp:.0f}%, EclipsePrism={p_ep:.0f}%"

        elif tid == 11:  # Dragons Eye: CP, Heavy Prism + Eclipse Prism
            cb = st.compute_cobuys([0, 206])
            p_hp = cb[0][2]; p_ep = cb[206][2]
            cp_pct = role_pct.get("cp", 0)
            if cp_pct >= 50 and p_ep >= 50:
                verdict = "CONFIRMED"
                reason  = f"CP {cp_pct:.0f}%, EclipsePrism {p_ep:.0f}%, HeavyPrism {p_hp:.0f}%"
            else:
                reason  = f"CP={cp_pct:.0f}%, HeavyPrism={p_hp:.0f}%, EclipsePrism={p_ep:.0f}%"

        elif tid == 12:  # Spellsword: Heavy Steel + Chronograph, Caine dominant
            cb = st.compute_cobuys([249, 219])
            p_hs = cb[249][2]; p_ch = cb[219][2]
            if p_hs >= 40 and p_ch >= 40:
                verdict = "CONFIRMED"
                reason  = f"HeavySteel {p_hs:.0f}%, Chronograph {p_ch:.0f}%"
            else:
                reason  = f"HeavySteel={p_hs:.0f}%, Chronograph={p_ch:.0f}%"

        elif tid == 15:  # SuperScout 2000: ALL captains
            cap_pct = role_pct.get("cap", 0)
            if cap_pct >= 80:
                verdict = "CONFIRMED"
                reason  = f"Captain-exclusive {cap_pct:.0f}%"
            else:
                reason  = f"Captain only {cap_pct:.0f}%"

        elif tid == 16:  # Contraption: ALL captains, Chronograph
            cb = st.compute_cobuys([219])
            p_ch = cb[219][2]
            cap_pct = role_pct.get("cap", 0)
            if cap_pct >= 80 and p_ch >= 50:
                verdict = "CONFIRMED"
                reason  = f"Captain {cap_pct:.0f}%, Chronograph {p_ch:.0f}%"
            else:
                reason  = f"Captain={cap_pct:.0f}%, Chronograph={p_ch:.0f}%"

        elif tid == 18:  # Crystal Infusion: multi-buy, CP-heavy
            cp_pct = role_pct.get("cp", 0)
            if consumable_flag and cp_pct >= 40:
                verdict = "CONFIRMED"
                reason  = f"Consumable (avg {st.avg_purchases():.1f}x), CP {cp_pct:.0f}%"
            elif consumable_flag:
                verdict = "CONFIRMED"
                reason  = f"Consumable pattern (avg {st.avg_purchases():.1f}x per buyer)"
            else:
                reason  = f"avg_purchases={st.avg_purchases():.2f}, CP={cp_pct:.0f}%"

        elif tid == 20:  # Flare Gun: ALL captains, consumable
            cap_pct = role_pct.get("cap", 0)
            if cap_pct >= 80 and consumable_flag:
                verdict = "CONFIRMED"
                reason  = f"Captain {cap_pct:.0f}%, consumable avg {st.avg_purchases():.1f}x"
            elif cap_pct >= 80:
                verdict = "CONFIRMED"
                reason  = f"Captain-exclusive {cap_pct:.0f}%"
            else:
                reason  = f"Captain={cap_pct:.0f}%, avg={st.avg_purchases():.2f}"

        elif tid == 22:  # Capacitor Plate: ALL captains, Dragonheart+Chronograph
            cb = st.compute_cobuys([212, 219])
            p_dh = cb[212][2]; p_ch = cb[219][2]
            cap_pct = role_pct.get("cap", 0)
            if cap_pct >= 80 and p_dh >= 50 and p_ch >= 50:
                verdict = "CONFIRMED"
                reason  = f"Captain {cap_pct:.0f}%, Dragonheart {p_dh:.0f}%, Chronograph {p_ch:.0f}%"
            else:
                reason  = f"Captain={cap_pct:.0f}%, Dragonheart={p_dh:.0f}%, Chronograph={p_ch:.0f}%"

        elif tid == 23:  # Rooks Decree: ALL captains, Dragonheart+Chronograph
            cb = st.compute_cobuys([212, 219])
            p_dh = cb[212][2]; p_ch = cb[219][2]
            cap_pct = role_pct.get("cap", 0)
            if cap_pct >= 80 and p_dh >= 50 and p_ch >= 50:
                verdict = "CONFIRMED"
                reason  = f"Captain {cap_pct:.0f}%, Dragonheart {p_dh:.0f}%, Chronograph {p_ch:.0f}%"
            else:
                reason  = f"Captain={cap_pct:.0f}%, Dragonheart={p_dh:.0f}%, Chronograph={p_ch:.0f}%"

        elif tid == 26:  # Warmail: Light Armor + Light Shield
            cb = st.compute_cobuys([213, 245])
            p_la = cb[213][2]; p_ls = cb[245][2]
            if p_la >= 50 and p_ls >= 50:
                verdict = "CONFIRMED"
                reason  = f"LightArmor {p_la:.0f}%, LightShield {p_ls:.0f}%"
            else:
                reason  = f"LightArmor={p_la:.0f}%, LightShield={p_ls:.0f}%"

        elif tid == 27:  # Metal Jacket: Coat of Plates
            cb = st.compute_cobuys([214])
            p_cop = cb[214][2]
            if p_cop >= 50:
                verdict = "CONFIRMED"
                reason  = f"CoatOfPlates {p_cop:.0f}%"
            else:
                reason  = f"CoatOfPlates only {p_cop:.0f}%"

        elif tid == 215:  # Light Armor variant: check Coat of Plates
            cb = st.compute_cobuys([214])
            p_cop = cb[214][2]
            reason  = f"CoatOfPlates co-buy {p_cop:.0f}%"
            if p_cop >= 60:
                verdict = "CONFIRMED"
                reason += " -> likely Light Armor (same ID variant)"
            else:
                reason += " -> unclear; may be duplicate Light Armor"

        elif tid == 225:  # Scout Trap: consumable, captain
            cap_pct = role_pct.get("cap", 0)
            if consumable_flag and cap_pct >= 60:
                verdict = "CONFIRMED"
                reason  = f"Consumable avg {st.avg_purchases():.1f}x, Captain {cap_pct:.0f}%"
            else:
                reason  = f"avg={st.avg_purchases():.2f}, Captain={cap_pct:.0f}%"

        elif tid == 228:  # Coat of Plates variant: check
            cb = st.compute_cobuys([213])
            p_la = cb[213][2]
            cop_rate = st.compute_cobuys([214])
            p_cop214 = cop_rate[214][2]
            reason = f"LightArmor={p_la:.0f}%, CoatOfPlates214={p_cop214:.0f}%"
            if n <= 5:
                verdict = "NEEDS_REVIEW"
                reason += f" (only {n} buyers - may be misidentified)"
            elif p_la >= 60:
                verdict = "CONFIRMED"
                reason += " -> Coat of Plates variant"

        print(f"\n  VERDICT: {verdict}")
        print(f"  REASON:  {reason}\n")

    print(sep)
    print("SUMMARY")
    print(sep)
    confirmed = [tid for tid in TARGET_IDS
                 if stats[tid].buyer_count > 0]
    print(f"Total target IDs analyzed: {len(TARGET_IDS)}")
    for tid in TARGET_IDS:
        st = stats[tid]
        n  = st.buyer_count
        iname = INFERRED_NAMES.get(tid, f"ID {tid}")
        print(f"  ID {tid:>3}  buyers={n:>3}  {iname}")


if __name__ == "__main__":
    main()
