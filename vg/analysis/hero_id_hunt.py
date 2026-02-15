#!/usr/bin/env python3
"""
Hero ID Hunt - Find where hero IDs are stored in player blocks.

Strategy:
1. Read replays with known truth data (hero assignments)
2. Find each player block (DA 03 EE marker)
3. For each byte offset in the player block, check if the value
   matches any known hero ID mapping
4. Cross-reference across all players/replays to find consistent offset
"""

import json
import struct
import sys
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Tuple, Optional, Any

# Hero ID mappings to test against
# ASSET_HERO_ID_MAP: folder numbers from game assets
ASSET_HERO_IDS = {
    "SAW": 9, "Ringo": 10, "Taka": 11, "Krul": 12,
    "Skaarf": 13, "Celeste": 14, "Vox": 15, "Catherine": 16,
    "Ardan": 17, "Glaive": 19, "Joule": 20, "Koshka": 21,
    "Petal": 23, "Adagio": 24, "Rona": 25, "Fortress": 27,
    "Reim": 28, "Phinn": 29, "Blackfeather": 30, "Skye": 31,
    "Kestrel": 36, "Alpha": 37, "Lance": 38, "Ozo": 39,
    "Lyra": 40, "Samuel": 41, "Baron": 42, "Gwen": 44,
    "Flicker": 45, "Idris": 46, "Grumpjaw": 47, "Baptiste": 48,
    "Grace": 54, "Reza": 55, "Churnwalker": 58, "Lorelai": 59,
    "Tony": 60, "Varya": 61, "Malene": 62, "Kensei": 63,
    "Kinetic": 64, "San Feng": 65, "Silvernail": 66, "Yates": 67,
    "Inara": 68, "Magnus": 69, "Caine": 70, "Leo": 71,
    "Warhawk": 22, "Anka": 32, "Miho": 56, "Amael": 72,
    "Ishtar": 75, "Karas": 82, "Shin": 103,
}

# HERO_ID_MAP: sequential IDs from vgr_mapping.py
SEQ_HERO_IDS = {
    "Adagio": 1, "Catherine": 2, "Glaive": 3, "Koshka": 4,
    "Krul": 5, "Petal": 6, "Ringo": 7, "SAW": 8,
    "Skaarf": 9, "Taka": 10, "Joule": 11, "Ardan": 12,
    "Celeste": 13, "Vox": 14, "Rona": 15, "Fortress": 16,
    "Reim": 17, "Phinn": 18, "Blackfeather": 19, "Skye": 20,
    "Kestrel": 21, "Alpha": 22, "Lance": 23, "Ozo": 24,
    "Lyra": 25, "Samuel": 26, "Baron": 27, "Gwen": 28,
    "Flicker": 29, "Idris": 30, "Grumpjaw": 31, "Baptiste": 32,
    "Grace": 33, "Reza": 34, "Churnwalker": 35, "Lorelai": 36,
    "Tony": 37, "Varya": 38, "Malene": 39, "Kensei": 40,
    "Kinetic": 41, "San Feng": 42, "Silvernail": 43, "Yates": 44,
    "Inara": 45, "Magnus": 46, "Caine": 47, "Leo": 48,
    "Viola": 49, "Warhawk": 50, "Anka": 51, "Miho": 52,
    "Karas": 53, "Shin": 54, "Ishtar": 55, "Ylva": 56,
    "Amael": 57,
}

# Hero name normalization
HERO_NAME_NORM = {
    "mallene": "Malene",
    "san feng": "San Feng",
}

def normalize_hero(name: str) -> str:
    n = HERO_NAME_NORM.get(name.lower(), name)
    # Title case for consistency
    for key in ASSET_HERO_IDS:
        if key.lower() == n.lower():
            return key
    return n

PLAYER_BLOCK_MARKER = bytes([0xDA, 0x03, 0xEE])
PLAYER_BLOCK_MARKER_ALT = bytes([0xE0, 0x03, 0xEE])
SCAN_RANGE = 0x120  # How far past the marker to scan


def find_player_blocks(data: bytes) -> List[Tuple[int, str]]:
    """Find all player blocks and extract (position, player_name)."""
    blocks = []
    search_start = 0
    markers = (PLAYER_BLOCK_MARKER, PLAYER_BLOCK_MARKER_ALT)

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
            if len(name) >= 3 and not name.startswith('GameMode'):
                blocks.append((pos, name))

        search_start = pos + 1

    return blocks


def analyze_replay(replay_path: str, truth_players: Dict[str, Dict]) -> List[Dict]:
    """Analyze a single replay against truth data."""
    path = Path(replay_path)
    if not path.exists():
        print(f"  [SKIP] File not found: {replay_path}")
        return []

    data = path.read_bytes()
    blocks = find_player_blocks(data)

    results = []
    seen_names = set()

    for block_pos, player_name in blocks:
        if player_name in seen_names:
            continue
        seen_names.add(player_name)

        # Find matching truth entry (fuzzy)
        truth_entry = None
        truth_key = None
        for tname, tdata in truth_players.items():
            # Try exact match or suffix match
            clean_tname = tname.split("_", 1)[-1] if "_" in tname else tname
            clean_pname = player_name.split("_", 1)[-1] if "_" in player_name else player_name
            if (player_name == tname or
                player_name.lower() == tname.lower() or
                clean_pname.lower() == clean_tname.lower()):
                truth_entry = tdata
                truth_key = tname
                break

        if not truth_entry:
            continue

        hero_name = normalize_hero(truth_entry["hero_name"])
        asset_id = ASSET_HERO_IDS.get(hero_name)
        seq_id = SEQ_HERO_IDS.get(hero_name)

        if not asset_id and not seq_id:
            print(f"  [WARN] Unknown hero: {hero_name}")
            continue

        # Extract bytes around the player block
        block_end = min(block_pos + SCAN_RANGE, len(data))
        block_data = data[block_pos:block_end]

        # Record match info
        result = {
            "player_name": truth_key,
            "block_player_name": player_name,
            "hero_name": hero_name,
            "asset_id": asset_id,
            "seq_id": seq_id,
            "block_pos": block_pos,
            "entity_id": int.from_bytes(data[block_pos+0xA5:block_pos+0xA5+2], 'little') if block_pos+0xA5+2 <= len(data) else None,
            "team_id": data[block_pos+0xD5] if block_pos+0xD5 < len(data) else None,
            "block_bytes": block_data,
        }
        results.append(result)

    return results


def search_hero_id_at_offsets(all_results: List[Dict]) -> Dict[str, Any]:
    """
    For every byte offset in the player block, check if any hero ID mapping
    matches consistently across all players.

    Tests:
    1. Single byte == asset_id
    2. Single byte == seq_id
    3. 2-byte LE uint16 == asset_id
    4. 2-byte LE uint16 == seq_id
    5. 4-byte LE uint32 == asset_id
    6. 4-byte LE uint32 == seq_id
    """
    # Track hits per offset per test type
    # offset -> test_name -> list of (player, matched)
    offset_hits = defaultdict(lambda: defaultdict(list))

    for r in all_results:
        block = r["block_bytes"]
        asset_id = r["asset_id"]
        seq_id = r["seq_id"]
        player = r["player_name"]
        hero = r["hero_name"]

        for off in range(min(len(block), SCAN_RANGE)):
            # Test 1: single byte == asset_id
            if asset_id is not None and asset_id < 256:
                matched = block[off] == asset_id
                offset_hits[off]["byte_asset"].append((player, hero, matched))

            # Test 2: single byte == seq_id
            if seq_id is not None and seq_id < 256:
                matched = block[off] == seq_id
                offset_hits[off]["byte_seq"].append((player, hero, matched))

            # Test 3: 2-byte LE == asset_id
            if off + 2 <= len(block) and asset_id is not None:
                val = int.from_bytes(block[off:off+2], 'little')
                matched = val == asset_id
                offset_hits[off]["u16le_asset"].append((player, hero, matched))

            # Test 4: 2-byte LE == seq_id
            if off + 2 <= len(block) and seq_id is not None:
                val = int.from_bytes(block[off:off+2], 'little')
                matched = val == seq_id
                offset_hits[off]["u16le_seq"].append((player, hero, matched))

            # Test 5: 4-byte LE == asset_id
            if off + 4 <= len(block) and asset_id is not None:
                val = int.from_bytes(block[off:off+4], 'little')
                matched = val == asset_id
                offset_hits[off]["u32le_asset"].append((player, hero, matched))

            # Test 6: 4-byte LE == seq_id
            if off + 4 <= len(block) and seq_id is not None:
                val = int.from_bytes(block[off:off+4], 'little')
                matched = val == seq_id
                offset_hits[off]["u32le_seq"].append((player, hero, matched))

    # Compute accuracy per offset per test
    best_results = []
    for off in sorted(offset_hits.keys()):
        for test_name, entries in offset_hits[off].items():
            total = len(entries)
            hits = sum(1 for _, _, m in entries if m)
            accuracy = hits / total if total > 0 else 0

            if hits >= 2:  # At least 2 matches to be interesting
                best_results.append({
                    "offset": off,
                    "offset_hex": f"0x{off:03X}",
                    "test": test_name,
                    "hits": hits,
                    "total": total,
                    "accuracy": round(accuracy, 4),
                    "examples": [
                        {"player": p, "hero": h, "matched": m}
                        for p, h, m in entries[:5]
                    ],
                })

    # Sort by accuracy then hits
    best_results.sort(key=lambda x: (-x["accuracy"], -x["hits"]))
    return best_results


def dump_block_hex(all_results: List[Dict], offsets_of_interest: List[int]):
    """Dump hex values at specific offsets for all players."""
    print("\n" + "=" * 80)
    print("PLAYER BLOCK HEX DUMP AT KEY OFFSETS")
    print("=" * 80)

    # Always include known offsets
    key_offsets = sorted(set([0xA5, 0xA6, 0xD5] + offsets_of_interest))

    header = f"{'Player':<20} {'Hero':<15} {'AssetID':>7} {'SeqID':>5}"
    for off in key_offsets:
        header += f" | 0x{off:03X}"
    print(header)
    print("-" * len(header))

    for r in all_results:
        block = r["block_bytes"]
        line = f"{r['player_name'][:20]:<20} {r['hero_name']:<15} {r['asset_id'] or '-':>7} {r['seq_id'] or '-':>5}"
        for off in key_offsets:
            if off < len(block):
                b = block[off]
                # Also show 2-byte LE value
                if off + 2 <= len(block):
                    val16 = int.from_bytes(block[off:off+2], 'little')
                    line += f" | {b:3d}({val16:5d})"
                else:
                    line += f" | {b:3d}(    -)"
            else:
                line += f" |   -(    -)"
        print(line)


def main():
    # Load truth data
    truth_path = Path(__file__).parent.parent / "output" / "tournament_truth.json"
    if not truth_path.exists():
        print(f"Truth data not found: {truth_path}")
        return

    with open(truth_path, 'r', encoding='utf-8') as f:
        truth = json.load(f)

    all_results = []

    for match in truth.get("matches", []):
        replay_file = match.get("replay_file", "")
        replay_name = match.get("replay_name", "")
        players = match.get("players", {})

        print(f"\n--- Analyzing: {replay_name[:60]}...")
        results = analyze_replay(replay_file, players)
        print(f"    Found {len(results)} players with truth data")
        all_results.extend(results)

    if not all_results:
        print("\nNo results found. Check replay file paths.")
        return

    print(f"\n{'=' * 80}")
    print(f"TOTAL PLAYERS ANALYZED: {len(all_results)}")
    print(f"{'=' * 80}")

    # Search for hero ID at every offset
    print("\nSearching for hero ID patterns at all offsets...")
    best = search_hero_id_at_offsets(all_results)

    # Show top results
    print(f"\n{'=' * 80}")
    print("TOP CANDIDATE OFFSETS (accuracy >= 10% or hits >= 5)")
    print(f"{'=' * 80}")
    print(f"{'Offset':<10} {'Test':<15} {'Hits':>5} {'Total':>6} {'Accuracy':>10}")
    print("-" * 50)

    shown = 0
    top_offsets = []
    for item in best:
        if item["accuracy"] >= 0.10 or item["hits"] >= 5:
            print(f"{item['offset_hex']:<10} {item['test']:<15} {item['hits']:>5} {item['total']:>6} {item['accuracy']:>10.1%}")
            if shown < 10:
                top_offsets.append(item["offset"])
            shown += 1
            if shown >= 40:
                break

    if not top_offsets:
        # If no good hits, show the best available
        print("\nNo strong hits found. Showing top 20 regardless:")
        for item in best[:20]:
            print(f"{item['offset_hex']:<10} {item['test']:<15} {item['hits']:>5} {item['total']:>6} {item['accuracy']:>10.1%}")
            top_offsets.append(item["offset"])

    # Hex dump at key offsets
    unique_offsets = sorted(set(top_offsets[:8]))
    dump_block_hex(all_results, unique_offsets)

    # Also dump a wider range around the most promising offset
    if best:
        best_off = best[0]["offset"]
        print(f"\n--- Detailed hex dump around best offset 0x{best_off:03X} ---")
        range_offsets = list(range(max(0, best_off - 4), min(SCAN_RANGE, best_off + 8)))
        dump_block_hex(all_results[:10], range_offsets)

    # Save full analysis
    output_path = Path(__file__).parent.parent / "output" / "hero_id_hunt_results.json"

    # Prepare serializable results
    serial_results = []
    for r in all_results:
        sr = dict(r)
        del sr["block_bytes"]  # Not JSON serializable
        # Add hex dump of first 0x120 bytes
        block = r["block_bytes"]
        sr["block_hex_0x00_0x40"] = block[0x00:0x40].hex()
        sr["block_hex_0x40_0x80"] = block[0x40:0x80].hex()
        sr["block_hex_0x80_0xC0"] = block[0x80:0xC0].hex()
        sr["block_hex_0xC0_0x100"] = block[0xC0:0x100].hex()
        sr["block_hex_0x100_0x120"] = block[0x100:0x120].hex()
        serial_results.append(sr)

    output = {
        "total_players": len(all_results),
        "top_offset_candidates": best[:50],
        "player_blocks": serial_results,
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nFull results saved to: {output_path}")


if __name__ == "__main__":
    main()
