#!/usr/bin/env python3
"""
Expand Hero ID Mapping - Tournament Replay Cross-Reference
Scans all tournament replays to extract binary hero IDs and cross-reference with truth data.
Identifies unmapped heroes to expand BINARY_HERO_ID_MAP coverage from 37/56 to maximum.
"""

import json
import struct
import io
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Set

# Fix Windows console encoding
import sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Import existing mapping
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.vgr_mapping import BINARY_HERO_ID_MAP, HERO_NAME_NORMALIZE

# Player block markers
PLAYER_BLOCK_MARKERS = [
    bytes.fromhex("DA 03 EE"),
    bytes.fromhex("E0 03 EE")
]

# Offsets from player block marker
ENTITY_ID_OFFSET = 0xA5  # uint16 LE
HERO_ID_OFFSET = 0xA9    # uint16 LE
TEAM_OFFSET = 0xD5       # byte (1=left, 2=right)

def find_player_blocks(data: bytes) -> List[int]:
    """Find all player block markers in replay data."""
    positions = []
    for marker in PLAYER_BLOCK_MARKERS:
        offset = 0
        while True:
            pos = data.find(marker, offset)
            if pos == -1:
                break
            positions.append(pos)
            offset = pos + 1
    return sorted(positions)

def extract_player_name(data: bytes, block_pos: int) -> str:
    """Extract player name from player block."""
    # Name starts after marker (3 bytes) and is null-terminated
    name_start = block_pos + 3
    name_end = data.find(b'\x00', name_start)
    if name_end == -1:
        return ""
    try:
        return data[name_start:name_end].decode('utf-8', errors='ignore')
    except:
        return ""

def extract_hero_id(data: bytes, block_pos: int) -> int:
    """Extract hero ID (uint16 LE) from player block."""
    offset = block_pos + HERO_ID_OFFSET
    if offset + 2 > len(data):
        return 0
    return struct.unpack('<H', data[offset:offset+2])[0]

def extract_entity_id(data: bytes, block_pos: int) -> int:
    """Extract entity ID (uint16 LE) from player block."""
    offset = block_pos + ENTITY_ID_OFFSET
    if offset + 2 > len(data):
        return 0
    return struct.unpack('<H', data[offset:offset+2])[0]

def extract_team(data: bytes, block_pos: int) -> int:
    """Extract team (1=left, 2=right) from player block."""
    offset = block_pos + TEAM_OFFSET
    if offset + 1 > len(data):
        return 0
    return data[offset]

def parse_replay_players(replay_file: str) -> List[Dict]:
    """Parse all players from a replay file."""
    try:
        with open(replay_file, 'rb') as f:
            data = f.read()

        # Find player blocks in first 50KB (frame 0 region)
        search_region = data[:50000]
        block_positions = find_player_blocks(search_region)

        players = []
        for pos in block_positions:
            player_name = extract_player_name(data, pos)
            if not player_name or len(player_name) < 2:
                continue

            hero_id = extract_hero_id(data, pos)
            entity_id = extract_entity_id(data, pos)
            team = extract_team(data, pos)

            players.append({
                'name': player_name,
                'hero_id': hero_id,
                'entity_id': entity_id,
                'team': 'left' if team == 1 else 'right' if team == 2 else 'unknown',
                'block_pos': pos
            })

        return players
    except Exception as e:
        print(f"Error parsing {replay_file}: {e}")
        return []

def normalize_hero_name(name: str) -> str:
    """Normalize hero name (handle OCR typos)."""
    if not name:
        return name
    # Handle common OCR typos
    normalized = HERO_NAME_NORMALIZE.get(name.lower(), name)
    # Capitalize first letter
    return normalized[0].upper() + normalized[1:] if normalized else name

def main():
    print("[STAGE:begin:data_loading]")

    # Load tournament truth data
    truth_file = Path("D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/tournament_truth.json")
    with open(truth_file, 'r', encoding='utf-8') as f:
        truth_data = json.load(f)

    print(f"[DATA] Loaded {len(truth_data['matches'])} tournament matches")
    print("[STAGE:status:success]")
    print("[STAGE:end:data_loading]")

    print("\n[STAGE:begin:extraction]")

    # Collect all (hero_id, hero_name) pairs
    hero_mappings = defaultdict(set)  # hero_id -> set of hero names
    player_records = []

    for match_idx, match in enumerate(truth_data['matches'], 1):
        replay_file = match['replay_file']
        print(f"\n[{match_idx}/{len(truth_data['matches'])}] Processing: {Path(replay_file).name}")

        # Parse binary replay
        binary_players = parse_replay_players(replay_file)
        print(f"  Found {len(binary_players)} player blocks")

        # Cross-reference with truth data
        truth_players = match['players']

        for bin_player in binary_players:
            player_name = bin_player['name']
            hero_id = bin_player['hero_id']

            # Find matching truth player
            if player_name in truth_players:
                truth_hero = truth_players[player_name]['hero_name']
                truth_hero_normalized = normalize_hero_name(truth_hero)

                hero_mappings[hero_id].add(truth_hero_normalized)

                player_records.append({
                    'match': match['replay_name'],
                    'player': player_name,
                    'hero_id': f"0x{hero_id:04X}",
                    'hero_name': truth_hero_normalized,
                    'team': bin_player['team'],
                    'entity_id': bin_player['entity_id']
                })

                print(f"    {player_name:20s} -> 0x{hero_id:04X} = {truth_hero_normalized}")
            else:
                print(f"    {player_name:20s} -> 0x{hero_id:04X} = ??? (not in truth)")

    print(f"\n[DATA] Extracted {len(player_records)} player records")
    print(f"[DATA] Found {len(hero_mappings)} unique hero IDs")
    print("[STAGE:status:success]")
    print("[STAGE:end:extraction]")

    print("\n[STAGE:begin:validation]")

    # Validate consistency (each hero_id should map to exactly 1 hero name)
    inconsistent = []
    consistent_mappings = {}

    for hero_id, names in hero_mappings.items():
        if len(names) > 1:
            inconsistent.append((hero_id, names))
            print(f"[LIMITATION] 0x{hero_id:04X} maps to multiple heroes: {names}")
        else:
            hero_name = list(names)[0]
            consistent_mappings[hero_id] = hero_name

    if not inconsistent:
        print("[FINDING] All hero IDs map consistently to single hero names (100% consistency)")

    print(f"[STAT:consistent_mappings] {len(consistent_mappings)}")
    print(f"[STAT:inconsistent_mappings] {len(inconsistent)}")
    print("[STAGE:status:success]")
    print("[STAGE:end:validation]")

    print("\n[STAGE:begin:comparison]")

    # Compare with existing BINARY_HERO_ID_MAP
    existing_count = len(BINARY_HERO_ID_MAP)
    new_mappings = {}
    confirmed_mappings = {}
    conflicting_mappings = {}

    for hero_id, hero_name in consistent_mappings.items():
        if hero_id in BINARY_HERO_ID_MAP:
            # Already mapped
            if BINARY_HERO_ID_MAP[hero_id] == hero_name:
                confirmed_mappings[hero_id] = hero_name
            else:
                # Conflict!
                conflicting_mappings[hero_id] = {
                    'existing': BINARY_HERO_ID_MAP[hero_id],
                    'new': hero_name
                }
        else:
            # New mapping
            new_mappings[hero_id] = hero_name

    print(f"\n[FINDING] Mapping Status:")
    print(f"  Existing mappings: {existing_count}")
    print(f"  Confirmed by tournament data: {len(confirmed_mappings)}")
    print(f"  New mappings found: {len(new_mappings)}")
    print(f"  Conflicts detected: {len(conflicting_mappings)}")

    if conflicting_mappings:
        print("\n[LIMITATION] Conflicts detected:")
        for hero_id, conflict in conflicting_mappings.items():
            print(f"  0x{hero_id:04X}: existing='{conflict['existing']}' vs new='{conflict['new']}'")

    if new_mappings:
        print("\n[FINDING] New hero mappings to add to BINARY_HERO_ID_MAP:")
        for hero_id, hero_name in sorted(new_mappings.items()):
            print(f"  0x{hero_id:04X}: \"{hero_name}\",")
    else:
        print("\n[FINDING] No new mappings found - all tournament heroes already in BINARY_HERO_ID_MAP")

    # Calculate coverage
    total_heroes_in_tournament = len(consistent_mappings)
    coverage_before = len([h for h in consistent_mappings if h in BINARY_HERO_ID_MAP])
    coverage_after = coverage_before + len(new_mappings)

    print(f"\n[STAT:tournament_unique_heroes] {total_heroes_in_tournament}")
    print(f"[STAT:coverage_before] {coverage_before}/{total_heroes_in_tournament} ({coverage_before/total_heroes_in_tournament*100:.1f}%)")
    print(f"[STAT:coverage_after] {coverage_after}/{total_heroes_in_tournament} ({coverage_after/total_heroes_in_tournament*100:.1f}%)")
    print(f"[STAT:total_mapped_heroes] {existing_count} -> {existing_count + len(new_mappings)}")

    print("[STAGE:status:success]")
    print("[STAGE:end:comparison]")

    # Save detailed report
    print("\n[STAGE:begin:reporting]")

    output_dir = Path("D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output")

    # Save player records
    player_records_file = output_dir / "hero_mapping_player_records.json"
    with open(player_records_file, 'w', encoding='utf-8') as f:
        json.dump({
            'total_records': len(player_records),
            'unique_heroes': len(consistent_mappings),
            'records': player_records
        }, f, indent=2)
    print(f"[FINDING] Saved player records to {player_records_file}")

    # Save mapping analysis
    mapping_analysis_file = output_dir / "hero_mapping_analysis.json"
    with open(mapping_analysis_file, 'w', encoding='utf-8') as f:
        json.dump({
            'existing_count': existing_count,
            'tournament_unique_heroes': total_heroes_in_tournament,
            'confirmed_mappings': {f"0x{k:04X}": v for k, v in confirmed_mappings.items()},
            'new_mappings': {f"0x{k:04X}": v for k, v in new_mappings.items()},
            'conflicting_mappings': {f"0x{k:04X}": v for k, v in conflicting_mappings.items()},
            'coverage_before_percent': coverage_before/total_heroes_in_tournament*100,
            'coverage_after_percent': coverage_after/total_heroes_in_tournament*100
        }, f, indent=2)
    print(f"[FINDING] Saved mapping analysis to {mapping_analysis_file}")

    # Generate code snippet for vgr_mapping.py
    if new_mappings:
        code_snippet_file = output_dir / "hero_mapping_code_snippet.txt"
        with open(code_snippet_file, 'w', encoding='utf-8') as f:
            f.write("# Add these lines to BINARY_HERO_ID_MAP in vg/core/vgr_mapping.py:\n\n")
            for hero_id, hero_name in sorted(new_mappings.items()):
                f.write(f"    0x{hero_id:04X}: \"{hero_name}\",\n")
        print(f"[FINDING] Saved code snippet to {code_snippet_file}")

    print("[STAGE:status:success]")
    print("[STAGE:end:reporting]")

    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Total unique heroes in tournament: {total_heroes_in_tournament}")
    print(f"Already mapped: {coverage_before}/{total_heroes_in_tournament}")
    print(f"New mappings found: {len(new_mappings)}")
    print(f"Final coverage: {coverage_after}/{total_heroes_in_tournament} ({coverage_after/total_heroes_in_tournament*100:.1f}%)")
    print(f"Total BINARY_HERO_ID_MAP size: {existing_count} -> {existing_count + len(new_mappings)}")

    if new_mappings:
        print("\n✓ Check vg/output/hero_mapping_code_snippet.txt for code to add")
    else:
        print("\n✓ No updates needed - all tournament heroes already mapped!")

if __name__ == '__main__':
    main()
