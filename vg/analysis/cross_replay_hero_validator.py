#!/usr/bin/env python3
"""
Cross-Replay Hero Validation Script
Validates binary hero ID mappings by analyzing player blocks across all replay files.

Purpose:
- Scan all replay folders for .vgr files
- Extract hero IDs and hashes from player blocks
- Build statistics on hero ID frequency and hash consistency
- Identify unmapped hero IDs
- Validate mapping consistency across replays

Player Block Structure:
- Marker: DA 03 EE (or E0 03 EE)
- Hero ID: uint16 LE at offset +0xA9 from marker
- Hero Hash: 4 bytes at offset +0xAB from marker
"""

import os
import json
import struct
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
from collections import defaultdict
from datetime import datetime

# Import existing mappings
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.vgr_mapping import BINARY_HERO_ID_MAP

# Constants
REPLAY_BASE_PATH = "D:/Desktop/My Folder/Game/VG/vg replay/"
OUTPUT_PATH = "D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/cross_replay_validation.json"
PLAYER_BLOCK_MARKERS = [
    bytes([0xDA, 0x03, 0xEE]),  # Primary marker
    bytes([0xE0, 0x03, 0xEE]),  # Alternative marker
]
HERO_ID_OFFSET = 0xA9
HERO_HASH_OFFSET = 0xAB


class PlayerBlockData:
    """Container for player block extracted data"""
    def __init__(self, player_name: str, hero_id: int, hero_hash: str,
                 replay_file: str, offset: int):
        self.player_name = player_name
        self.hero_id = hero_id
        self.hero_hash = hero_hash
        self.replay_file = replay_file
        self.offset = offset


class HeroStatistics:
    """Statistics for a specific binary hero ID"""
    def __init__(self, hero_id: int):
        self.hero_id = hero_id
        self.count = 0
        self.hashes: Set[str] = set()
        self.player_names: Set[str] = set()
        self.replay_files: Set[str] = set()
        self.mapped_name = BINARY_HERO_ID_MAP.get(hero_id, None)
        self.is_confirmed = self._is_confirmed(hero_id)

    def _is_confirmed(self, hero_id: int) -> bool:
        """Check if hero ID is in confirmed set (first 37 entries)"""
        confirmed_ids = [
            0x0101, 0x0301, 0x0501, 0x0901, 0x0A01, 0x0B01, 0x0D01, 0x1101,
            0x1201, 0x1401, 0x1701, 0x1801, 0x1901, 0x1D01, 0x8B01, 0x8C01,
            0x8D01, 0x8F01, 0x9103, 0x9301, 0x9303, 0x9403, 0x9601, 0x9901,
            0x9A03, 0x9C01, 0xA201, 0xA401, 0xB001, 0xB401, 0xB701, 0xB801,
            0xBE01, 0xF200, 0xF300, 0xFD00, 0xFF00,
        ]
        return hero_id in confirmed_ids

    def add_occurrence(self, player_name: str, hero_hash: str, replay_file: str):
        """Record a new occurrence of this hero ID"""
        self.count += 1
        self.hashes.add(hero_hash)
        self.player_names.add(player_name)
        self.replay_files.add(replay_file)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON export"""
        return {
            "hero_id_hex": f"0x{self.hero_id:04X}",
            "hero_id_decimal": self.hero_id,
            "mapped_name": self.mapped_name,
            "is_confirmed": self.is_confirmed,
            "count": self.count,
            "unique_hashes": list(self.hashes),
            "hash_count": len(self.hashes),
            "hash_consistency": "CONSISTENT" if len(self.hashes) == 1 else "INCONSISTENT",
            "sample_players": list(self.player_names)[:10],  # Limit to 10 samples
            "player_count": len(self.player_names),
            "replay_count": len(self.replay_files),
        }


def find_vgr_files(base_path: str) -> List[Path]:
    """
    Find all .vgr files in replay directory structure.

    Expected structure:
    - base_path/21.11.04/cache/*.vgr
    - base_path/22.05.16/cache/*.vgr
    - base_path/Tournament_Replays/*/*.vgr (may vary)
    """
    vgr_files = []
    base = Path(base_path)

    if not base.exists():
        print(f"[ERROR] Replay base path not found: {base_path}")
        return []

    # Search all subdirectories recursively for .vgr files
    for vgr_file in base.rglob("*.vgr"):
        vgr_files.append(vgr_file)

    return sorted(vgr_files)


def extract_player_name(data: bytes, marker_pos: int) -> str:
    """
    Extract player name from player block.
    Player name appears after marker + 3 bytes, null-terminated.
    """
    try:
        # Start reading after marker (3 bytes) + immediate byte
        name_start = marker_pos + 4
        name_bytes = bytearray()

        # Read until null terminator or max length
        max_length = 50
        for i in range(max_length):
            byte = data[name_start + i]
            if byte == 0:
                break
            # Only printable ASCII
            if 32 <= byte <= 126:
                name_bytes.append(byte)
            else:
                break

        name = name_bytes.decode('ascii', errors='ignore').strip()
        return name if name else "Unknown"
    except (IndexError, UnicodeDecodeError):
        return "Unknown"


def parse_player_blocks(vgr_file: Path) -> List[PlayerBlockData]:
    """
    Parse all player blocks from a .vgr file.

    Returns list of PlayerBlockData objects.
    """
    player_data = []

    try:
        with open(vgr_file, 'rb') as f:
            data = f.read()

        # Search for all player block markers
        for marker in PLAYER_BLOCK_MARKERS:
            pos = 0
            while True:
                pos = data.find(marker, pos)
                if pos == -1:
                    break

                # Check if we have enough bytes for hero ID and hash
                if pos + HERO_HASH_OFFSET + 4 > len(data):
                    pos += 1
                    continue

                # Extract player name
                player_name = extract_player_name(data, pos)

                # Extract hero ID (uint16 LE at +0xA9)
                hero_id_offset = pos + HERO_ID_OFFSET
                if hero_id_offset + 2 > len(data):
                    pos += 1
                    continue

                hero_id = struct.unpack('<H', data[hero_id_offset:hero_id_offset + 2])[0]

                # Extract hero hash (4 bytes at +0xAB)
                hash_offset = pos + HERO_HASH_OFFSET
                if hash_offset + 4 > len(data):
                    pos += 1
                    continue

                hero_hash_bytes = data[hash_offset:hash_offset + 4]
                hero_hash = hero_hash_bytes.hex().upper()

                # Skip obviously invalid hero IDs (0x0000, 0xFFFF)
                if hero_id == 0 or hero_id == 0xFFFF:
                    pos += 1
                    continue

                player_data.append(PlayerBlockData(
                    player_name=player_name,
                    hero_id=hero_id,
                    hero_hash=hero_hash,
                    replay_file=str(vgr_file.relative_to(REPLAY_BASE_PATH)),
                    offset=pos
                ))

                pos += 1

    except Exception as e:
        print(f"[WARNING] Error parsing {vgr_file.name}: {e}")

    return player_data


def build_statistics(all_player_data: List[PlayerBlockData]) -> Dict[int, HeroStatistics]:
    """Build statistics from all player block data"""
    stats: Dict[int, HeroStatistics] = {}

    for player in all_player_data:
        if player.hero_id not in stats:
            stats[player.hero_id] = HeroStatistics(player.hero_id)

        stats[player.hero_id].add_occurrence(
            player.player_name,
            player.hero_hash,
            player.replay_file
        )

    return stats


def analyze_consistency(stats: Dict[int, HeroStatistics]) -> dict:
    """Analyze hash consistency across all hero IDs"""
    total_heroes = len(stats)
    consistent_heroes = sum(1 for s in stats.values() if len(s.hashes) == 1)
    inconsistent_heroes = total_heroes - consistent_heroes

    mapped_heroes = sum(1 for s in stats.values() if s.mapped_name is not None)
    unmapped_heroes = total_heroes - mapped_heroes

    confirmed_heroes = sum(1 for s in stats.values() if s.is_confirmed)
    inferred_heroes = sum(1 for s in stats.values() if s.mapped_name and not s.is_confirmed)

    return {
        "total_unique_hero_ids": total_heroes,
        "consistent_hashes": consistent_heroes,
        "inconsistent_hashes": inconsistent_heroes,
        "mapped_heroes": mapped_heroes,
        "unmapped_heroes": unmapped_heroes,
        "confirmed_mappings": confirmed_heroes,
        "inferred_mappings": inferred_heroes,
        "consistency_rate": f"{(consistent_heroes / total_heroes * 100):.1f}%",
    }


def identify_unmapped_heroes(stats: Dict[int, HeroStatistics]) -> List[dict]:
    """Identify hero IDs not in BINARY_HERO_ID_MAP"""
    unmapped = []

    for hero_id, stat in sorted(stats.items()):
        if stat.mapped_name is None:
            unmapped.append({
                "hero_id_hex": f"0x{hero_id:04X}",
                "hero_id_decimal": hero_id,
                "occurrences": stat.count,
                "unique_hash": list(stat.hashes)[0] if len(stat.hashes) == 1 else None,
                "hash_count": len(stat.hashes),
                "sample_players": list(stat.player_names)[:5],
                "replay_count": len(stat.replay_files),
            })

    return unmapped


def main():
    """Main execution"""
    print("[STAGE:begin:data_collection]")
    print(f"[OBJECTIVE] Validate binary hero ID mappings across all replay files")

    # Find all .vgr files
    print(f"\nScanning replay directory: {REPLAY_BASE_PATH}")
    vgr_files = find_vgr_files(REPLAY_BASE_PATH)
    print(f"[DATA] Found {len(vgr_files)} .vgr files")

    if not vgr_files:
        print("[LIMITATION] No replay files found - check path")
        return

    # Parse all player blocks
    print("\nParsing player blocks from all replays...")
    all_player_data = []

    for i, vgr_file in enumerate(vgr_files, 1):
        if i % 50 == 0:
            print(f"  Progress: {i}/{len(vgr_files)} files...")

        player_data = parse_player_blocks(vgr_file)
        all_player_data.extend(player_data)

    print(f"[DATA] Extracted {len(all_player_data)} player blocks from {len(vgr_files)} replays")
    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:data_collection]")

    # Build statistics
    print("\n[STAGE:begin:analysis]")
    print("Building hero ID statistics...")
    stats = build_statistics(all_player_data)

    # Analyze consistency
    consistency = analyze_consistency(stats)
    print(f"\n[FINDING] Hero ID Analysis Summary:")
    print(f"[STAT:total_hero_ids] {consistency['total_unique_hero_ids']}")
    print(f"[STAT:consistent_hashes] {consistency['consistent_hashes']}")
    print(f"[STAT:inconsistent_hashes] {consistency['inconsistent_hashes']}")
    print(f"[STAT:consistency_rate] {consistency['consistency_rate']}")
    print(f"[STAT:mapped_heroes] {consistency['mapped_heroes']}")
    print(f"[STAT:unmapped_heroes] {consistency['unmapped_heroes']}")
    print(f"[STAT:confirmed_mappings] {consistency['confirmed_mappings']}")
    print(f"[STAT:inferred_mappings] {consistency['inferred_mappings']}")

    # Identify unmapped heroes
    unmapped = identify_unmapped_heroes(stats)
    if unmapped:
        print(f"\n[FINDING] Found {len(unmapped)} unmapped hero IDs:")
        for hero in unmapped[:10]:  # Show first 10
            print(f"  {hero['hero_id_hex']}: {hero['occurrences']} occurrences, "
                  f"hash={'consistent' if hero['unique_hash'] else 'INCONSISTENT'}")
    else:
        print("\n[FINDING] All discovered hero IDs are mapped!")

    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:analysis]")

    # Generate output
    print("\n[STAGE:begin:output_generation]")
    output_data = {
        "generated_at": datetime.now().isoformat(),
        "replay_base_path": REPLAY_BASE_PATH,
        "total_replays_scanned": len(vgr_files),
        "total_player_blocks": len(all_player_data),
        "consistency_analysis": consistency,
        "hero_statistics": {
            f"0x{hero_id:04X}": stat.to_dict()
            for hero_id, stat in sorted(stats.items())
        },
        "unmapped_heroes": unmapped,
        "inconsistent_heroes": [
            {
                "hero_id_hex": f"0x{hero_id:04X}",
                "mapped_name": stat.mapped_name,
                "hashes": list(stat.hashes),
                "count": stat.count,
            }
            for hero_id, stat in sorted(stats.items())
            if len(stat.hashes) > 1
        ],
        "top_10_most_frequent": [
            {
                "hero_id_hex": f"0x{hero_id:04X}",
                "mapped_name": stat.mapped_name,
                "count": stat.count,
                "consistency": "CONSISTENT" if len(stat.hashes) == 1 else "INCONSISTENT",
            }
            for hero_id, stat in sorted(stats.items(), key=lambda x: x[1].count, reverse=True)[:10]
        ],
    }

    # Save output
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(f"[FINDING] Validation report saved to: {OUTPUT_PATH}")
    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:output_generation]")

    print("\n" + "="*60)
    print("VALIDATION SUMMARY")
    print("="*60)
    print(f"Total replays analyzed: {len(vgr_files)}")
    print(f"Total player blocks: {len(all_player_data)}")
    print(f"Unique hero IDs: {consistency['total_unique_hero_ids']}")
    print(f"Hash consistency: {consistency['consistency_rate']}")
    print(f"Mapped heroes: {consistency['mapped_heroes']}/{consistency['total_unique_hero_ids']}")
    print(f"Unmapped heroes: {len(unmapped)}")
    print("="*60)


if __name__ == "__main__":
    main()
