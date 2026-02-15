#!/usr/bin/env python3
"""
Item-Player Mapping Research
Investigates WHERE in VGR binary files item ownership is encoded.

Research Strategy:
1. Load player blocks with entity IDs
2. Find all item occurrences in frame 0 and late-game frames
3. Search for patterns linking items to player entity IDs
4. Look for item records near player blocks
5. Check if item markers contain entity ID references

Usage:
    python -m vg.analysis.item_player_research
"""

import sys
import struct
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Set, Optional

# Add to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from vg.core.vgr_mapping import ITEM_ID_MAP, BINARY_HERO_ID_MAP

# Player block markers
PLAYER_BLOCK_MARKER_1 = b'\xDA\x03\xEE'
PLAYER_BLOCK_MARKER_2 = b'\xE0\x03\xEE'

# Item pattern markers
MARKER_FF = b'\xFF\xFF\xFF\xFF'
MARKER_00 = b'\x00\x00\x00\x00'
MARKER_05 = b'\x00\x00\x00\x05'

# Known event patterns
KILL_PATTERN = b'\x18\x04\x1C'
DEATH_PATTERN = b'\x08\x04\x31'
CREDIT_PATTERN = b'\x10\x04\x1D'

# Item ID ranges
ITEM_RANGES = {
    'weapon': (101, 129),
    'crystal': (201, 229),
    'defense': (301, 328),
    'utility': (401, 423),
}


class PlayerBlock:
    """Represents a player block in the binary data"""
    def __init__(self, offset: int, marker: bytes, data: bytes):
        self.offset = offset
        self.marker = marker

        # Extract entity ID at +0xA5 (uint16 LE)
        eid_offset = offset + 0xA5
        if eid_offset + 2 <= len(data):
            self.entity_id = struct.unpack('<H', data[eid_offset:eid_offset+2])[0]
        else:
            self.entity_id = None

        # Extract hero ID at +0xA9 (uint16 LE)
        hero_offset = offset + 0xA9
        if hero_offset + 2 <= len(data):
            self.hero_id = struct.unpack('<H', data[hero_offset:hero_offset+2])[0]
            self.hero_name = BINARY_HERO_ID_MAP.get(self.hero_id, f"Unknown_{self.hero_id:04X}")
        else:
            self.hero_id = None
            self.hero_name = "Unknown"

        # Extract team at +0xD5 (byte: 1=left, 2=right)
        team_offset = offset + 0xD5
        if team_offset + 1 <= len(data):
            team_byte = data[team_offset]
            self.team = "left" if team_byte == 1 else "right" if team_byte == 2 else "unknown"
        else:
            self.team = "unknown"

    def __repr__(self):
        return f"Player(eid={self.entity_id}, hero={self.hero_name}, team={self.team}, offset=0x{self.offset:X})"


class ItemOccurrence:
    """Represents an item occurrence in binary data"""
    def __init__(self, item_id: int, offset: int, context: bytes, pattern: str):
        self.item_id = item_id
        self.offset = offset
        self.context = context
        self.pattern = pattern
        self.item_info = ITEM_ID_MAP.get(item_id, {})
        self.name = self.item_info.get('name', f'Unknown_{item_id}')
        self.category = self.item_info.get('category', 'Unknown')

    def __repr__(self):
        return f"Item({self.name}, offset=0x{self.offset:X}, pattern={self.pattern})"


class ItemPlayerResearcher:
    """Research tool to find item→player mappings"""

    def __init__(self, replay_dir: Path):
        self.replay_dir = replay_dir
        self.frames = self._load_frames()

    def _load_frames(self) -> List[Path]:
        """Find all .vgr frame files"""
        frames = list(self.replay_dir.glob('*.vgr'))
        return sorted(frames, key=lambda p: int(p.stem.split('.')[-1]))

    def find_player_blocks(self, data: bytes) -> List[PlayerBlock]:
        """Find all player blocks in frame data"""
        blocks = []

        # Search for both marker types
        for marker in [PLAYER_BLOCK_MARKER_1, PLAYER_BLOCK_MARKER_2]:
            offset = 0
            while True:
                pos = data.find(marker, offset)
                if pos == -1:
                    break

                block = PlayerBlock(pos, marker, data)
                if block.entity_id is not None:
                    blocks.append(block)

                offset = pos + 1

        return blocks

    def find_items_with_marker(self, data: bytes, marker: bytes,
                               item_range: Tuple[int, int], pattern_name: str) -> List[ItemOccurrence]:
        """Find items using marker pattern (e.g., FF FF FF FF [ID])"""
        items = []
        offset = 0

        while True:
            pos = data.find(marker, offset)
            if pos == -1 or pos + 6 > len(data):
                break

            # Read uint16 LE after marker
            item_id = struct.unpack('<H', data[pos + 4:pos + 6])[0]

            if item_range[0] <= item_id <= item_range[1] and item_id in ITEM_ID_MAP:
                context = data[max(0, pos-8):pos+16]
                items.append(ItemOccurrence(item_id, pos, context, pattern_name))

            offset = pos + 1

        return items

    def find_items_direct(self, data: bytes, item_range: Tuple[int, int]) -> List[ItemOccurrence]:
        """Find items using direct 2-byte LE search"""
        items = []

        for item_id in range(item_range[0], item_range[1] + 1):
            if item_id not in ITEM_ID_MAP:
                continue

            item_bytes = struct.pack('<H', item_id)
            offset = 0

            while True:
                pos = data.find(item_bytes, offset)
                if pos == -1:
                    break

                context = data[max(0, pos-8):pos+16]
                items.append(ItemOccurrence(item_id, pos, context, 'direct_2byte'))

                offset = pos + 1

        return items

    def search_entity_id_near_items(self, data: bytes, items: List[ItemOccurrence],
                                    players: List[PlayerBlock], search_radius: int = 64) -> Dict:
        """Search for player entity IDs near item occurrences"""
        findings = defaultdict(list)

        for item in items:
            start = max(0, item.offset - search_radius)
            end = min(len(data), item.offset + search_radius)
            region = data[start:end]

            # Search for each player's entity ID (both LE and BE)
            for player in players:
                eid_le = struct.pack('<H', player.entity_id)
                eid_be = struct.pack('>H', player.entity_id)

                # Search in LE
                pos_le = region.find(eid_le)
                if pos_le != -1:
                    abs_pos = start + pos_le
                    rel_pos = abs_pos - item.offset
                    findings['entity_id_near_item'].append({
                        'item': item.name,
                        'item_offset': item.offset,
                        'player': player.hero_name,
                        'entity_id': player.entity_id,
                        'entity_offset': abs_pos,
                        'relative_pos': rel_pos,
                        'endianness': 'LE',
                        'pattern': item.pattern
                    })

                # Search in BE
                pos_be = region.find(eid_be)
                if pos_be != -1:
                    abs_pos = start + pos_be
                    rel_pos = abs_pos - item.offset
                    findings['entity_id_near_item'].append({
                        'item': item.name,
                        'item_offset': item.offset,
                        'player': player.hero_name,
                        'entity_id': player.entity_id,
                        'entity_offset': abs_pos,
                        'relative_pos': rel_pos,
                        'endianness': 'BE',
                        'pattern': item.pattern
                    })

        return findings

    def search_items_near_player_blocks(self, data: bytes, players: List[PlayerBlock],
                                       all_items: List[ItemOccurrence], search_radius: int = 512) -> Dict:
        """Search for items near player blocks"""
        findings = defaultdict(list)

        for player in players:
            player_start = player.offset
            player_end = player.offset + 0x200  # Typical player block size

            for item in all_items:
                # Check if item is within search radius of player block
                if player_start - search_radius <= item.offset <= player_end + search_radius:
                    rel_pos = item.offset - player_start
                    findings['items_near_player'].append({
                        'player': player.hero_name,
                        'entity_id': player.entity_id,
                        'team': player.team,
                        'player_offset': player.offset,
                        'item': item.name,
                        'item_id': item.item_id,
                        'item_offset': item.offset,
                        'relative_pos': rel_pos,
                        'pattern': item.pattern,
                        'category': item.category
                    })

        return findings

    def analyze_item_record_structure(self, data: bytes, items: List[ItemOccurrence]) -> Dict:
        """Analyze the structure around item occurrences"""
        patterns = defaultdict(list)

        for item in items:
            # Get context around item (32 bytes before, 32 after)
            start = max(0, item.offset - 32)
            end = min(len(data), item.offset + 32)
            context = data[start:end]

            # Look for event-like structures (similar to kill/death records)
            # Event format: [EntityID 2B LE][00 00][ActionCode 1B][Payload ~32B]

            # Check if there's a potential entity ID 4 bytes before
            if item.offset >= 4:
                potential_eid_pos = item.offset - 4
                if data[potential_eid_pos+2:potential_eid_pos+4] == b'\x00\x00':
                    potential_eid = struct.unpack('<H', data[potential_eid_pos:potential_eid_pos+2])[0]
                    if 50000 <= potential_eid <= 60000:  # Player entity ID range
                        patterns['potential_item_event'].append({
                            'item': item.name,
                            'item_offset': item.offset,
                            'potential_owner_eid': potential_eid,
                            'context_hex': context.hex()
                        })

            # Store context patterns for analysis
            patterns['context_samples'].append({
                'item': item.name,
                'offset': item.offset,
                'before': context[:32].hex(),
                'after': context[32:].hex()
            })

        return patterns

    def run_analysis(self):
        """Run comprehensive item→player mapping analysis"""
        print("[OBJECTIVE] Discover item→player ownership mapping in VGR binary files\n")

        if not self.frames:
            print("[LIMITATION] No replay frames found")
            return

        print(f"[DATA] Analyzing replay: {self.replay_dir.name}")
        print(f"[DATA] Total frames: {len(self.frames)}\n")

        # Analyze frame 0 (initial state) and last frame (end game)
        frames_to_analyze = [0, len(self.frames) - 1, len(self.frames) // 2]

        for frame_idx in frames_to_analyze:
            if frame_idx >= len(self.frames):
                continue

            frame_path = self.frames[frame_idx]
            data = frame_path.read_bytes()

            print(f"\n{'='*80}")
            print(f"FRAME {frame_idx} ANALYSIS (size: {len(data):,} bytes)")
            print(f"{'='*80}\n")

            # 1. Find player blocks
            players = self.find_player_blocks(data)
            print(f"[DATA] Found {len(players)} player blocks:")
            for p in players:
                print(f"  {p}")
            print()

            # 2. Find all items
            all_items = []

            # Weapon items
            all_items.extend(self.find_items_with_marker(data, MARKER_FF, ITEM_RANGES['weapon'], 'ff_marker'))

            # Crystal items
            all_items.extend(self.find_items_with_marker(data, MARKER_05, ITEM_RANGES['crystal'], '05_marker'))

            # Defense items
            all_items.extend(self.find_items_with_marker(data, MARKER_FF, ITEM_RANGES['defense'], 'ff_marker'))
            all_items.extend(self.find_items_with_marker(data, MARKER_00, ITEM_RANGES['defense'], '00_marker'))

            # Direct search for all categories
            for category, item_range in ITEM_RANGES.items():
                all_items.extend(self.find_items_direct(data, item_range))

            # Deduplicate items (same item_id at same offset)
            unique_items = []
            seen = set()
            for item in all_items:
                key = (item.item_id, item.offset)
                if key not in seen:
                    unique_items.append(item)
                    seen.add(key)

            print(f"[DATA] Found {len(unique_items)} unique item occurrences")

            # Group by category
            by_category = defaultdict(list)
            for item in unique_items:
                by_category[item.category].append(item)

            for cat in sorted(by_category.keys()):
                items = by_category[cat]
                unique_ids = len(set(i.item_id for i in items))
                print(f"  {cat}: {unique_ids} unique items, {len(items)} total occurrences")
            print()

            # 3. Search for entity IDs near items
            print("[FINDING] Searching for player entity IDs near item occurrences...")
            eid_findings = self.search_entity_id_near_items(data, unique_items, players, search_radius=64)

            if eid_findings['entity_id_near_item']:
                print(f"[FINDING] Found {len(eid_findings['entity_id_near_item'])} entity ID occurrences near items")

                # Count by relative position
                rel_pos_counter = defaultdict(int)
                for finding in eid_findings['entity_id_near_item']:
                    rel_pos_counter[finding['relative_pos']] += 1

                print("\n[STAT:entity_id_relative_positions] Distribution:")
                for rel_pos in sorted(rel_pos_counter.keys())[:10]:
                    count = rel_pos_counter[rel_pos]
                    print(f"  Offset {rel_pos:+4d}: {count} occurrences")

                # Show sample matches
                print("\n[FINDING] Sample entity ID matches near items:")
                for finding in eid_findings['entity_id_near_item'][:10]:
                    print(f"  {finding['item']} @ 0x{finding['item_offset']:X} -> "
                          f"{finding['player']} (EID {finding['entity_id']}) at offset {finding['relative_pos']:+d} ({finding['endianness']})")
            else:
                print("[LIMITATION] No entity IDs found near items within 64-byte radius")
            print()

            # 4. Search for items near player blocks
            print("[FINDING] Searching for items near player blocks...")
            player_findings = self.search_items_near_player_blocks(data, players, unique_items, search_radius=512)

            if player_findings['items_near_player']:
                print(f"[FINDING] Found {len(player_findings['items_near_player'])} items near player blocks")

                # Group by player
                by_player = defaultdict(list)
                for finding in player_findings['items_near_player']:
                    by_player[finding['player']].append(finding)

                for player_name in sorted(by_player.keys()):
                    findings = by_player[player_name]
                    items = [f['item'] for f in findings]
                    print(f"\n  {player_name}:")
                    print(f"    Items found: {', '.join(set(items))}")
                    print(f"    Total occurrences: {len(findings)}")

                    # Show relative positions
                    rel_positions = [f['relative_pos'] for f in findings]
                    print(f"    Relative positions: {sorted(set(rel_positions))[:5]}")
            else:
                print("[LIMITATION] No items found within 512-byte radius of player blocks")
            print()

            # 5. Analyze item record structure
            print("[FINDING] Analyzing item record structures...")
            structure_findings = self.analyze_item_record_structure(data, unique_items[:50])  # Sample first 50

            if structure_findings['potential_item_event']:
                print(f"[FINDING] Found {len(structure_findings['potential_item_event'])} potential item events with entity IDs")
                print("\n[FINDING] Sample potential item events:")
                for finding in structure_findings['potential_item_event'][:5]:
                    print(f"  Item: {finding['item']}")
                    print(f"  Offset: 0x{finding['item_offset']:X}")
                    print(f"  Potential owner EID: {finding['potential_owner_eid']}")
                    print(f"  Context: {finding['context_hex'][:64]}...")
                    print()
            else:
                print("[LIMITATION] No event-like structures found near items")


def main():
    """Main entry point"""
    # Use first tournament replay as test case
    replay_dir = Path(r"D:\Desktop\My Folder\Game\VG\vg replay\Tournament_Replays\SFC vs Team Stooopid (Semi)\1")

    if not replay_dir.exists():
        print(f"[LIMITATION] Replay directory not found: {replay_dir}")
        print("Please update the path in the script")
        return 1

    researcher = ItemPlayerResearcher(replay_dir)
    researcher.run_analysis()

    print("\n" + "="*80)
    print("ANALYSIS COMPLETE")
    print("="*80)
    print("\n[LIMITATION] Research is exploratory - no ground truth for item ownership")
    print("[LIMITATION] Further validation requires external data sources or manual verification")

    return 0


if __name__ == '__main__':
    sys.exit(main())
