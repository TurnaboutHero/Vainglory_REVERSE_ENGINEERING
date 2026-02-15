#!/usr/bin/env python3
"""
Hero ID Correlator - Find bytes in player blocks that are CONSISTENT per hero.

Strategy: Group players by known hero, then for each byte offset, check if
the value is always the same for the same hero AND different between heroes.
This finds the hero ID regardless of which numbering system is used.
"""

import json
import struct
import sys
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Tuple, Optional, Any, Set

PLAYER_BLOCK_MARKER = bytes([0xDA, 0x03, 0xEE])
PLAYER_BLOCK_MARKER_ALT = bytes([0xE0, 0x03, 0xEE])
SCAN_RANGE = 0x150  # Extended scan range

# Hero name normalization
HERO_NORM = {
    "mallene": "Malene", "ishutar": "Ishtar", "san feng": "San Feng",
}

def normalize_hero(name: str) -> str:
    n = HERO_NORM.get(name.lower().strip(), name.strip())
    return n


def find_player_blocks(data: bytes) -> List[Tuple[int, str]]:
    blocks = []
    search_start = 0
    markers = (PLAYER_BLOCK_MARKER, PLAYER_BLOCK_MARKER_ALT)
    seen = set()
    while True:
        pos = -1
        marker = None
        for candidate in markers:
            idx = data.find(candidate, search_start)
            if idx != -1 and (pos == -1 or idx < pos):
                pos = idx
                marker = candidate
        if pos == -1 or marker is None:
            break
        name_start = pos + len(marker)
        name_end = name_start
        while name_end < len(data) and name_end < name_start + 30:
            byte = data[name_end]
            if byte < 32 or byte > 126:
                break
            name_end += 1
        if name_end > name_start:
            try:
                name = data[name_start:name_end].decode('ascii')
            except Exception:
                name = ""
            if len(name) >= 3 and not name.startswith('GameMode') and name not in seen:
                blocks.append((pos, name))
                seen.add(name)
        search_start = pos + 1
    return blocks


def load_all_player_blocks(truth_path: Path) -> List[Dict]:
    """Load all player blocks with truth data."""
    with open(truth_path, 'r', encoding='utf-8') as f:
        truth = json.load(f)

    all_blocks = []
    for match in truth.get("matches", []):
        replay_file = match.get("replay_file", "")
        players = match.get("players", {})
        replay_name = match.get("replay_name", "")

        path = Path(replay_file)
        if not path.exists():
            continue

        data = path.read_bytes()
        blocks = find_player_blocks(data)

        # Also search for hero name strings near player blocks
        for block_pos, player_name in blocks:
            # Match to truth
            truth_entry = None
            truth_key = None
            for tname, tdata in players.items():
                clean_t = tname.split("_", 1)[-1] if "_" in tname else tname
                clean_p = player_name.split("_", 1)[-1] if "_" in player_name else player_name
                if (player_name == tname or
                    player_name.lower() == tname.lower() or
                    clean_p.lower() == clean_t.lower()):
                    truth_entry = tdata
                    truth_key = tname
                    break

            if not truth_entry:
                continue

            hero_name = normalize_hero(truth_entry["hero_name"])
            block_end = min(block_pos + SCAN_RANGE, len(data))
            block_bytes = data[block_pos:block_end]

            # Also scan wider area for hero name strings
            wide_start = max(0, block_pos - 256)
            wide_end = min(len(data), block_pos + 1024)
            wide_data = data[wide_start:wide_end]

            all_blocks.append({
                "player_name": truth_key,
                "hero_name": hero_name,
                "replay_name": replay_name,
                "block_pos": block_pos,
                "block_bytes": block_bytes,
                "block_len": len(block_bytes),
                "wide_data": wide_data,
                "wide_offset": block_pos - wide_start,
            })

    return all_blocks


def find_hero_name_strings(all_blocks: List[Dict]):
    """Search for hero name strings anywhere near player blocks."""
    print("\n" + "=" * 80)
    print("SEARCHING FOR HERO NAME STRINGS NEAR PLAYER BLOCKS")
    print("=" * 80)

    # Known hero names to search for
    hero_names = [
        "SAW", "Ringo", "Taka", "Krul", "Skaarf", "Celeste", "Vox", "Catherine",
        "Ardan", "Glaive", "Joule", "Koshka", "Petal", "Adagio", "Rona", "Fortress",
        "Reim", "Phinn", "Blackfeather", "Skye", "Kestrel", "Alpha", "Lance", "Ozo",
        "Lyra", "Samuel", "Baron", "Gwen", "Flicker", "Idris", "Grumpjaw", "Baptiste",
        "Grace", "Reza", "Churnwalker", "Lorelai", "Tony", "Varya", "Malene", "Kensei",
        "Kinetic", "San Feng", "Silvernail", "Yates", "Inara", "Magnus", "Caine", "Leo",
        "Warhawk", "Anka", "Miho", "Amael", "Ishtar", "Karas", "Shin", "Ylva", "Viola",
    ]
    # Also search for asset path patterns
    asset_patterns = [
        b"Hero0", b"Hero1", b"Characters/", b"/Hero",
        b"hero_", b"Hero_",
    ]

    found_count = 0
    for block in all_blocks[:20]:  # Check first 20 blocks
        wide = block["wide_data"]
        player = block["player_name"]
        hero = block["hero_name"]
        wide_off = block["wide_offset"]

        # Search for the expected hero name
        for name in hero_names:
            name_bytes = name.encode('ascii')
            idx = wide.find(name_bytes)
            while idx != -1:
                rel_pos = idx - wide_off
                context_start = max(0, idx - 10)
                context_end = min(len(wide), idx + len(name_bytes) + 10)
                context = wide[context_start:context_end]
                if name.lower() == hero.lower():
                    print(f"  [MATCH] {player} ({hero}): Found '{name}' at relative offset {rel_pos:+d}")
                    print(f"          Context: {context.hex()}")
                    print(f"          ASCII:   {context.decode('ascii', errors='replace')}")
                    found_count += 1
                idx = wide.find(name_bytes, idx + 1)

        # Search for asset patterns
        for pattern in asset_patterns:
            idx = wide.find(pattern)
            while idx != -1:
                rel_pos = idx - wide_off
                context_end = min(len(wide), idx + 40)
                context = wide[idx:context_end]
                ascii_ctx = context.decode('ascii', errors='replace')
                print(f"  [ASSET] {player} ({hero}): Pattern at relative offset {rel_pos:+d}")
                print(f"          ASCII: {ascii_ctx}")
                found_count += 1
                idx = wide.find(pattern, idx + 1)

    if found_count == 0:
        print("  No hero name strings found near player blocks.")
    return found_count


def correlate_bytes_per_hero(all_blocks: List[Dict]) -> List[Dict]:
    """
    For each byte offset, group values by hero name.
    Find offsets where the same hero ALWAYS has the same value.
    Then check uniqueness across heroes.
    """
    # Group blocks by hero
    hero_groups: Dict[str, List[bytes]] = defaultdict(list)
    for block in all_blocks:
        hero_groups[block["hero_name"]].append(block["block_bytes"])

    max_offset = min(SCAN_RANGE, min(len(b) for blocks in hero_groups.values() for b in blocks))

    # For each offset, check consistency
    results = []
    for off in range(max_offset):
        # For each hero, collect the set of values at this offset
        hero_values: Dict[str, Set[int]] = {}
        hero_value_lists: Dict[str, List[int]] = defaultdict(list)

        for hero, blocks in hero_groups.items():
            vals = set()
            for b in blocks:
                if off < len(b):
                    vals.add(b[off])
                    hero_value_lists[hero].append(b[off])
            hero_values[hero] = vals

        # Check: how many heroes have exactly 1 unique value at this offset?
        consistent_heroes = {h: vals for h, vals in hero_values.items() if len(vals) == 1}
        total_heroes = len(hero_values)
        consistent_count = len(consistent_heroes)

        if consistent_count < total_heroes * 0.5:
            continue  # Not consistent enough

        # Now check uniqueness: are the consistent values different between heroes?
        value_to_heroes: Dict[int, List[str]] = defaultdict(list)
        for hero, vals in consistent_heroes.items():
            val = list(vals)[0]
            value_to_heroes[val].append(hero)

        unique_values = len(value_to_heroes)
        # If each hero has a unique value, this is a perfect hero ID offset
        max_collision = max(len(heroes) for heroes in value_to_heroes.values()) if value_to_heroes else 0

        results.append({
            "offset": off,
            "offset_hex": f"0x{off:03X}",
            "consistent_heroes": consistent_count,
            "total_heroes": total_heroes,
            "consistency_ratio": round(consistent_count / total_heroes, 4) if total_heroes > 0 else 0,
            "unique_values": unique_values,
            "max_collision": max_collision,
            "value_map": {
                hero: list(vals)[0] if len(vals) == 1 else sorted(vals)
                for hero, vals in hero_values.items()
            },
        })

    # Sort by consistency ratio (descending), then unique values (descending)
    results.sort(key=lambda x: (-x["consistency_ratio"], -x["unique_values"], x["max_collision"]))
    return results


def correlate_2byte_per_hero(all_blocks: List[Dict]) -> List[Dict]:
    """Same as correlate_bytes_per_hero but for 2-byte LE values."""
    hero_groups: Dict[str, List[bytes]] = defaultdict(list)
    for block in all_blocks:
        hero_groups[block["hero_name"]].append(block["block_bytes"])

    max_offset = min(SCAN_RANGE - 1, min(len(b) for blocks in hero_groups.values() for b in blocks) - 1)

    results = []
    for off in range(max_offset):
        hero_values: Dict[str, Set[int]] = {}
        for hero, blocks in hero_groups.items():
            vals = set()
            for b in blocks:
                if off + 2 <= len(b):
                    val = int.from_bytes(b[off:off+2], 'little')
                    vals.add(val)
            hero_values[hero] = vals

        consistent_heroes = {h: vals for h, vals in hero_values.items() if len(vals) == 1}
        total_heroes = len(hero_values)
        consistent_count = len(consistent_heroes)

        if consistent_count < total_heroes * 0.5:
            continue

        value_to_heroes: Dict[int, List[str]] = defaultdict(list)
        for hero, vals in consistent_heroes.items():
            val = list(vals)[0]
            value_to_heroes[val].append(hero)

        unique_values = len(value_to_heroes)
        max_collision = max(len(heroes) for heroes in value_to_heroes.values()) if value_to_heroes else 0

        results.append({
            "offset": off,
            "offset_hex": f"0x{off:03X}",
            "type": "uint16_le",
            "consistent_heroes": consistent_count,
            "total_heroes": total_heroes,
            "consistency_ratio": round(consistent_count / total_heroes, 4) if total_heroes > 0 else 0,
            "unique_values": unique_values,
            "max_collision": max_collision,
            "value_map": {
                hero: list(vals)[0] if len(vals) == 1 else sorted(vals)
                for hero, vals in hero_values.items()
            },
        })

    results.sort(key=lambda x: (-x["consistency_ratio"], -x["unique_values"], x["max_collision"]))
    return results


def correlate_4byte_per_hero(all_blocks: List[Dict]) -> List[Dict]:
    """Same for 4-byte LE values."""
    hero_groups: Dict[str, List[bytes]] = defaultdict(list)
    for block in all_blocks:
        hero_groups[block["hero_name"]].append(block["block_bytes"])

    max_offset = min(SCAN_RANGE - 3, min(len(b) for blocks in hero_groups.values() for b in blocks) - 3)

    results = []
    for off in range(max_offset):
        hero_values: Dict[str, Set[int]] = {}
        for hero, blocks in hero_groups.items():
            vals = set()
            for b in blocks:
                if off + 4 <= len(b):
                    val = int.from_bytes(b[off:off+4], 'little')
                    vals.add(val)
            hero_values[hero] = vals

        consistent_heroes = {h: vals for h, vals in hero_values.items() if len(vals) == 1}
        total_heroes = len(hero_values)
        consistent_count = len(consistent_heroes)

        if consistent_count < total_heroes * 0.7:
            continue

        value_to_heroes: Dict[int, List[str]] = defaultdict(list)
        for hero, vals in consistent_heroes.items():
            val = list(vals)[0]
            value_to_heroes[val].append(hero)

        unique_values = len(value_to_heroes)
        max_collision = max(len(heroes) for heroes in value_to_heroes.values()) if value_to_heroes else 0

        results.append({
            "offset": off,
            "offset_hex": f"0x{off:03X}",
            "type": "uint32_le",
            "consistent_heroes": consistent_count,
            "total_heroes": total_heroes,
            "consistency_ratio": round(consistent_count / total_heroes, 4) if total_heroes > 0 else 0,
            "unique_values": unique_values,
            "max_collision": max_collision,
            "value_map": {
                hero: list(vals)[0] if len(vals) == 1 else sorted(vals)
                for hero, vals in hero_values.items()
            },
        })

    results.sort(key=lambda x: (-x["consistency_ratio"], -x["unique_values"], x["max_collision"]))
    return results


def main():
    truth_path = Path(__file__).parent.parent / "output" / "tournament_truth.json"
    if not truth_path.exists():
        print(f"Truth data not found: {truth_path}")
        return

    print("Loading player blocks from replays...")
    all_blocks = load_all_player_blocks(truth_path)
    print(f"Loaded {len(all_blocks)} player blocks")

    heroes = set(b["hero_name"] for b in all_blocks)
    print(f"Unique heroes: {len(heroes)}: {sorted(heroes)}")

    # Phase 1: Search for hero name strings
    find_hero_name_strings(all_blocks)

    # Phase 2: Single byte correlation
    print("\n" + "=" * 80)
    print("PHASE 2: SINGLE BYTE CORRELATION PER HERO")
    print("=" * 80)
    byte_results = correlate_bytes_per_hero(all_blocks)
    print(f"\nTop 20 offsets (single byte, consistent & unique per hero):")
    print(f"{'Offset':<10} {'Consistent':>10} {'Total':>6} {'Ratio':>8} {'UniqueVals':>10} {'MaxCollision':>12}")
    print("-" * 60)
    for r in byte_results[:20]:
        print(f"{r['offset_hex']:<10} {r['consistent_heroes']:>10} {r['total_heroes']:>6} {r['consistency_ratio']:>8.1%} {r['unique_values']:>10} {r['max_collision']:>12}")

    # Show the value map for the best offset
    if byte_results:
        best = byte_results[0]
        print(f"\n--- Best single-byte offset: {best['offset_hex']} ---")
        print(f"{'Hero':<20} {'Value':>6} {'Hex':>6}")
        print("-" * 35)
        for hero in sorted(best["value_map"].keys()):
            val = best["value_map"][hero]
            if isinstance(val, int):
                print(f"{hero:<20} {val:>6} {val:>5X}h")
            else:
                print(f"{hero:<20} {str(val):>6}")

    # Phase 3: 2-byte correlation
    print("\n" + "=" * 80)
    print("PHASE 3: 2-BYTE (UINT16 LE) CORRELATION PER HERO")
    print("=" * 80)
    u16_results = correlate_2byte_per_hero(all_blocks)
    print(f"\nTop 20 offsets (uint16 LE, consistent & unique per hero):")
    print(f"{'Offset':<10} {'Consistent':>10} {'Total':>6} {'Ratio':>8} {'UniqueVals':>10} {'MaxCollision':>12}")
    print("-" * 60)
    for r in u16_results[:20]:
        print(f"{r['offset_hex']:<10} {r['consistent_heroes']:>10} {r['total_heroes']:>6} {r['consistency_ratio']:>8.1%} {r['unique_values']:>10} {r['max_collision']:>12}")

    if u16_results:
        best_u16 = u16_results[0]
        print(f"\n--- Best uint16 offset: {best_u16['offset_hex']} ---")
        print(f"{'Hero':<20} {'Value':>8} {'Hex':>8}")
        print("-" * 40)
        for hero in sorted(best_u16["value_map"].keys()):
            val = best_u16["value_map"][hero]
            if isinstance(val, int):
                print(f"{hero:<20} {val:>8} {val:>7X}h")
            else:
                print(f"{hero:<20} {str(val):>8}")

    # Phase 4: 4-byte correlation
    print("\n" + "=" * 80)
    print("PHASE 4: 4-BYTE (UINT32 LE) CORRELATION PER HERO")
    print("=" * 80)
    u32_results = correlate_4byte_per_hero(all_blocks)
    print(f"\nTop 20 offsets (uint32 LE, consistent & unique per hero):")
    print(f"{'Offset':<10} {'Consistent':>10} {'Total':>6} {'Ratio':>8} {'UniqueVals':>10} {'MaxCollision':>12}")
    print("-" * 60)
    for r in u32_results[:20]:
        print(f"{r['offset_hex']:<10} {r['consistent_heroes']:>10} {r['total_heroes']:>6} {r['consistency_ratio']:>8.1%} {r['unique_values']:>10} {r['max_collision']:>12}")

    if u32_results:
        best_u32 = u32_results[0]
        print(f"\n--- Best uint32 offset: {best_u32['offset_hex']} ---")
        print(f"{'Hero':<20} {'Value':>12} {'Hex':>10}")
        print("-" * 45)
        for hero in sorted(best_u32["value_map"].keys()):
            val = best_u32["value_map"][hero]
            if isinstance(val, int):
                print(f"{hero:<20} {val:>12} {val:>9X}h")
            else:
                print(f"{hero:<20} {str(val):>12}")

    # Save results
    output = {
        "total_blocks": len(all_blocks),
        "unique_heroes": sorted(heroes),
        "best_byte_offsets": byte_results[:10],
        "best_u16_offsets": u16_results[:10],
        "best_u32_offsets": u32_results[:10],
    }
    output_path = Path(__file__).parent.parent / "output" / "hero_id_correlation.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to: {output_path}")


if __name__ == "__main__":
    main()
