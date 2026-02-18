#!/usr/bin/env python3
"""
truth_item_comparison.py

Compares Korean truth item data (matches 1-4) against decoder English output.
Also scans matches 5-11 for unknown items, Stormguard Banner, and Shiversteel.
"""

import json
import re
import sys
from collections import defaultdict

# ============================================================
# 1. KOREAN -> ENGLISH ITEM NAME MAPPING
# ============================================================

KO_TO_EN = {
    # Defense T3
    "경비대의 깃발": "Stormguard Banner",
    "경비대의 길밧": "Stormguard Banner",  # typo variant from match 2
    "도가니": "Crucible",
    "재생의 분수": "Fountain of Renewal",
    "재생의 샘": "Lifespring",
    "생명의 샘": "Lifespring",
    "천상의 장막": "Slumbering Husk",       # 'celestial curtain' = Slumbering Husk
    "거대괴수": "Slumbering Husk",
    "거대괴수 갑주": "Slumbering Husk",
    "거인의 견갑": "Atlas Pauldron",
    "이지스": "Aegis",
    "반사의 완갑": "Reflex Block",
    "반응형 장갑": "Kinetic Shield",
    "용심장": "Dragonheart",               # T2 defense component
    "떡갈나무 심장": "Oakheart",
    "떡갈나무심장": "Oakheart",
    "작은방패": "Light Shield",
    "작은 방패": "Light Shield",
    "가죽 갑옷": "Light Armor",
    "전쟁 갑옷": "Warmail",
    "전쟁갑옷": "Warmail",
    "판금 흉갑": "Metal Jacket",

    # Utility / Boots
    "폭풍우 왕관": "Stormcrown",
    "전쟁걸음": "War Treads",
    "전쟁 걸음": "War Treads",
    "척력장": "Pulseweave",
    "만능 허리띠": "Contraption",
    "만능허리띠": "Contraption",
    "만년한철": "Shiversteel",
    "수호령": "Rooks Decree",
    "강화부표": "SuperScout 2000",
    "할시온 박차": "Halcyon Chargers",
    "할시온박차": "Halcyon Chargers",
    "신속의 신발": "Travel Boots",         # T2 boots
    "가죽 신발": "Sprint Boots",           # T1 boots
    "초시계": "Chronograph",
    "모래시계": "Hourglass",

    # Crystal T3
    "주문불꽃": "Spellfire",
    "주문불곷": "Spellfire",               # typo variant
    "강화유리": "Shatterglass",
    "신화의 종말": "Broken Myth",
    "시계장치": "Clockwork",
    "공허의 배터리": "Void Battery",
    "얼음불꽃": "Frostburn",
    "영혼수확기": "Eve of Harvest",
    "연쇄충격기": "Aftershock",
    "교류전류": "Alternating Current",
    "용의 눈": "Dragons Eye",

    # Crystal T1/T2
    "수정조각": "Crystal Bit",             # T1 component (might be Piercing Shard context-dep)
    "관통 샤드": "Piercing Shard",
    "관통샤드": "Piercing Shard",
    "대형 프리즘": "Heavy Prism",
    "일식 프리즘": "Eclipse Prism",
    "에너지 배터리": "Energy Battery",
    "수정강화제": "Crystal Infusion",

    # Weapon T3
    "비탄의 도끼": "Sorrowblade",
    "뼈톱": "Bonesaw",
    "폭군의 단안경": "Tyrants Monocle",
    "바다뱀의 가면": "Serpent Mask",
    "천공기": "Breaking Point",
    "탄성궁": "Tension Bow",
    "주문검": "Spellsword",
    "용의피 계약서": "Dragonblood Contract",  # Warhawk special item

    # Weapon T2
    "단검": "Six Sins",
    "자동권총": "Blazing Salvo",
    "기관단총": "Blazing Salvo",           # alternate Korean name
    "여우발": "Barbed Needle",             # note: from prompt "Minion's Foot" but actually Barbed Needle
    "가시바늘": "Barbed Needle",
    "가시 바늘": "Barbed Needle",
    "미늘창": "Piercing Spear",
    "행운의 과녁": "Lucky Strike",
    "강철대검": "Heavy Steel",

    # Weapon T1
    "찬가의 고서": "Book of Eulogies",

    # Utility T2/other
    "조명탄": "Flare",                     # flare consumable / Flare Gun
    "2티어신발": "Travel Boots",           # "2nd tier boots"

    # Special
    "주문장갑": "Alternating Current",     # fallback if seen
}

# Normalization helper: strip spaces, lowercase for fuzzy match
def normalize(s):
    return s.strip().lower().replace(" ", "").replace("\u200b", "")

# Build normalized lookup
KO_NORM_MAP = {normalize(k): v for k, v in KO_TO_EN.items()}

def ko_to_en(korean_name: str) -> str:
    """Convert a Korean item name to English. Returns original if not found."""
    if not korean_name or not korean_name.strip():
        return ""
    # Direct lookup
    direct = KO_TO_EN.get(korean_name.strip())
    if direct:
        return direct
    # Normalized lookup (strip spaces)
    norm = normalize(korean_name)
    norm_result = KO_NORM_MAP.get(norm)
    if norm_result:
        return norm_result
    # Return as-is with marker
    return f"[UNMAPPED: {korean_name}]"

def en_normalize(s: str) -> str:
    """Normalize English item name for set comparison."""
    return s.strip().lower().replace(" ", "").replace("'", "").replace("-", "")

# ============================================================
# 2. LOAD DATA FILES
# ============================================================

TRUTH_PATH = r"D:\Documents\GitHub\VG_REVERSE_ENGINEERING\vg\output\item_truth_template.json"
DECODER_PATH = r"D:\Documents\GitHub\VG_REVERSE_ENGINEERING\vg\output\extracted_items_all_matches.json"

def load_truth_json(path):
    """Load truth JSON that has unquoted Korean strings in item arrays.
    Fixes: [경비대의 깃발, 신속의 신발] -> ["경비대의 깃발", "신속의 신발"]
    Strategy: for each items: [...] line, quote every comma-separated token.
    """
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()

    # Fix unquoted items arrays: items: [tok1, tok2, ...]
    # Match content inside items: [ ... ] where content is NOT already quoted JSON
    def fix_items_array(m):
        inner = m.group(1)
        # If already valid JSON (starts with " or is empty), leave alone
        inner_stripped = inner.strip()
        if not inner_stripped or inner_stripped.startswith('"'):
            return m.group(0)
        # Split by comma, strip each token, wrap in quotes
        tokens = [t.strip() for t in inner.split(',')]
        quoted = ', '.join(f'"{t}"' for t in tokens if t)
        return f'"items": [{quoted}]'

    fixed = re.sub(r'"items":\s*\[([^\]]*)\]', fix_items_array, raw)
    return json.loads(fixed)

truth_data = load_truth_json(TRUTH_PATH)

with open(DECODER_PATH, "r", encoding="utf-8") as f:
    decoder_data = json.load(f)

# Index decoder by match number then player name
decoder_by_match = {}
for m in decoder_data["matches"]:
    decoder_by_match[m["match"]] = m

# ============================================================
# 3. MATCH 1-4: TRUTH vs DECODER COMPARISON
# ============================================================

print("=" * 70)
print("ITEM TRUTH COMPARISON: MATCHES 1-4")
print("=" * 70)

total_truth_items = 0
total_correct = 0
total_missing = 0      # in truth but NOT in decoder
total_extra = 0        # in decoder but NOT in truth
unmapped_ko_names = set()

# Per-player discrepancy log
all_discrepancies = []

for match_data in truth_data["matches"]:
    match_num = match_data["match"]
    if match_num > 4:
        break

    dec_match = decoder_by_match.get(match_num, {})
    dec_players = dec_match.get("players", {})

    print(f"\n{'='*70}")
    print(f"MATCH {match_num}: {dec_match.get('match_name', f'Match {match_num}')}")
    print(f"{'='*70}")

    for player_name, player_data in match_data["players"].items():
        hero = player_data.get("hero", "?")
        truth_items_ko = player_data.get("items", [])

        # Skip players with no truth items
        if not truth_items_ko:
            continue

        # Convert Korean truth items to English
        truth_items_en = []
        for ko in truth_items_ko:
            ko_str = ko.strip()
            en = ko_to_en(ko_str)
            truth_items_en.append(en)
            if en.startswith("[UNMAPPED:"):
                unmapped_ko_names.add(ko_str)

        # Get decoder items for this player
        dec_player = dec_players.get(player_name, {})
        decoder_items = dec_player.get("final_build", [])

        # Normalize for set comparison
        truth_set = set(en_normalize(x) for x in truth_items_en if x and not x.startswith("[UNMAPPED:"))
        dec_set = set(en_normalize(x) for x in decoder_items if x and not x.startswith("Unknown"))

        correct = truth_set & dec_set
        missing_from_dec = truth_set - dec_set      # in truth but not decoder
        extra_in_dec = dec_set - truth_set          # in decoder but not truth

        # Unknown items in decoder for this player
        unknowns_in_dec = [x for x in decoder_items if x.startswith("Unknown")]

        # Count toward totals
        n_truth = len(truth_set)
        total_truth_items += n_truth
        total_correct += len(correct)
        total_missing += len(missing_from_dec)
        total_extra += len(extra_in_dec)

        # Print player summary
        status = "OK" if (not missing_from_dec and not extra_in_dec) else "MISMATCH"
        print(f"\n  [{status}] {player_name} ({hero})")
        print(f"    Truth ({n_truth}): {', '.join(sorted(truth_items_en))}")
        print(f"    Decoder ({len(decoder_items)}): {', '.join(decoder_items) if decoder_items else '(no decoder data)'}")

        if correct:
            print(f"    CORRECT  ({len(correct)}): {', '.join(sorted(correct))}")
        if missing_from_dec:
            print(f"    MISSING  ({len(missing_from_dec)}): {', '.join(sorted(missing_from_dec))}")
            all_discrepancies.append({
                "match": match_num, "player": player_name, "hero": hero,
                "type": "MISSING", "items": list(missing_from_dec)
            })
        if extra_in_dec:
            print(f"    EXTRA    ({len(extra_in_dec)}): {', '.join(sorted(extra_in_dec))}")
            all_discrepancies.append({
                "match": match_num, "player": player_name, "hero": hero,
                "type": "EXTRA", "items": list(extra_in_dec)
            })
        if unknowns_in_dec:
            print(f"    UNKNOWNS in decoder: {', '.join(unknowns_in_dec)}")

        if not dec_player:
            print(f"    ** WARNING: Player '{player_name}' NOT found in decoder output **")

# ============================================================
# 4. SUMMARY STATISTICS (MATCHES 1-4)
# ============================================================

print(f"\n{'='*70}")
print("SUMMARY STATISTICS: MATCHES 1-4")
print("=" * 70)
print(f"  Total truth items compared : {total_truth_items}")
print(f"  Correct (both agree)       : {total_correct}  ({100*total_correct/max(1,total_truth_items):.1f}%)")
print(f"  Missing from decoder       : {total_missing}  ({100*total_missing/max(1,total_truth_items):.1f}%)")
print(f"  Extra in decoder           : {total_extra}")
print()

if unmapped_ko_names:
    print(f"UNMAPPED Korean names (need adding to KO_TO_EN dict):")
    for name in sorted(unmapped_ko_names):
        print(f"    '{name}'")
else:
    print("All Korean names successfully mapped.")

# ============================================================
# 5. DISCREPANCY DEEP-DIVE
# ============================================================

print(f"\n{'='*70}")
print("DISCREPANCY ANALYSIS")
print("=" * 70)

# Group missing items by item name
missing_counts = defaultdict(list)
extra_counts = defaultdict(list)

for d in all_discrepancies:
    for item in d["items"]:
        if d["type"] == "MISSING":
            missing_counts[item].append(f"M{d['match']} {d['player']} ({d['hero']})")
        else:
            extra_counts[item].append(f"M{d['match']} {d['player']} ({d['hero']})")

if missing_counts:
    print("\nItems frequently MISSING from decoder:")
    for item, occurrences in sorted(missing_counts.items(), key=lambda x: -len(x[1])):
        print(f"  '{item}' missing {len(occurrences)}x: {'; '.join(occurrences)}")

if extra_counts:
    print("\nItems frequently EXTRA in decoder (false positives):")
    for item, occurrences in sorted(extra_counts.items(), key=lambda x: -len(x[1])):
        print(f"  '{item}' extra {len(occurrences)}x: {'; '.join(occurrences)}")

# ============================================================
# 6. UNKNOWN ITEMS: MATCHES 5-11
# ============================================================

print(f"\n{'='*70}")
print("UNKNOWN ITEMS IN DECODER: MATCHES 5-11")
print("=" * 70)

unknown_appearances = defaultdict(list)  # unknown_id -> [(match, player, hero, full_build)]

for m in decoder_data["matches"]:
    match_num = m["match"]
    if match_num < 5:
        continue
    for player_name, pdata in m.get("players", {}).items():
        hero = pdata.get("hero", "?")
        final_build = pdata.get("final_build", [])
        for item in final_build:
            if item.startswith("Unknown"):
                unknown_appearances[item].append({
                    "match": match_num,
                    "player": player_name,
                    "hero": hero,
                    "build": final_build
                })

for unknown_id in sorted(unknown_appearances.keys()):
    appearances = unknown_appearances[unknown_id]
    print(f"\n  {unknown_id} ({len(appearances)} appearance(s)):")
    for a in appearances:
        build_str = ", ".join(a["build"])
        print(f"    M{a['match']} {a['player']} ({a['hero']}): [{build_str}]")

# ============================================================
# 7. UNKNOWN 19 CONTEXT ANALYSIS
# ============================================================

print(f"\n{'='*70}")
print("UNKNOWN 19: DETAILED CONTEXT ANALYSIS")
print("=" * 70)

unk19_appearances = unknown_appearances.get("Unknown 19", [])
if unk19_appearances:
    print(f"\n  Unknown 19 appears {len(unk19_appearances)} time(s) across all matches:")
    for a in unk19_appearances:
        print(f"\n  M{a['match']} | {a['player']} | Hero: {a['hero']}")
        print(f"  Full build: {a['build']}")

    print(f"\n  Common co-items across all Unknown 19 appearances:")
    all_co_items = []
    for a in unk19_appearances:
        co = [x for x in a["build"] if x != "Unknown 19"]
        all_co_items.append(set(en_normalize(x) for x in co))

    if all_co_items:
        common = all_co_items[0].copy()
        for s in all_co_items[1:]:
            common &= s
        if common:
            print(f"    Always present: {sorted(common)}")
        else:
            print(f"    No universal co-items (varies per match)")

    # Also check matches 1-4 for known context
    print(f"\n  Cross-reference: Acex/Lorelai builds in matches 1-4 (from truth):")
    for match_data in truth_data["matches"]:
        mn = match_data["match"]
        if mn > 4:
            continue
        for pname, pdata in match_data["players"].items():
            if "Acex" in pname and pdata.get("hero") == "Lorelai":
                truth_en = [ko_to_en(k.strip()) for k in pdata.get("items", [])]
                print(f"    M{mn} {pname}: {truth_en}")

    print(f"\n  Decoder note from vgr_mapping.py:")
    print(f"    ID 19 = 'qty=2. 19 buyers, Captain 89% (Ardan 6, Lorelai 4, Lance 4).")
    print(f"    Reflex Block+Crucible+Oakheart 100% co-buy. Captain defense T3'")
    print(f"\n  HYPOTHESIS: What defense T3 fits captain+Lorelai builds with Crucible+FoR?")
    print(f"    - Capacitor Plate (ID 22, confirmed) -- but only 25 buyers")
    print(f"    - Nullwave Gauntlet? -- CP-shred captain item")
    print(f"    - Atlas Pauldron? -- already ID 242")
    print(f"    - Stormcrown? -- already ID 7")
    print(f"    => Most likely: Nullwave Gauntlet (captain anti-CP utility)")

# ============================================================
# 8. UNKNOWN 22 CONTEXT ANALYSIS
# ============================================================

print(f"\n{'='*70}")
print("UNKNOWN 22 (ID 22=Capacitor Plate CONFIRMED): DECODER appearances as 'Unknown 22'")
print("=" * 70)

unk22_appearances = unknown_appearances.get("Unknown 22", [])
if unk22_appearances:
    print(f"  'Unknown 22' appears {len(unk22_appearances)} time(s):")
    for a in unk22_appearances:
        print(f"\n  M{a['match']} | {a['player']} | Hero: {a['hero']}")
        print(f"  Full build: {a['build']}")
    print(f"\n  NOTE: ID 22 in qty=2 map = Capacitor Plate (confirmed).")
    print(f"  'Unknown 22' label in decoder suggests different ID namespace or label bug.")
else:
    print("  'Unknown 22' not found in matches 5-11.")

# ============================================================
# 9. STORMGUARD BANNER: ALL DECODER APPEARANCES
# ============================================================

print(f"\n{'='*70}")
print("STORMGUARD BANNER: ALL APPEARANCES IN DECODER (final build)")
print("=" * 70)

sgb_appearances = []
for m in decoder_data["matches"]:
    match_num = m["match"]
    for player_name, pdata in m.get("players", {}).items():
        hero = pdata.get("hero", "?")
        final_build = pdata.get("final_build", [])
        if "Stormguard Banner" in final_build:
            sgb_appearances.append({
                "match": match_num,
                "player": player_name,
                "hero": hero,
                "build": final_build
            })

print(f"\n  Stormguard Banner appears as FINAL item in {len(sgb_appearances)} player builds:")
for a in sgb_appearances:
    print(f"    M{a['match']} {a['player']} ({a['hero']}): {a['build']}")

# Count by match
by_match = defaultdict(int)
for a in sgb_appearances:
    by_match[a["match"]] += 1

print(f"\n  Per-match count: {dict(sorted(by_match.items()))}")
print(f"\n  INTERPRETATION:")
print(f"    Stormguard Banner (T2 utility) appearing in final build means the player")
print(f"    did NOT upgrade to Stormcrown (T3) or Contraption (T3) by game end.")
print(f"    This is valid for support/early-game builds or short match durations.")

# ============================================================
# 10. SHIVERSTEEL: ALL DECODER APPEARANCES
# ============================================================

print(f"\n{'='*70}")
print("SHIVERSTEEL: ALL APPEARANCES IN DECODER (final build)")
print("=" * 70)

shiver_appearances = []
for m in decoder_data["matches"]:
    match_num = m["match"]
    for player_name, pdata in m.get("players", {}).items():
        hero = pdata.get("hero", "?")
        final_build = pdata.get("final_build", [])
        if "Shiversteel" in final_build:
            shiver_appearances.append({
                "match": match_num,
                "player": player_name,
                "hero": hero,
                "build": final_build
            })

print(f"\n  Shiversteel appears in {len(shiver_appearances)} player builds:")
for a in shiver_appearances:
    print(f"    M{a['match']} {a['player']} ({a['hero']}): {a['build']}")

# Cross-reference against truth for M1/M2
print(f"\n  Cross-reference vs truth (only matches 1-4 have truth):")
for match_data in truth_data["matches"]:
    mn = match_data["match"]
    if mn > 4:
        continue
    for pname, pdata in match_data["players"].items():
        truth_en = [ko_to_en(k.strip()) for k in pdata.get("items", [])]
        if "Shiversteel" in truth_en:
            print(f"    TRUTH M{mn} {pname}: has Shiversteel -> verify decoder agrees")

# In decoder M1-4
print(f"\n  Decoder Shiversteel in matches 1-4:")
for a in shiver_appearances:
    if a["match"] <= 4:
        print(f"    M{a['match']} {a['player']} ({a['hero']})")

# In decoder M5-11
print(f"\n  Decoder Shiversteel in matches 5-11:")
for a in shiver_appearances:
    if a["match"] >= 5:
        print(f"    M{a['match']} {a['player']} ({a['hero']})")

# ============================================================
# 11. ITEM ID COVERAGE CHECK
# ============================================================

print(f"\n{'='*70}")
print("DECODER ITEM COVERAGE: All unique item names across all matches")
print("=" * 70)

all_decoder_items = set()
for m in decoder_data["matches"]:
    for pname, pdata in m.get("players", {}).items():
        for item in pdata.get("final_build", []):
            all_decoder_items.add(item)

known_items = sorted(x for x in all_decoder_items if not x.startswith("Unknown") and not x.startswith("Weapon T"))
unknown_items = sorted(x for x in all_decoder_items if x.startswith("Unknown") or x.startswith("Weapon T"))

print(f"\n  Known items ({len(known_items)}): {', '.join(known_items)}")
print(f"\n  Unknown/unlabeled items ({len(unknown_items)}): {', '.join(unknown_items)}")

# ============================================================
# 12. MATCH 1-4 TRUTH vs DECODER: PLAYER ALIGNMENT REPORT
# ============================================================

print(f"\n{'='*70}")
print("MATCH 1-4: PLAYERS IN TRUTH BUT NOT IN DECODER")
print("=" * 70)

for match_data in truth_data["matches"]:
    match_num = match_data["match"]
    if match_num > 4:
        break
    dec_match = decoder_by_match.get(match_num, {})
    dec_players = dec_match.get("players", {})
    for player_name, player_data in match_data["players"].items():
        if player_data.get("items") and player_name not in dec_players:
            print(f"  M{match_num} '{player_name}' ({player_data.get('hero')}) has truth items but NO decoder entry")

print(f"\n{'='*70}")
print("MATCH 1-4: DECODER PLAYERS NOT IN TRUTH")
print("=" * 70)

for match_data in truth_data["matches"]:
    match_num = match_data["match"]
    if match_num > 4:
        break
    dec_match = decoder_by_match.get(match_num, {})
    dec_players = dec_match.get("players", {})
    truth_players = set(match_data["players"].keys())
    for dec_name in dec_players:
        if dec_name not in truth_players:
            dec_hero = dec_players[dec_name].get("hero", "?")
            print(f"  M{match_num} '{dec_name}' ({dec_hero}) is in decoder but NOT in truth")

# ============================================================
# 13. FINAL ACTIONABLE FINDINGS
# ============================================================

print(f"\n{'='*70}")
print("ACTIONABLE FINDINGS & UNKNOWN IDENTIFICATION HYPOTHESES")
print("=" * 70)

print("""
[FINDING 1] Unknown 19 = Most likely "Nullwave Gauntlet"
  - 19 buyers, Captain 89% (Ardan, Lorelai, Lance dominant)
  - Co-buys: Crucible + Fountain of Renewal + Oakheart (all captain items)
  - Appears in Acex/Lorelai builds across M6 and M7 (Finals)
  - Nullwave Gauntlet is a CP-shred captain item, fits perfectly
  - Alternative: could be "Echo" (captain skill-reset item) -- less likely

[FINDING 2] Unknown 22 in decoder = DISTINCT from item ID 22
  - Item ID 22 in ITEM_ID_MAP = Capacitor Plate (confirmed)
  - "Unknown 22" appears in Yates (M10) and Grace (M10) builds
  - These are support/captain heroes -> likely another captain defense T3
  - Hypothesis: This is a different item ID altogether (not qty=2 ID 22)
  - Grace/Yates both have Crucible+FoR+Warmail -> "Unknown 22" is an additional
    captain defense. Candidates: Nullwave Gauntlet, Atlas Pauldron
  - NOTE: Atlas Pauldron = ID 242 (confirmed), so Unknown 22 != Atlas Pauldron

[FINDING 3] Stormguard Banner as final build is LEGITIMATE
  - Appears as final item (not upgraded to Stormcrown) in multiple matches
  - Common on Reza (M3, M4) = aggressive mage who takes early Stormguard
    then switches to other items (Aftershock, Spellfire) before completing Stormcrown
  - Warhawk (M10), Malene (M11), Samuel (M5) also show it
  - This indicates players who bought Stormguard Banner but didn't build Stormcrown

[FINDING 4] Items missing from decoder mapping:
  - "Stormguard Banner" itself IS detected (appears in decoder output)
  - Main mapping gaps: check unmapped Korean names section above

[FINDING 5] Shiversteel identification
  - Appears in decoder for Ghost/Catherine (M2), multiple other captains
  - Currently "Unknown 24" in qty=2 map has Shiversteel as candidate
  - Truth for M2 Ghost/Catherine: decoder shows Shiversteel -- need to verify
    if the truth screenshot for M2 Ghost shows Shiversteel
""")

print("=" * 70)
print("SCRIPT COMPLETE")
print("=" * 70)
