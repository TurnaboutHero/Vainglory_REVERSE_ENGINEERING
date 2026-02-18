#!/usr/bin/env python3
"""
Cross-reference measured item prices (from gold deductions) with official VG prices.
Identifies WRONG mappings where measured price doesn't match official price.
"""

# Official VG item prices from NamuWiki (verified)
OFFICIAL_PRICES = {
    # T1 (all 300g except Hourglass 250g)
    "Weapon Blade": 300, "Book of Eulogies": 300, "Swift Shooter": 300,
    "Minion's Foot": 300, "Crystal Bit": 300, "Energy Battery": 300,
    "Hourglass": 250, "Oakheart": 300, "Light Shield": 300,
    "Light Armor": 300, "Sprint Boots": 300,

    # T2 Weapon
    "Heavy Steel": 1150, "Six Sins": 650, "Barbed Needle": 800,
    "Piercing Spear": 900, "Blazing Salvo": 700, "Lucky Strike": 900,

    # T2 Crystal
    "Heavy Prism": 1050, "Eclipse Prism": 650, "Void Battery": 700,
    "Piercing Shard": 900, "Chronograph": 800,

    # T2 Defense
    "Dragonheart": 650, "Lifespring": 800, "Reflex Block": 700,
    "Protector Contract": 600, "Kinetic Shield": 750, "Warmail": 800,
    "Coat of Plates": 750,

    # T2 Utility
    "Travel Boots": 800, "Flare Gun": 600, "Stormguard Banner": 600,

    # T3 Weapon
    "Sorrowblade": 3100, "Serpent Mask": 2800, "Spellsword": 2800,
    "Poisoned Shiv": 2750, "Breaking Point": 2700, "Tension Bow": 2900,
    "Bonesaw": 2900, "Tornado Trigger": 2800, "Tyrants Monocle": 2750,

    # T3 Crystal
    "Shatterglass": 3000, "Spellfire": 2700, "Frostburn": 2700,
    "Dragons Eye": 3000, "Clockwork": 2400, "Broken Myth": 2900,
    "Eve of Harvest": 2600, "Aftershock": 2600, "Alternating Current": 2800,

    # T3 Defense
    "Pulseweave": 2300, "Crucible": 1850, "Capacitor Plate": 2100,
    "Rooks Decree": 2200, "Fountain of Renewal": 2300, "Aegis": 2250,
    "Slumbering Husk": 2350, "Metal Jacket": 2000, "Atlas Pauldron": 1900,

    # T3 Utility
    "Teleport Boots": 1600, "Journey Boots": 1700, "War Treads": 1900,
    "Halcyon Chargers": 1700, "Contraption": 2100, "Stormcrown": 2000,
    "Shiversteel": 1950,

    # Consumables
    "Flare": 25, "Scout Trap": 50, "Minion Candy": 75,
    "ScoutPak": 500, "ScoutTuff": 500, "SuperScout 2000": 2000,
    "Weapon Infusion": 500, "Crystal Infusion": 500,
    "Ironguard Contract": 250, "Dragonblood Contract": 250,
}

# Build recipe: item -> (component1, component2_or_None, recipe_cost)
OFFICIAL_RECIPES = {
    # T2 Weapon
    "Heavy Steel": ("Weapon Blade", None, 850),
    "Six Sins": ("Weapon Blade", None, 350),
    "Barbed Needle": ("Book of Eulogies", None, 500),
    "Piercing Spear": ("Weapon Blade", None, 600),
    "Blazing Salvo": ("Swift Shooter", None, 400),
    "Lucky Strike": ("Minion's Foot", None, 600),

    # T2 Crystal
    "Heavy Prism": ("Crystal Bit", None, 750),
    "Eclipse Prism": ("Crystal Bit", None, 350),
    "Void Battery": ("Energy Battery", None, 400),
    "Piercing Shard": ("Crystal Bit", None, 600),
    "Chronograph": ("Hourglass", None, 550),

    # T2 Defense
    "Dragonheart": ("Oakheart", None, 350),
    "Lifespring": ("Oakheart", None, 500),
    "Reflex Block": ("Oakheart", None, 400),
    "Protector Contract": ("Oakheart", None, 300),
    "Kinetic Shield": ("Light Shield", None, 450),
    "Warmail": ("Light Armor", "Light Shield", 200),
    "Coat of Plates": ("Light Armor", None, 450),

    # T2 Utility
    "Travel Boots": ("Sprint Boots", None, 500),
    "Flare Gun": ("Oakheart", None, 300),
    "Stormguard Banner": ("Oakheart", None, 300),

    # T3 Weapon
    "Sorrowblade": ("Heavy Steel", "Six Sins", 1300),
    "Serpent Mask": ("Heavy Steel", "Barbed Needle", 850),
    "Spellsword": ("Heavy Steel", "Chronograph", 750),
    "Poisoned Shiv": ("Blazing Salvo", "Barbed Needle", 1300),
    "Breaking Point": ("Heavy Steel", "Blazing Salvo", 850),
    "Tension Bow": ("Six Sins", "Piercing Spear", 1350),
    "Bonesaw": ("Piercing Spear", "Blazing Salvo", 1300),
    "Tornado Trigger": ("Blazing Salvo", "Lucky Strike", 1000),
    "Tyrants Monocle": ("Six Sins", "Lucky Strike", 1200),

    # T3 Crystal
    "Shatterglass": ("Heavy Prism", "Eclipse Prism", 1300),
    "Spellfire": ("Heavy Prism", "Eclipse Prism", 1000),
    "Frostburn": ("Heavy Prism", "Eclipse Prism", 900),
    "Dragons Eye": ("Heavy Prism", "Eclipse Prism", 1300),
    "Clockwork": ("Void Battery", "Chronograph", 1000),
    "Broken Myth": ("Heavy Prism", "Piercing Shard", 950),
    "Eve of Harvest": ("Heavy Prism", "Void Battery", 850),
    "Aftershock": ("Eclipse Prism", "Chronograph", 1150),
    "Alternating Current": ("Heavy Prism", "Blazing Salvo", 1050),

    # T3 Defense
    "Pulseweave": ("Dragonheart", "Lifespring", 850),
    "Crucible": ("Dragonheart", "Reflex Block", 500),
    "Capacitor Plate": ("Dragonheart", "Chronograph", 650),
    "Rooks Decree": ("Dragonheart", "Chronograph", 750),
    "Fountain of Renewal": ("Lifespring", "Kinetic Shield", 700),
    "Aegis": ("Reflex Block", "Kinetic Shield", 750),
    "Slumbering Husk": ("Coat of Plates", "Kinetic Shield", 750),
    "Metal Jacket": ("Coat of Plates", None, 1200),
    "Atlas Pauldron": ("Coat of Plates", None, 1100),

    # T3 Utility
    "Teleport Boots": ("Travel Boots", None, 800),
    "Journey Boots": ("Travel Boots", None, 900),
    "War Treads": ("Travel Boots", "Dragonheart", 450),
    "Halcyon Chargers": ("Travel Boots", "Void Battery", 200),
    "Contraption": ("Flare Gun", "Chronograph", 700),
    "Stormcrown": ("Stormguard Banner", "Chronograph", 600),
    "Shiversteel": ("Dragonheart", "Blazing Salvo", 600),

    # Consumable T2/T3
    "ScoutPak": ("Hourglass", None, 250),
    "ScoutTuff": ("Flare Gun", None, 200),  # actually unclear
    "SuperScout 2000": ("ScoutPak", "ScoutTuff", 1000),
}

# Our measured prices from -24 offset
MEASURED_PRICES = {
    0: 1050, 1: 600, 5: 300, 8: 2750, 11: 3000, 13: 2100,
    16: 500, 17: 500, 18: 1400, 20: 300, 21: 2000, 22: 2000,
    23: 600, 24: 600, 26: 800,
    202: 300, 203: 300, 204: 300, 205: 650, 206: 650, 207: 700,
    209: 3000, 211: 300, 212: 650, 213: 300, 214: 750, 216: 300,
    217: 250, 218: 700, 219: 800, 220: 2400, 221: 300, 222: 650,
    229: 700, 233: 1400, 234: 1400, 235: 2900, 237: 500, 238: 500,
    241: 1600, 243: 300, 244: 800, 245: 300, 246: 750, 247: 2400,
    248: 800, 249: 1150, 250: 900, 251: 2700, 252: 900, 254: 900,
    255: 2600,
}

# Current mapping from vgr_mapping.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from vg.core.vgr_mapping import ITEM_ID_MAP


def find_matching_items(price):
    """Find all official items matching a given price."""
    return [name for name, p in OFFICIAL_PRICES.items() if p == price]


def main():
    print("=" * 90)
    print("ITEM MAPPING VERIFICATION: Measured Price vs Official Price")
    print("=" * 90)

    correct = []
    wrong = []
    unknown = []

    for iid, measured in sorted(MEASURED_PRICES.items()):
        info = ITEM_ID_MAP.get(iid, {})
        current_name = info.get("name", "UNMAPPED")
        status = info.get("status", "?")
        tier = info.get("tier", "?")

        official_price = OFFICIAL_PRICES.get(current_name)

        if official_price is not None:
            if official_price == measured:
                correct.append((iid, current_name, measured, status))
            else:
                # Check recipe cost too
                recipe = OFFICIAL_RECIPES.get(current_name)
                recipe_cost = recipe[2] if recipe else None
                candidates = find_matching_items(measured)
                wrong.append((iid, current_name, measured, official_price, recipe_cost, candidates, status))
        else:
            candidates = find_matching_items(measured)
            unknown.append((iid, current_name, measured, candidates, status))

    # Print results
    print(f"\n{'='*70}")
    print(f"CORRECT MAPPINGS ({len(correct)} items) - Measured = Official")
    print(f"{'='*70}")
    for iid, name, price, status in correct:
        print(f"  ID {iid:>3}: {name:<28} {price:>5}g  [{status}]")

    print(f"\n{'='*70}")
    print(f"WRONG MAPPINGS ({len(wrong)} items) - Measured != Official")
    print(f"{'='*70}")
    for iid, name, measured, official, recipe_cost, candidates, status in wrong:
        recipe_match = " (=recipe)" if recipe_cost == measured else ""
        print(f"\n  ID {iid:>3}: '{name}' [{status}]")
        print(f"    Measured: {measured}g | Official '{name}': {official}g{recipe_match}")
        print(f"    Items at {measured}g: {candidates}")

    print(f"\n{'='*70}")
    print(f"UNKNOWN/UNMAPPED ({len(unknown)} items)")
    print(f"{'='*70}")
    for iid, name, measured, candidates, status in unknown:
        print(f"  ID {iid:>3}: '{name}' [{status}] measured={measured}g")
        print(f"    Items at {measured}g: {candidates}")


if __name__ == "__main__":
    main()
