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
# Two acquisition mechanisms in [10 04 3D] acquire events:
#   - qty=1 + IDs 200-255: Standard shop purchase (all tiers)
#   - qty=2 + IDs 0-27:    T3/special item completion (crafted from components)
#
# Evidence for qty=2 = items (NOT ability upgrades):
#   - Only 2-5 qty=2 events per player (ability upgrades would be 12 = max level)
#   - Hero role distribution matches expected item buyers perfectly
#   - ID 14 is universal (system event, excluded)
#
# Mapping sources:
#   - "confirmed": Replay viewer screenshot or build comparison with known match
#   - "tentative": Role matrix + co-item analysis + upgrade chain inference
#   - "inferred":  qty=2 hero distribution analysis (buyer role matching)
#   - "unknown":   Category known from buyer profile, specific item uncertain
# =============================================================================
ITEM_ID_MAP: Dict[int, Dict] = {
    # =========================================================================
    # qty=2 T3/Special Items (IDs 0-27) - crafted/completed items
    # Identified by hero buyer distribution across 56 replays
    # =========================================================================
    0: {"name": "Heavy Prism", "category": "Crystal", "tier": 2, "status": "inferred",
        "note": "qty=2. 63 buyers, ALL CP heroes. Crystal T2 component"},
    1: {"name": "Journey Boots", "category": "Utility", "tier": 3, "status": "inferred",
        "note": "qty=2. 57 buyers, melee/bruiser heavy. T3 boots"},
    5: {"name": "Tyrants Monocle", "category": "Weapon", "tier": 3, "status": "inferred",
        "note": "qty=2. 15 buyers (Baron 6x, Ringo 5x). WP carry T3"},
    7: {"name": "Stormcrown", "category": "Utility", "tier": 3, "status": "inferred",
        "note": "qty=2. 39 buyers, junglers/bruisers. Jungle utility T3"},
    8: {"name": "Weapon Infusion", "category": "Consumable", "tier": 0, "status": "inferred",
        "note": "qty=2. 12 buyers, ALL WP carries. Late-game WP buff (alt ID, see also 244)"},
    10: {"name": "Spellfire", "category": "Crystal", "tier": 3, "status": "inferred",
         "note": "qty=2. 38 buyers, CP mages. Crystal T3"},
    11: {"name": "Dragons Eye", "category": "Crystal", "tier": 3, "status": "inferred",
         "note": "qty=2. 19 buyers, CP carries. Crystal T3"},
    12: {"name": "Spellsword", "category": "Weapon", "tier": 3, "status": "inferred",
         "note": "qty=2. 12 buyers (Caine 7x dominant). WP/hybrid T3"},
    13: {"name": "Slumbering Husk", "category": "Defense", "tier": 3, "status": "inferred",
         "note": "qty=2. 19 buyers, mixed carry+tank. Defense T3"},
    # ID 14 = system event (universal, excluded via STARTER_IDS)
    15: {"name": "SuperScout 2000", "category": "Utility", "tier": 3, "status": "inferred",
         "note": "qty=2. 12 buyers, ALL captains. Vision utility T3"},
    16: {"name": "Contraption", "category": "Utility", "tier": 3, "status": "inferred",
         "note": "qty=2. 15 buyers, ALL captains. Vision/utility T3"},
    17: {"name": "Shiversteel", "category": "Defense", "tier": 3, "status": "inferred",
         "note": "qty=2. 13 buyers, ALL captains. HP/slow utility T3"},
    18: {"name": "Crystal Infusion", "category": "Consumable", "tier": 0, "status": "inferred",
         "note": "qty=2. 11 buyers, mixed. Late-game CP buff consumable"},
    20: {"name": "Flare Gun", "category": "Consumable", "tier": 0, "status": "inferred",
         "note": "qty=2. 29 buyers, ALL captains. Captain consumable/utility"},
    21: {"name": "Pulseweave", "category": "Defense", "tier": 3, "status": "inferred",
         "note": "qty=2. 40 buyers, bruisers/tanks. Defense T3"},
    22: {"name": "Capacitor Plate", "category": "Defense", "tier": 3, "status": "inferred",
         "note": "qty=2. 25 buyers, ALL captains. Captain defense T3"},
    23: {"name": "Rooks Decree", "category": "Defense", "tier": 3, "status": "inferred",
         "note": "qty=2. 16 buyers, ALL captains. Captain defense T3"},
    26: {"name": "Warmail", "category": "Defense", "tier": 2, "status": "inferred",
         "note": "qty=2. 45 buyers, captains/tanks. Defense T2 armor"},
    27: {"name": "Metal Jacket", "category": "Defense", "tier": 3, "status": "inferred",
         "note": "qty=2. 31 buyers, bruisers+carries (Gwen/Kinetic/SAW). Armor T3"},

    # =========================================================================
    # Weapon T1
    # =========================================================================
    202: {"name": "Weapon Blade", "category": "Weapon", "tier": 1, "status": "tentative",
          "note": "WP 92% (140 buyers), most common WP T1 component"},
    204: {"name": "Swift Shooter", "category": "Weapon", "tier": 1, "status": "confirmed"},
    243: {"name": "Book of Eulogies", "category": "Weapon", "tier": 1, "status": "confirmed"},

    # =========================================================================
    # Weapon T2
    # =========================================================================
    205: {"name": "Six Sins", "category": "Weapon", "tier": 2, "status": "tentative",
          "note": "WP 93%, builds into Sorrowblade(208), Tension Bow(224)"},
    207: {"name": "Blazing Salvo", "category": "Weapon", "tier": 2, "status": "tentative",
          "note": "WP 85% (144 buyers), multi-buy. Builds into Tornado Trigger(210), Poisoned Shiv(252). Co-occurs with Barbed Needle(237) 86%"},
    235: {"name": "Lucky Strike", "category": "Weapon", "tier": 2, "status": "confirmed",
          "note": "CONFIRMED via 21.11.04 match. Builds into Tornado Trigger(210)"},
    237: {"name": "Barbed Needle", "category": "Weapon", "tier": 2, "status": "tentative",
          "note": "WP 75%, builds into Serpent Mask(223), Poisoned Shiv(252), Breaking Point(251)"},
    249: {"name": "Heavy Steel", "category": "Weapon", "tier": 2, "status": "tentative",
          "note": "WP 100% (132 buyers), builds into Sorrowblade(208)"},
    250: {"name": "Piercing Spear", "category": "Weapon", "tier": 2, "status": "tentative",
          "note": "WP 100% (111 buyers), builds into Bonesaw(226), Tension Bow(224)"},

    # =========================================================================
    # Weapon T3
    # =========================================================================
    208: {"name": "Sorrowblade", "category": "Weapon", "tier": 3, "status": "confirmed"},
    210: {"name": "Tornado Trigger", "category": "Weapon", "tier": 3, "status": "confirmed",
          "note": "CONFIRMED via 21.11.04 match. Built from Lucky Strike(235)+Blazing Salvo(207)"},
    223: {"name": "Serpent Mask", "category": "Weapon", "tier": 3, "status": "confirmed"},
    224: {"name": "Tension Bow", "category": "Weapon", "tier": 3, "status": "confirmed",
          "note": "CONFIRMED: all buyers have Piercing Spear(250)+Six Sins(205)"},
    226: {"name": "Bonesaw", "category": "Weapon", "tier": 3, "status": "confirmed"},
    251: {"name": "Breaking Point", "category": "Weapon", "tier": 3, "status": "confirmed"},
    252: {"name": "Poisoned Shiv", "category": "Weapon", "tier": 3, "status": "tentative",
          "note": "WP 100% (50 buyers). Co-occurs with Barbed Needle(237) 90% + Blazing Salvo(207) 92%. Built from Blazing Salvo+Barbed Needle"},

    # =========================================================================
    # Crystal T1
    # =========================================================================
    203: {"name": "Crystal Bit", "category": "Crystal", "tier": 1, "status": "tentative",
          "note": "CP 86% (177 buyers), most common CP T1"},
    206: {"name": "Energy Battery", "category": "Crystal", "tier": 1, "status": "tentative",
          "note": "CP 81% (174 buyers)"},
    216: {"name": "Hourglass", "category": "Crystal", "tier": 1, "status": "tentative",
          "note": "CP 65% (138 buyers)"},

    # =========================================================================
    # Crystal T2
    # =========================================================================
    218: {"name": "Chronograph", "category": "Crystal", "tier": 2, "status": "tentative",
          "note": "CP 81% (80 buyers), builds into Clockwork(220), Aftershock(236)"},
    254: {"name": "Piercing Shard", "category": "Crystal", "tier": 2, "status": "confirmed"},

    # =========================================================================
    # Crystal T3
    # =========================================================================
    209: {"name": "Shatterglass", "category": "Crystal", "tier": 3, "status": "confirmed"},
    220: {"name": "Clockwork", "category": "Crystal", "tier": 3, "status": "confirmed"},
    230: {"name": "Frostburn", "category": "Crystal", "tier": 3, "status": "confirmed"},
    236: {"name": "Aftershock", "category": "Crystal", "tier": 3, "status": "confirmed"},
    240: {"name": "Broken Myth", "category": "Crystal", "tier": 3, "status": "confirmed"},
    253: {"name": "Alternating Current", "category": "Crystal", "tier": 3, "status": "confirmed"},
    255: {"name": "Eve of Harvest", "category": "Crystal", "tier": 3, "status": "confirmed"},

    # =========================================================================
    # Defense T1
    # =========================================================================
    211: {"name": "Light Shield", "category": "Defense", "tier": 1, "status": "tentative",
          "note": "276 buyers, very common (multi-buy for Aegis/shield items)"},
    212: {"name": "Oakheart", "category": "Defense", "tier": 1, "status": "tentative",
          "note": "202 buyers, HP component for Dragonheart and other tank items"},
    213: {"name": "Light Armor", "category": "Defense", "tier": 1, "status": "tentative",
          "note": "169 buyers, armor component"},
    215: {"name": "Light Armor", "category": "Defense", "tier": 1, "status": "tentative",
          "note": "Variant of ID 213. 12 buyers, rare"},
    245: {"name": "Light Shield", "category": "Defense", "tier": 1, "status": "tentative",
          "note": "Variant of ID 211. 122 buyers, transitions to Kinetic Shield(246)"},

    # =========================================================================
    # Defense T2
    # =========================================================================
    214: {"name": "Dragonheart", "category": "Defense", "tier": 2, "status": "tentative",
          "note": "108 buyers, HP component for Crucible(232), War Treads(241)"},
    228: {"name": "Coat of Plates", "category": "Defense", "tier": 2, "status": "tentative",
          "note": "4 buyers (Grumpjaw/BF/SanFeng/Catherine). Co-occurs with Light Armor(213) 100%, Atlas Pauldron(242) 75%"},
    229: {"name": "Reflex Block", "category": "Defense", "tier": 2, "status": "tentative",
          "note": "378 buyers, builds into Crucible(232)+Aegis(247)"},
    246: {"name": "Kinetic Shield", "category": "Defense", "tier": 2, "status": "tentative",
          "note": "85 buyers, builds into Aegis(247), Fountain(231)"},
    248: {"name": "Lifespring", "category": "Defense", "tier": 2, "status": "tentative",
          "note": "167 buyers, builds into Fountain(231)"},

    # =========================================================================
    # Defense T3
    # =========================================================================
    231: {"name": "Fountain of Renewal", "category": "Defense", "tier": 3, "status": "confirmed"},
    232: {"name": "Crucible", "category": "Defense", "tier": 3, "status": "confirmed"},
    242: {"name": "Atlas Pauldron", "category": "Defense", "tier": 3, "status": "confirmed"},
    247: {"name": "Aegis", "category": "Defense", "tier": 3, "status": "confirmed"},

    # =========================================================================
    # Utility / Boots
    # =========================================================================
    219: {"name": "Stormguard Banner", "category": "Utility", "tier": 2, "status": "tentative",
          "note": "139 buyers, captain/jungler utility"},
    221: {"name": "Sprint Boots", "category": "Utility", "tier": 1, "status": "tentative",
          "note": "426 buyers, universal T1 boots"},
    222: {"name": "Travel Boots", "category": "Utility", "tier": 2, "status": "tentative",
          "note": "429 buyers, universal T2 boots"},
    234: {"name": "Halcyon Chargers", "category": "Utility", "tier": 3, "status": "confirmed"},
    241: {"name": "War Treads", "category": "Utility", "tier": 3, "status": "confirmed"},

    # =========================================================================
    # Consumables / System
    # =========================================================================
    201: {"name": "Starting Item", "category": "System", "tier": 0, "status": "tentative",
          "note": "456 buyers (everyone), avg 13s. Auto-purchased at game start"},
    217: {"name": "Unknown 217", "category": "Unknown", "tier": 0, "status": "unknown",
          "note": "108 buyers, mixed roles (Lorelai 9, Samuel 8, Magnus 7). avg 604s. Could be Healing Flask or contract item"},
    225: {"name": "Scout Trap", "category": "Consumable", "tier": 0, "status": "tentative",
          "note": "13 captain buyers, qty up to 24x. Repeated purchase pattern = vision consumable"},
    233: {"name": "Unknown 233", "category": "Consumable", "tier": 0, "status": "unknown",
          "note": "4 buyers (Reim/Lorelai/Reza/Baron), avg 1316s. Very late-game, possibly Crystal Infusion"},
    238: {"name": "Flare", "category": "Consumable", "tier": 0, "status": "confirmed",
          "note": "CONFIRMED: vision consumable. Tanks buy x1-4"},
    239: {"name": "Unknown 239", "category": "Consumable", "tier": 0, "status": "unknown",
          "note": "7 captain buyers, qty 2-7. Co-occurs with Scout Trap(225) 86%. Another vision consumable?"},
    244: {"name": "Weapon Infusion", "category": "Consumable", "tier": 0, "status": "confirmed",
          "note": "CONFIRMED via replay viewer. Late-game WP buff consumable"},
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
