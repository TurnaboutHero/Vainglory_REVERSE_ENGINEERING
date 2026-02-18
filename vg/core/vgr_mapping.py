#!/usr/bin/env python3
"""
VGR Mapping - Hero and Item ID Mapping for Vainglory
Maps internal game IDs to human-readable names.

Note: IDs are based on game version 4.13 and may vary in different versions.
These mappings are derived from game data analysis and community resources.
"""

import json
from typing import Dict, Optional, List
from dataclasses import dataclass, asdict

# Asset-based Hero ID Mapping (extracted from game files)
# These IDs are used in /Characters/HeroXXX/ paths in game assets
ASSET_HERO_ID_MAP: Dict[str, str] = {
    "009": "SAW", "010": "Ringo", "011": "Taka", "012": "Krul",
    "013": "Skaarf", "014": "Celeste", "015": "Vox", "016": "Catherine",
    "017": "Ardan", "019": "Glaive", "020": "Joule", "021": "Koshka",
    "023": "Petal", "024": "Adagio", "025": "Rona", "027": "Fortress",
    "028": "Reim", "029": "Phinn", "030": "Blackfeather", "031": "Skye",
    "036": "Kestrel", "037": "Alpha", "038": "Lance", "039": "Ozo",
    "040": "Lyra", "041": "Samuel", "042": "Baron", "044": "Gwen",
    "045": "Flicker", "046": "Idris", "047": "Grumpjaw", "048": "Baptiste",
    "054": "Grace", "055": "Reza", "058": "Churnwalker", "059": "Lorelai",
    "060": "Tony", "061": "Varya", "062": "Malene", "063": "Kensei",
    "064": "Kinetic", "065": "San Feng", "066": "Silvernail", "067": "Yates",
    "068": "Inara", "069": "Magnus", "070": "Caine", "071": "Leo",
    "022": "Warhawk", # Likely candidate
    "032": "Anka",    # Confirmed active ID with high event count
    "056": "Miho",    # Likely candidate
    "072": "Amael",   # Confirmed from replay analysis
    "075": "Ishtar",  # Likely candidate
    "082": "Karas",   # Likely candidate
    "103": "Shin",    # Likely candidate (Latest hero)
    # Still missing: Ylva, Viola (One is likely 056 or 022?)
}

# Binary Hero ID Mapping (uint16 LE at player block offset +0x0A9)
# Discovered via cross-correlation analysis of 107 player blocks
# across 11 tournament replays with 100% consistency, 0 collisions.
# Structure: player_block_marker(DA 03 EE) + name + ... + entity_id(0xA5) + 00 00 + hero_id(0xA9)
BINARY_HERO_ID_MAP: Dict[int, str] = {
    # === Confirmed (100% - validated across 107 tournament players) ===
    0x0101: "Ardan",
    0x0301: "Fortress",
    0x0501: "Baron",
    0x0901: "Skye",
    0x0A01: "Reim",
    0x0B01: "Kestrel",
    0x0D01: "Lyra",
    0x1101: "Idris",
    0x1201: "Ozo",
    0x1401: "Samuel",
    0x1701: "Phinn",
    0x1801: "Blackfeather",
    0x1901: "Malene",
    0x1D01: "Celeste",
    0x8B01: "Gwen",
    0x8C01: "Grumpjaw",
    0x8D01: "Tony",
    0x8F01: "Baptiste",
    0x9103: "Leo",
    0x9301: "Reza",
    0x9303: "Caine",
    0x9403: "Warhawk",
    0x9601: "Grace",
    0x9901: "Lorelai",
    0x9A03: "Ishtar",
    0x9C01: "Kensei",
    0xA201: "Magnus",
    0xA401: "Kinetic",
    0xB001: "Silvernail",
    0xB401: "Ylva",
    0xB701: "Yates",
    0xB801: "Inara",
    0xBE01: "San Feng",
    0xF200: "Catherine",
    0xF300: "Ringo",
    0xFD00: "Joule",
    0xFF00: "Skaarf",
    # === Inferred (avg ~80% confidence - release chronology + ID pattern) ===
    # 0x00 suffix: original heroes
    0xF400: "Glaive",       # 85% - sequential in 0xFx00 range
    0xF500: "Koshka",       # 85% - sequential after F4
    0xF600: "Petal",        # 80% - sequential after F5
    0xF900: "Krul",         # 80% - original warrior
    0xFA00: "Adagio",       # 85% - sequential position
    0xFE00: "SAW",          # 90% - just before Skaarf(FF)
    # 0x01 suffix: season 1-3 heroes
    0x0001: "Taka",         # 90% - first assassin, early release
    0x0201: "Vox",          # 85% - sequential, high usage(10)
    0x0401: "Rona",         # 80% - season 1 warrior
    0x0C01: "Flicker",      # 75% - season 2 support
    0x1301: "Lance",        # 85% - season 2 captain, high usage(20)
    0x8901: "Alpha",        # 80% - season 2 warrior
    0x9801: "Churnwalker",  # 75% - between Grace(96) and Lorelai(99)
    0x9D01: "Varya",        # 70% - season 3 mage
    0xAD01: "Miho",         # 65% - between Kinetic(A4) and Silvernail(B0)
    # 0x03 suffix: season 4+ heroes
    0x9703: "Viola",        # 75% - between Warhawk(94) and Ishtar(9A)
    0x9C03: "Anka",         # 80% - season 4 assassin
    0x9D03: "Amael",        # CONFIRMED via replay screenshot (21.11.04 match, support build)
    0x9E03: "Shin",         # 70% - latest captain
    0x9F03: "Karas",        # SWAPPED with Amael - Karas is CP ranged dealer
}

# Reverse lookup: hero name -> binary ID
BINARY_HERO_NAME_TO_ID: Dict[str, int] = {
    name: bid for bid, name in BINARY_HERO_ID_MAP.items()
    if not name.startswith("unknown_")
}

# Binary Hero ID offset from player block marker (DA 03 EE)
HERO_ID_OFFSET = 0x0A9

# Hero name normalization for OCR typos
HERO_NAME_NORMALIZE: Dict[str, str] = {
    "mallene": "Malene",
    "ishutar": "Ishtar",
    # Add more typos as discovered
}

def normalize_hero_name(name: str) -> str:
    """Normalize hero name to handle OCR typos."""
    if not name:
        return name
    return HERO_NAME_NORMALIZE.get(name.lower(), name)

# Asset Hero ID map with integer keys for byte pattern matching
def _build_asset_hero_id_int_map() -> Dict[int, str]:
    """Convert ASSET_HERO_ID_MAP string keys to integers."""
    result = {}
    for key, name in ASSET_HERO_ID_MAP.items():
        try:
            # "009" -> 9, "010" -> 10
            int_key = int(key)
            result[int_key] = name
        except ValueError:
            continue
    return result

ASSET_HERO_ID_INT_MAP: Dict[int, str] = _build_asset_hero_id_int_map()

# Asset-based Item Name Mapping (extracted from game files)
ASSET_ITEM_NAMES = [
    "AC", "AMR", "CapPlate", "Crisis_Crystal_Con", "Crisis_Weapon_Con",
    "Crucible", "EMP", "Echo", "Flare_Proj_A", "Flare_Proj_E", "Flare_Ring_A",
    "Fountain", "Frostburn", "GraveLash", "HealingFlask", "IronGuard",
    "Protector", "ReflexBlock", "ScoutTrap", "Shell", "Shiv", "Slumbering_Husk",
    "StormGuard", "UC", "WarTreads", "WindRider"
]

# Hero ID Mapping
# Based on internal game order and community research
HERO_ID_MAP: Dict[int, Dict] = {
    # Original Heroes (Season 1)
    1: {"name": "Adagio", "name_ko": "아다지오", "role": "Captain"},
    2: {"name": "Catherine", "name_ko": "캐서린", "role": "Captain"},
    3: {"name": "Glaive", "name_ko": "글레이브", "role": "Warrior"},
    4: {"name": "Koshka", "name_ko": "코쉬카", "role": "Assassin"},
    5: {"name": "Krul", "name_ko": "크럴", "role": "Warrior"},
    6: {"name": "Petal", "name_ko": "페탈", "role": "Mage"},
    7: {"name": "Ringo", "name_ko": "링고", "role": "Sniper"},
    8: {"name": "SAW", "name_ko": "쏘우", "role": "Sniper"},
    9: {"name": "Skaarf", "name_ko": "스카프", "role": "Mage"},
    10: {"name": "Taka", "name_ko": "타카", "role": "Assassin"},
    
    # Season 1 Additions
    11: {"name": "Joule", "name_ko": "쥴", "role": "Warrior"},
    12: {"name": "Ardan", "name_ko": "아단", "role": "Captain"},
    13: {"name": "Celeste", "name_ko": "셀레스트", "role": "Mage"},
    14: {"name": "Vox", "name_ko": "복스", "role": "Sniper"},
    15: {"name": "Rona", "name_ko": "로나", "role": "Warrior"},
    16: {"name": "Fortress", "name_ko": "포트리스", "role": "Captain"},
    17: {"name": "Reim", "name_ko": "라임", "role": "Mage"},
    
    # Season 2 Heroes
    18: {"name": "Phinn", "name_ko": "핀", "role": "Captain"},
    19: {"name": "Blackfeather", "name_ko": "흑깃", "role": "Assassin"},
    20: {"name": "Skye", "name_ko": "스카이", "role": "Mage"},
    21: {"name": "Kestrel", "name_ko": "케스트럴", "role": "Sniper"},
    22: {"name": "Alpha", "name_ko": "알파", "role": "Warrior"},
    23: {"name": "Lance", "name_ko": "랜스", "role": "Captain"},
    24: {"name": "Ozo", "name_ko": "오조", "role": "Warrior"},
    25: {"name": "Lyra", "name_ko": "라이라", "role": "Captain"},
    26: {"name": "Samuel", "name_ko": "사무엘", "role": "Mage"},
    27: {"name": "Baron", "name_ko": "바론", "role": "Sniper"},
    28: {"name": "Gwen", "name_ko": "그웬", "role": "Sniper"},
    29: {"name": "Flicker", "name_ko": "플리커", "role": "Captain"},
    30: {"name": "Idris", "name_ko": "이드리스", "role": "Assassin"},
    
    # Season 3 Heroes  
    31: {"name": "Grumpjaw", "name_ko": "사슬니", "role": "Warrior"},
    32: {"name": "Baptiste", "name_ko": "바티스트", "role": "Mage"},
    33: {"name": "Grace", "name_ko": "그레이스", "role": "Captain"},
    34: {"name": "Reza", "name_ko": "레자", "role": "Assassin"},
    35: {"name": "Churnwalker", "name_ko": "어둠추적자", "role": "Captain"},
    36: {"name": "Lorelai", "name_ko": "로렐라이", "role": "Captain"},
    37: {"name": "Tony", "name_ko": "토니", "role": "Warrior"},
    38: {"name": "Varya", "name_ko": "바리야", "role": "Mage"},
    39: {"name": "Malene", "name_ko": "말렌", "role": "Mage"},
    40: {"name": "Kensei", "name_ko": "켄세이", "role": "Warrior"},
    41: {"name": "Kinetic", "name_ko": "키네틱", "role": "Sniper"},
    42: {"name": "San Feng", "name_ko": "삼봉", "role": "Warrior"},
    43: {"name": "Silvernail", "name_ko": "실버네일", "role": "Sniper"},
    44: {"name": "Yates", "name_ko": "예이츠", "role": "Captain"},
    45: {"name": "Inara", "name_ko": "이나라", "role": "Warrior"},
    
    # Season 4+ Heroes
    46: {"name": "Magnus", "name_ko": "마그누스", "role": "Mage"},
    47: {"name": "Caine", "name_ko": "케인", "role": "Sniper"},
    48: {"name": "Leo", "name_ko": "레오", "role": "Warrior"},
    49: {"name": "Viola", "name_ko": "비올라", "role": "Captain"},
    50: {"name": "Warhawk", "name_ko": "워호크", "role": "Sniper"},
    51: {"name": "Anka", "name_ko": "앙카", "role": "Assassin"},
    52: {"name": "Miho", "name_ko": "미호", "role": "Assassin"},
    53: {"name": "Karas", "name_ko": "카라스", "role": "Mage"},  # CP ranged dealer
    54: {"name": "Shin", "name_ko": "신", "role": "Captain"},
    55: {"name": "Ishtar", "name_ko": "이슈타르", "role": "Sniper"},
    56: {"name": "Ylva", "name_ko": "일바", "role": "Assassin"},
    57: {"name": "Amael", "name_ko": "아마엘", "role": "Captain"},  # tank/support
}

# Reverse lookup: name to ID
HERO_NAME_TO_ID: Dict[str, int] = {
    info["name"].lower(): id for id, info in HERO_ID_MAP.items()
}

# Item ID Mapping
# =============================================================================
# IMPORTANT: The old 100/300/400-series IDs were WRONG (never appeared in replay
# binary data). Real item IDs use the 200-255 range plus low IDs (0-27, qty=1).
#
# Mapping sources:
#   - "confirmed": Truth data frequency matching (Jaccard >= 0.50, matches 1-4)
#   - "moderate":  Truth data lower confidence + role matrix corroboration
#   - "tentative": Role matrix + transition chain analysis (no direct truth match)
#   - "unknown":   Category known from role matrix, specific item uncertain
# =============================================================================
ITEM_ID_MAP: Dict[int, Dict] = {
    # =========================================================================
    # LOW IDs (0-27): qty=1 = shop items, qty=2 = ability upgrades
    # =========================================================================
    0:  {"name": "Heavy Prism", "category": "Crystal", "tier": 2, "status": "tentative",
         "note": "Appears in all crystal carry builds, consumed into crystal T3 items"},
    5:  {"name": "Tyrants Monocle", "category": "Weapon", "tier": 3, "status": "confirmed"},
    8:  {"name": "Weapon Infusion", "category": "Consumable", "tier": 0, "status": "tentative",
         "note": "Only WP carry (tsuki/Kinetic) in M7. Late-game consumable."},
    7:  {"name": "Stormcrown", "category": "Utility", "tier": 3, "status": "confirmed"},
    10: {"name": "Spellfire", "category": "Crystal", "tier": 3, "status": "confirmed"},
    11: {"name": "Dragons Eye", "category": "Crystal", "tier": 3, "status": "confirmed"},
    12: {"name": "Spellsword", "category": "Weapon", "tier": 3, "status": "confirmed"},
    13: {"name": "Slumbering Husk", "category": "Defense", "tier": 3, "status": "confirmed"},
    15: {"name": "SuperScout 2000", "category": "Utility", "tier": 3, "status": "confirmed"},
    16: {"name": "Contraption", "category": "Utility", "tier": 3, "status": "tentative",
         "note": "Appears exclusively in captain builds (Lorelai, Lyra, Ardan). Built from Stormguard Banner + Chronograph"},
    20: {"name": "Flare", "category": "Utility", "tier": 0, "status": "confirmed"},
    21: {"name": "Pulseweave", "category": "Defense", "tier": 3, "status": "confirmed"},
    24: {"name": "Blazing Salvo", "category": "Weapon", "tier": 2, "status": "confirmed",
         "note": "Tied J=1.00 with Dragonblood Contract (same player)"},
    26: {"name": "Warmail", "category": "Defense", "tier": 2, "status": "confirmed"},
    27: {"name": "Rooks Decree", "category": "Defense", "tier": 3, "status": "confirmed"},

    # =========================================================================
    # IDs 200+: Main shop items
    # =========================================================================

    # --- Weapon T1 (300g) ---
    202: {"name": "Weapon Blade", "category": "Weapon", "tier": 1, "status": "tentative",
          "note": "Role matrix: 92% WP (46/50), cost=300g"},
    204: {"name": "Swift Shooter", "category": "Weapon", "tier": 1, "status": "confirmed"},
    243: {"name": "Book of Eulogies", "category": "Weapon", "tier": 1, "status": "confirmed"},

    # --- Weapon T2 (400-850g) ---
    205: {"name": "Six Sins", "category": "Weapon", "tier": 2, "status": "tentative",
          "note": "WP 93%, cost=350g matches Six Sins"},
    207: {"name": "Weapon T2", "category": "Weapon", "tier": 2, "status": "unknown",
          "note": "WP 85% (17/20), cost=400g"},
    237: {"name": "Barbed Needle", "category": "Weapon", "tier": 2, "status": "tentative",
          "note": "WP 75% (36/48), cost=500g, transitions to Breaking Point(251)"},
    244: {"name": "Lucky Strike", "category": "Weapon", "tier": 2, "status": "tentative",
          "note": "WP 83% (5/6), cost=500g"},
    249: {"name": "Heavy Steel", "category": "Weapon", "tier": 2, "status": "tentative",
          "note": "WP 100% (27/27), cost=850g, transitions to Sorrowblade(208)"},
    250: {"name": "Piercing Spear", "category": "Weapon", "tier": 2, "status": "tentative",
          "note": "WP 100% (14/14), cost=600g, transitions to Bonesaw(226)"},
    252: {"name": "Weapon T2-T3", "category": "Weapon", "tier": 2, "status": "unknown",
          "note": "WP 100% (5/5), cost=900g"},

    # --- Weapon T3 (1300g+) ---
    208: {"name": "Sorrowblade", "category": "Weapon", "tier": 3, "status": "confirmed"},
    223: {"name": "Serpent Mask", "category": "Weapon", "tier": 3, "status": "confirmed"},
    226: {"name": "Bonesaw", "category": "Weapon", "tier": 3, "status": "confirmed"},
    235: {"name": "Tension Bow", "category": "Weapon", "tier": 3, "status": "tentative",
          "note": "WP 100% (4/4), cost=1350g"},
    251: {"name": "Breaking Point", "category": "Weapon", "tier": 3, "status": "confirmed"},

    # --- Crystal T1 (300g) ---
    203: {"name": "Crystal Bit", "category": "Crystal", "tier": 1, "status": "tentative",
          "note": "CP 86% (77/90), cost=300g, most common CP item"},
    206: {"name": "Energy Battery", "category": "Crystal", "tier": 1, "status": "tentative",
          "note": "CP 81% (35/43), cost=350g"},
    216: {"name": "Hourglass", "category": "Crystal", "tier": 1, "status": "tentative",
          "note": "CP 65% (17/26), cost=300g"},

    # --- Crystal T2 (400-600g) ---
    218: {"name": "Chronograph", "category": "Crystal", "tier": 2, "status": "tentative",
          "note": "CP 81% (13/16), cost=400g"},
    238: {"name": "Eclipse Prism", "category": "Crystal", "tier": 2, "status": "tentative",
          "note": "CP 74% (31/42), cost=500g, transitions to Broken Myth(240)"},
    254: {"name": "Piercing Shard", "category": "Crystal", "tier": 2, "status": "confirmed"},

    # --- Crystal T3 (900g+) ---
    209: {"name": "Shatterglass", "category": "Crystal", "tier": 3, "status": "confirmed"},
    220: {"name": "Clockwork", "category": "Crystal", "tier": 3, "status": "confirmed"},
    230: {"name": "Frostburn", "category": "Crystal", "tier": 3, "status": "confirmed"},
    236: {"name": "Aftershock", "category": "Crystal", "tier": 3, "status": "confirmed"},
    240: {"name": "Broken Myth", "category": "Crystal", "tier": 3, "status": "confirmed"},
    253: {"name": "Alternating Current", "category": "Crystal", "tier": 3, "status": "confirmed"},
    255: {"name": "Eve of Harvest", "category": "Crystal", "tier": 3, "status": "confirmed"},

    # --- Defense T1 (250-350g) ---
    211: {"name": "Light Shield", "category": "Defense", "tier": 1, "status": "tentative",
          "note": "CAP 58% (61/105), cost=300g, very common (multi-buy for Aegis)"},
    212: {"name": "Oakheart", "category": "Defense", "tier": 1, "status": "moderate",
          "note": "Truth J=0.18 (recall 100%), CAP 61% (38/62), cost=350g"},
    213: {"name": "Light Armor", "category": "Defense", "tier": 1, "status": "tentative",
          "note": "CAP 58% (18/31), cost=300g"},
    245: {"name": "Light Shield", "category": "Defense", "tier": 1, "status": "tentative",
          "note": "Variant of ID 211 (Light Shield). CAP 52%, cost=300g, transitions to Kinetic Shield(246). Very common across all matches."},
    215: {"name": "Light Armor", "category": "Defense", "tier": 1, "status": "tentative",
          "note": "Variant of ID 213 (Light Armor). Only topLaner in M7/M8. Transitions to Kinetic Shield."},

    # --- Defense T2 (400-800g) ---
    214: {"name": "Dragonheart", "category": "Defense", "tier": 2, "status": "tentative",
          "note": "BR 57% (13/23), cost=450g"},
    229: {"name": "Reflex Block", "category": "Defense", "tier": 2, "status": "tentative",
          "note": "Universal (69p), cost=700g, transitions to Crucible(232)+Aegis(247)"},
    246: {"name": "Kinetic Shield", "category": "Defense", "tier": 2, "status": "moderate",
          "note": "Truth J=0.17, DEF (BR+CAP 91%), cost=450g"},
    248: {"name": "Lifespring", "category": "Defense", "tier": 2, "status": "tentative",
          "note": "CAP 57% (17/30), cost=800g, transitions to Fountain(231)"},

    # --- Defense T3 (950g+) ---
    231: {"name": "Fountain of Renewal", "category": "Defense", "tier": 3, "status": "confirmed"},
    232: {"name": "Crucible", "category": "Defense", "tier": 3, "status": "confirmed"},
    242: {"name": "Atlas Pauldron", "category": "Defense", "tier": 3, "status": "confirmed"},
    247: {"name": "Aegis", "category": "Defense", "tier": 3, "status": "confirmed"},

    # --- Utility / Boots ---
    201: {"name": "Unknown 201", "category": "Utility", "tier": 0, "status": "unknown",
          "note": "Universal (70p), cost=FREE, possibly system/start item"},
    219: {"name": "Stormguard Banner", "category": "Utility", "tier": 2, "status": "tentative",
          "note": "Mixed roles (20p), cost=800g"},
    221: {"name": "Sprint Boots", "category": "Utility", "tier": 1, "status": "tentative",
          "note": "Universal (67p), cost=300g"},
    222: {"name": "Travel Boots", "category": "Utility", "tier": 2, "status": "tentative",
          "note": "Universal (73p), cost=350g"},
    234: {"name": "Halcyon Chargers", "category": "Utility", "tier": 3, "status": "confirmed"},
    241: {"name": "War Treads", "category": "Utility", "tier": 3, "status": "confirmed"},

    # --- Identified from final build analysis ---
    17: {"name": "Shiversteel", "category": "Defense", "tier": 3, "status": "tentative",
         "note": "Appears exclusively in captain/tank builds (Warhawk, Lorelai, Grumpjaw). Built from Dragonheart."},
    18: {"name": "Crystal Infusion", "category": "Consumable", "tier": 0, "status": "tentative",
         "note": "M7 right team ALL 4 players (WP+CP+tank+mage) = role-independent consumable. Late-game buff."},
    19: {"name": "Unknown 19", "category": "Utility", "tier": 3, "status": "unknown",
         "note": "Only Acex(Lorelai) in M6/M7. Captain-specific T3 (Echo? Capacitor Plate? Nullwave?)."},
    22: {"name": "Unknown 22", "category": "Utility", "tier": 3, "status": "unknown",
         "note": "Captain builds (Yates, Grace) in M10. Non-boot T3."},

    # --- Unknown (category from role matrix but item uncertain) ---
    217: {"name": "Unknown 217", "category": "Defense", "tier": 1, "status": "unknown",
          "note": "Mixed roles (19p), cost=250g"},
}

# Reverse lookup: item name to ID
ITEM_NAME_TO_ID: Dict[str, int] = {
    info["name"].lower(): id for id, info in ITEM_ID_MAP.items()
}

# Skin Tier Mapping
SKIN_TIERS = {
    0: "Default",
    1: "Rare (Tier I)",
    2: "Epic (Tier II)",
    3: "Legendary (Tier III)",
    4: "Special Edition (SE)",
    5: "Limited Edition (LE)",
}


class VGRMapping:
    """Mapping utility for Vainglory game data"""
    
    @staticmethod
    def get_hero_by_id(hero_id: int) -> Optional[Dict]:
        """Get hero info by ID"""
        return HERO_ID_MAP.get(hero_id)
    
    @staticmethod
    def get_hero_by_name(name: str) -> Optional[Dict]:
        """Get hero info by name"""
        name_lower = name.lower()
        for id, info in HERO_ID_MAP.items():
            if info["name"].lower() == name_lower or info["name_ko"] == name:
                return {"id": id, **info}
        return None
    
    @staticmethod
    def get_item_by_id(item_id: int) -> Optional[Dict]:
        """Get item info by ID"""
        return ITEM_ID_MAP.get(item_id)
    
    @staticmethod
    def get_item_by_name(name: str) -> Optional[Dict]:
        """Get item info by name"""
        name_lower = name.lower()
        for id, info in ITEM_ID_MAP.items():
            if info["name"].lower() == name_lower:
                return {"id": id, **info}
        return None
    
    @staticmethod
    def get_all_heroes() -> List[Dict]:
        """Get all heroes with IDs"""
        return [{"id": id, **info} for id, info in HERO_ID_MAP.items()]
    
    @staticmethod
    def get_all_items() -> List[Dict]:
        """Get all items with IDs"""
        return [{"id": id, **info} for id, info in ITEM_ID_MAP.items()]
    
    @staticmethod
    def search_hero(query: str) -> List[Dict]:
        """Search heroes by partial name match"""
        query_lower = query.lower()
        results = []
        for id, info in HERO_ID_MAP.items():
            if query_lower in info["name"].lower() or query_lower in info.get("name_ko", ""):
                results.append({"id": id, **info})
        return results
    
    @staticmethod
    def search_item(query: str) -> List[Dict]:
        """Search items by partial name match"""
        query_lower = query.lower()
        results = []
        for id, info in ITEM_ID_MAP.items():
            if query_lower in info["name"].lower():
                results.append({"id": id, **info})
        return results
    
    @staticmethod
    def export_mapping(output_path: str = "vg_mapping.json"):
        """Export all mappings to JSON file"""
        data = {
            "heroes": [{"id": id, **info} for id, info in HERO_ID_MAP.items()],
            "items": [{"id": id, **info} for id, info in ITEM_ID_MAP.items()],
            "skin_tiers": SKIN_TIERS
        }
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return output_path


def main():
    """CLI for VGR Mapping"""
    import argparse
    
    parser = argparse.ArgumentParser(description='VGR Mapping - Hero/Item ID Lookup')
    parser.add_argument('command', choices=['heroes', 'items', 'search', 'export'],
                        help='Command to run')
    parser.add_argument('-q', '--query', help='Search query')
    parser.add_argument('-i', '--id', type=int, help='ID to lookup')
    parser.add_argument('-o', '--output', default='vg_mapping.json', help='Output file')
    
    args = parser.parse_args()
    mapping = VGRMapping()
    
    if args.command == 'heroes':
        if args.id:
            hero = mapping.get_hero_by_id(args.id)
            if hero:
                print(f"ID {args.id}: {hero['name']} ({hero['name_ko']}) - {hero['role']}")
            else:
                print(f"Hero ID {args.id} not found")
        else:
            print(f"{'ID':>3} {'Name':<15} {'한글':<10} {'Role':<10}")
            print("-" * 45)
            for hero in mapping.get_all_heroes():
                print(f"{hero['id']:>3} {hero['name']:<15} {hero['name_ko']:<10} {hero['role']:<10}")
    
    elif args.command == 'items':
        if args.id:
            item = mapping.get_item_by_id(args.id)
            if item:
                print(f"ID {args.id}: {item['name']} ({item['category']}, Tier {item['tier']})")
            else:
                print(f"Item ID {args.id} not found")
        else:
            current_category = None
            for item in mapping.get_all_items():
                if item['category'] != current_category:
                    current_category = item['category']
                    print(f"\n=== {current_category} ===")
                print(f"  {item['id']:>3}: [{item['tier']}] {item['name']}")
    
    elif args.command == 'search':
        if not args.query:
            print("Usage: vgr_mapping.py search -q <query>")
        else:
            heroes = mapping.search_hero(args.query)
            items = mapping.search_item(args.query)
            
            if heroes:
                print("Heroes:")
                for h in heroes:
                    print(f"  ID {h['id']}: {h['name']} ({h['name_ko']})")
            
            if items:
                print("Items:")
                for i in items:
                    print(f"  ID {i['id']}: {i['name']}")
            
            if not heroes and not items:
                print("No results found")
    
    elif args.command == 'export':
        output = mapping.export_mapping(args.output)
        print(f"✓ Mapping exported to: {output}")
        print(f"  - Heroes: {len(HERO_ID_MAP)}")
        print(f"  - Items: {len(ITEM_ID_MAP)}")


if __name__ == '__main__':
    main()
