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
    53: {"name": "Karas", "name_ko": "카라스", "role": "Assassin"},
    54: {"name": "Shin", "name_ko": "신", "role": "Captain"},
    55: {"name": "Ishtar", "name_ko": "이슈타르", "role": "Sniper"},
    56: {"name": "Ylva", "name_ko": "일바", "role": "Assassin"},
    57: {"name": "Amael", "name_ko": "아마엘", "role": "Mage"},
}

# Reverse lookup: name to ID
HERO_NAME_TO_ID: Dict[str, int] = {
    info["name"].lower(): id for id, info in HERO_ID_MAP.items()
}

# Item ID Mapping
ITEM_ID_MAP: Dict[int, Dict] = {
    # Weapon - Basic
    101: {"name": "Weapon Blade", "category": "Weapon", "tier": 1},
    102: {"name": "Book of Eulogies", "category": "Weapon", "tier": 1},
    103: {"name": "Swift Shooter", "category": "Weapon", "tier": 1},
    104: {"name": "Minion's Foot", "category": "Weapon", "tier": 1},
    105: {"name": "Unknown Weapon 105", "category": "Weapon", "tier": 1, "status": "discovered"},
    106: {"name": "Unknown Weapon 106", "category": "Weapon", "tier": 1, "status": "discovered"},
    107: {"name": "Unknown Weapon 107", "category": "Weapon", "tier": 1, "status": "discovered"},
    108: {"name": "Unknown Weapon 108", "category": "Weapon", "tier": 1, "status": "discovered"},
    109: {"name": "Unknown Weapon 109", "category": "Weapon", "tier": 1, "status": "discovered"},
    110: {"name": "Unknown Weapon 110", "category": "Weapon", "tier": 1, "status": "discovered"},
    
    # Weapon - Tier 2
    111: {"name": "Heavy Steel", "category": "Weapon", "tier": 2},
    112: {"name": "Six Sins", "category": "Weapon", "tier": 2},
    113: {"name": "Blazing Salvo", "category": "Weapon", "tier": 2},
    114: {"name": "Lucky Strike", "category": "Weapon", "tier": 2},
    115: {"name": "Piercing Spear", "category": "Weapon", "tier": 2},
    116: {"name": "Barbed Needle", "category": "Weapon", "tier": 2},
    
    # Weapon - Tier 3
    # Note: Tier 3 items (121-129, 221-229, 321-328) are NOT stored with FF FF FF FF pattern
    # They use different storage mechanism when crafted from components
    121: {"name": "Sorrowblade", "category": "Weapon", "tier": 3},
    122: {"name": "Serpent Mask", "category": "Weapon", "tier": 3},
    123: {"name": "Tornado Trigger", "category": "Weapon", "tier": 3},
    124: {"name": "Tyrant's Monocle", "category": "Weapon", "tier": 3},
    125: {"name": "Bonesaw", "category": "Weapon", "tier": 3},
    126: {"name": "Poisoned Shiv", "category": "Weapon", "tier": 3},
    127: {"name": "Breaking Point", "category": "Weapon", "tier": 3},
    128: {"name": "Tension Bow", "category": "Weapon", "tier": 3},
    129: {"name": "Spellsword", "category": "Weapon", "tier": 3},
    
    # Crystal - Basic
    201: {"name": "Crystal Bit", "category": "Crystal", "tier": 1},
    202: {"name": "Energy Battery", "category": "Crystal", "tier": 1},
    203: {"name": "Hourglass", "category": "Crystal", "tier": 1},
    
    # Crystal - Tier 2
    211: {"name": "Eclipse Prism", "category": "Crystal", "tier": 2},
    212: {"name": "Heavy Prism", "category": "Crystal", "tier": 2},
    213: {"name": "Piercing Shard", "category": "Crystal", "tier": 2},
    214: {"name": "Chronograph", "category": "Crystal", "tier": 2},
    215: {"name": "Void Battery", "category": "Crystal", "tier": 2},
    
    # Crystal - Tier 3
    221: {"name": "Shatterglass", "category": "Crystal", "tier": 3},
    222: {"name": "Frostburn", "category": "Crystal", "tier": 3},
    223: {"name": "Eve of Harvest", "category": "Crystal", "tier": 3},
    224: {"name": "Broken Myth", "category": "Crystal", "tier": 3},
    225: {"name": "Clockwork", "category": "Crystal", "tier": 3},
    226: {"name": "Alternating Current", "category": "Crystal", "tier": 3},
    227: {"name": "Dragon's Eye", "category": "Crystal", "tier": 3},
    228: {"name": "Spellfire", "category": "Crystal", "tier": 3},
    229: {"name": "Aftershock", "category": "Crystal", "tier": 3},
    
    # Defense - Basic
    301: {"name": "Light Shield", "category": "Defense", "tier": 1},
    302: {"name": "Light Armor", "category": "Defense", "tier": 1},
    303: {"name": "Oakheart", "category": "Defense", "tier": 1},
    
    # Defense - Tier 2
    311: {"name": "Kinetic Shield", "category": "Defense", "tier": 2},
    312: {"name": "Coat of Plates", "category": "Defense", "tier": 2},
    313: {"name": "Dragonheart", "category": "Defense", "tier": 2},
    314: {"name": "Reflex Block", "category": "Defense", "tier": 2},
    
    # Defense - Tier 3
    321: {"name": "Aegis", "category": "Defense", "tier": 3},
    322: {"name": "Metal Jacket", "category": "Defense", "tier": 3},
    323: {"name": "Fountain of Renewal", "category": "Defense", "tier": 3},
    324: {"name": "Crucible", "category": "Defense", "tier": 3},
    325: {"name": "Atlas Pauldron", "category": "Defense", "tier": 3},
    326: {"name": "Slumbering Husk", "category": "Defense", "tier": 3},
    327: {"name": "Pulseweave", "category": "Defense", "tier": 3},
    328: {"name": "Capacitor Plate", "category": "Defense", "tier": 3},
    
    # Utility - Boots
    401: {"name": "Sprint Boots", "category": "Utility", "tier": 1},
    402: {"name": "Travel Boots", "category": "Utility", "tier": 2},
    403: {"name": "Journey Boots", "category": "Utility", "tier": 3},
    404: {"name": "Halcyon Chargers", "category": "Utility", "tier": 3},
    405: {"name": "War Treads", "category": "Utility", "tier": 3},
    406: {"name": "Teleport Boots", "category": "Utility", "tier": 3},
    
    # Utility - Vision
    411: {"name": "Flare", "category": "Utility", "tier": 1},
    412: {"name": "Scout Trap", "category": "Utility", "tier": 1},
    413: {"name": "Flare Gun", "category": "Utility", "tier": 2},
    414: {"name": "Contraption", "category": "Utility", "tier": 3},
    415: {"name": "Superscout 2000", "category": "Utility", "tier": 3},
    
    # Utility - Other
    421: {"name": "Nullwave Gauntlet", "category": "Utility", "tier": 3},
    422: {"name": "Echo", "category": "Utility", "tier": 3},
    423: {"name": "Stormcrown", "category": "Utility", "tier": 3},

    # System Items
    188: {"name": "System Item 188", "category": "System", "tier": 0, "status": "system"},
    255: {"name": "Marker 255", "category": "System", "tier": 0, "status": "marker"},
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
