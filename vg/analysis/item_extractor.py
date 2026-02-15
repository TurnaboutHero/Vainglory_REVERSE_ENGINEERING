#!/usr/bin/env python3
"""
Item Extractor - Unified Item Detection System
Combines all discovered patterns for maximum item detection across all categories.

Patterns discovered:
- Weapon (101-129): FF FF FF FF [ID uint16 LE] + direct 2-byte LE (86-100% detection)
- Crystal T3 (201+): 00 00 00 05 [ID uint16 LE] (HIGH confidence) + direct 2-byte LE
- Defense: FF FF FF FF [ID] + 00 00 00 00 [ID] + direct 2-byte LE
- Utility: Limited markers, direct 2-byte LE primary method
- Universal: Direct 2-byte LE search works for all categories (86-100% detection)

Usage:
    python -m vg.analysis.item_extractor /path/to/replay/cache/
    python -m vg.analysis.item_extractor /path/to/replay/cache/ --json
    python -m vg.analysis.item_extractor /path/to/replay/cache/ --player-builds
"""

import sys
import struct
import json
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass, asdict

# Add to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from vg.core.vgr_mapping import ITEM_ID_MAP

# Item ID ranges by category
ITEM_RANGES = {
    'weapon': (101, 129),
    'crystal': (201, 229),
    'defense': (301, 328),
    'utility': (401, 423),
}

# Pattern markers
MARKER_FF = b'\xFF\xFF\xFF\xFF'
MARKER_00 = b'\x00\x00\x00\x00'
MARKER_05 = b'\x00\x00\x00\x05'


@dataclass
class ItemDetection:
    """Single item detection instance"""
    item_id: int
    name: str
    category: str
    tier: int
    frame: int
    offset: int
    pattern: str  # Pattern type that found it
    context: str  # Hex context around detection


@dataclass
class ItemExtractionReport:
    """Complete extraction report"""
    replay_dir: str
    total_frames: int
    items_found: Dict[str, List[Dict]]
    total_unique_items: int
    detection_methods: Dict[str, int]
    player_builds: Optional[Dict] = None


class ItemExtractor:
    """Unified item extractor using all discovered patterns"""

    def __init__(self, replay_dir: Path):
        self.replay_dir = replay_dir
        self.frames = self._load_frames()
        self.detections: List[ItemDetection] = []

    def _load_frames(self) -> List[Path]:
        """Find and load all .vgr frame files"""
        frames = list(self.replay_dir.glob('*.vgr'))
        if not frames:
            # Try subdirectories
            for subdir in self.replay_dir.iterdir():
                if subdir.is_dir():
                    frames = list(subdir.glob('*.vgr'))
                    if frames:
                        break

        return sorted(frames, key=lambda p: int(p.stem.split('.')[-1]))

    def _extract_with_marker_pattern(self, data: bytes, frame_num: int,
                                     marker: bytes, pattern_name: str,
                                     item_range: Tuple[int, int]) -> Set[int]:
        """Extract items using marker + ID pattern (FF FF FF FF [ID] or similar)"""
        found_ids = set()
        offset = 0

        while True:
            pos = data.find(marker, offset)
            if pos == -1 or pos + 6 > len(data):
                break

            # Read uint16 LE after marker
            item_id = struct.unpack('<H', data[pos + 4:pos + 6])[0]

            # Check if in valid range
            if item_range[0] <= item_id <= item_range[1]:
                # Verify it's a known item
                if item_id in ITEM_ID_MAP:
                    item_info = ITEM_ID_MAP[item_id]
                    context = data[max(0, pos-4):pos+10].hex()

                    detection = ItemDetection(
                        item_id=item_id,
                        name=item_info['name'],
                        category=item_info['category'],
                        tier=item_info['tier'],
                        frame=frame_num,
                        offset=pos,
                        pattern=pattern_name,
                        context=context
                    )
                    self.detections.append(detection)
                    found_ids.add(item_id)

            offset = pos + 1

        return found_ids

    def _extract_with_direct_search(self, data: bytes, frame_num: int,
                                    item_range: Tuple[int, int],
                                    category: str) -> Set[int]:
        """Extract items using direct 2-byte LE search (universal method)"""
        found_ids = set()

        # Search for each item ID in the range
        for item_id in range(item_range[0], item_range[1] + 1):
            if item_id not in ITEM_ID_MAP:
                continue

            item_bytes = struct.pack('<H', item_id)
            offset = 0

            while True:
                pos = data.find(item_bytes, offset)
                if pos == -1:
                    break

                # Found occurrence
                item_info = ITEM_ID_MAP[item_id]
                context = data[max(0, pos-4):pos+10].hex()

                detection = ItemDetection(
                    item_id=item_id,
                    name=item_info['name'],
                    category=item_info['category'],
                    tier=item_info['tier'],
                    frame=frame_num,
                    offset=pos,
                    pattern='direct_2byte_le',
                    context=context
                )
                self.detections.append(detection)
                found_ids.add(item_id)

                offset = pos + 1

        return found_ids

    def extract_items(self) -> ItemExtractionReport:
        """Extract all items using combined pattern strategies"""

        if not self.frames:
            return ItemExtractionReport(
                replay_dir=str(self.replay_dir),
                total_frames=0,
                items_found={},
                total_unique_items=0,
                detection_methods={}
            )

        all_found_ids: Set[int] = set()
        pattern_stats: Counter = Counter()

        # Process each frame
        for frame_path in self.frames:
            frame_num = int(frame_path.stem.split('.')[-1])
            data = frame_path.read_bytes()

            # Strategy 1: Weapon - FF FF FF FF [ID] pattern
            weapon_ids = self._extract_with_marker_pattern(
                data, frame_num, MARKER_FF, 'ff_marker',
                ITEM_RANGES['weapon']
            )
            all_found_ids.update(weapon_ids)
            pattern_stats['ff_marker'] += len(weapon_ids)

            # Strategy 2: Crystal T3 - 00 00 00 05 [ID] pattern
            crystal_ids = self._extract_with_marker_pattern(
                data, frame_num, MARKER_05, '05_marker',
                ITEM_RANGES['crystal']
            )
            all_found_ids.update(crystal_ids)
            pattern_stats['05_marker'] += len(crystal_ids)

            # Strategy 3: Defense - FF FF FF FF [ID] + 00 00 00 00 [ID]
            defense_ids_ff = self._extract_with_marker_pattern(
                data, frame_num, MARKER_FF, 'ff_marker',
                ITEM_RANGES['defense']
            )
            defense_ids_00 = self._extract_with_marker_pattern(
                data, frame_num, MARKER_00, '00_marker',
                ITEM_RANGES['defense']
            )
            all_found_ids.update(defense_ids_ff | defense_ids_00)
            pattern_stats['ff_marker'] += len(defense_ids_ff)
            pattern_stats['00_marker'] += len(defense_ids_00)

            # Strategy 4: Universal direct search (for all categories)
            # This catches items missed by marker patterns
            for category, id_range in ITEM_RANGES.items():
                direct_ids = self._extract_with_direct_search(
                    data, frame_num, id_range, category
                )
                new_ids = direct_ids - all_found_ids
                all_found_ids.update(new_ids)
                pattern_stats['direct_2byte_le'] += len(new_ids)

        # Organize detections by category
        items_by_category = defaultdict(list)
        seen_items = set()  # Track unique (id, frame) pairs to avoid duplicates

        for detection in self.detections:
            key = (detection.item_id, detection.frame)
            if key not in seen_items:
                items_by_category[detection.category.lower()].append({
                    'id': detection.item_id,
                    'name': detection.name,
                    'tier': detection.tier,
                    'frame': detection.frame,
                    'pattern': detection.pattern,
                    'offset': detection.offset
                })
                seen_items.add(key)

        # Sort items within each category by ID
        for category in items_by_category:
            items_by_category[category].sort(key=lambda x: (x['id'], x['frame']))

        report = ItemExtractionReport(
            replay_dir=str(self.replay_dir),
            total_frames=len(self.frames),
            items_found=dict(items_by_category),
            total_unique_items=len(all_found_ids),
            detection_methods=dict(pattern_stats)
        )

        return report

    def get_player_builds(self) -> Dict:
        """
        Extract player item builds from replay.
        Analyzes item acquisitions across frames to reconstruct player inventories.
        """
        # Group detections by frame
        items_by_frame = defaultdict(list)
        for detection in self.detections:
            items_by_frame[detection.frame].append(detection)

        # Track item progression (simplified - full implementation would need player entity mapping)
        item_timeline = []
        unique_items = set()

        for frame_num in sorted(items_by_frame.keys()):
            frame_items = items_by_frame[frame_num]
            new_items = []

            for detection in frame_items:
                if detection.item_id not in unique_items:
                    new_items.append({
                        'frame': frame_num,
                        'item_id': detection.item_id,
                        'name': detection.name,
                        'category': detection.category,
                        'tier': detection.tier
                    })
                    unique_items.add(detection.item_id)

            if new_items:
                item_timeline.append({
                    'frame': frame_num,
                    'new_items': new_items
                })

        # Build summary by category
        build_summary = defaultdict(list)
        for item_id in unique_items:
            item_info = ITEM_ID_MAP.get(item_id)
            if item_info:
                build_summary[item_info['category'].lower()].append({
                    'id': item_id,
                    'name': item_info['name'],
                    'tier': item_info['tier']
                })

        # Sort each category
        for category in build_summary:
            build_summary[category].sort(key=lambda x: x['id'])

        return {
            'timeline': item_timeline,
            'build_summary': dict(build_summary),
            'total_items': len(unique_items)
        }


def print_summary(report: ItemExtractionReport, verbose: bool = False):
    """Print human-readable summary to stderr"""
    print("=" * 70, file=sys.stderr)
    print("ITEM EXTRACTION REPORT", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    print(f"Replay Directory: {report.replay_dir}", file=sys.stderr)
    print(f"Total Frames: {report.total_frames}", file=sys.stderr)
    print(f"Unique Items Found: {report.total_unique_items}", file=sys.stderr)
    print("", file=sys.stderr)

    print("Detection Methods:", file=sys.stderr)
    for method, count in sorted(report.detection_methods.items()):
        print(f"  {method}: {count} detections", file=sys.stderr)
    print("", file=sys.stderr)

    print("Items by Category:", file=sys.stderr)
    for category in ['weapon', 'crystal', 'defense', 'utility']:
        items = report.items_found.get(category, [])
        if items:
            unique_count = len(set(item['id'] for item in items))
            total_detections = len(items)
            print(f"\n  {category.upper()}: {unique_count} unique items, {total_detections} total detections", file=sys.stderr)

            if verbose:
                # Group by tier
                by_tier = defaultdict(list)
                for item in items:
                    by_tier[item['tier']].append(item)

                for tier in sorted(by_tier.keys()):
                    tier_items = by_tier[tier]
                    unique_in_tier = list({item['id']: item for item in tier_items}.values())
                    print(f"    Tier {tier}:", file=sys.stderr)
                    for item in sorted(unique_in_tier, key=lambda x: x['id']):
                        print(f"      {item['name']} (ID {item['id']})", file=sys.stderr)

    if report.player_builds:
        print(f"\n\nPlayer Build Timeline:", file=sys.stderr)
        print(f"  Total unique items acquired: {report.player_builds['total_items']}", file=sys.stderr)
        print(f"  Item acquisition events: {len(report.player_builds['timeline'])}", file=sys.stderr)

    print("=" * 70, file=sys.stderr)


def main():
    """CLI entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Extract all items from VG replay using unified pattern detection',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m vg.analysis.item_extractor "/path/to/replay/cache/"
  python -m vg.analysis.item_extractor "/path/to/replay/cache/" --json
  python -m vg.analysis.item_extractor "/path/to/replay/cache/" --player-builds --verbose
        """
    )

    parser.add_argument('replay_dir', type=Path,
                       help='Path to replay cache directory containing .vgr files')
    parser.add_argument('--json', action='store_true',
                       help='Output JSON format only (no summary)')
    parser.add_argument('--player-builds', action='store_true',
                       help='Include player build timeline analysis')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Verbose output with detailed item listings')

    args = parser.parse_args()

    # Validate replay directory
    if not args.replay_dir.exists():
        print(f"ERROR: Directory not found: {args.replay_dir}", file=sys.stderr)
        sys.exit(1)

    if not args.replay_dir.is_dir():
        print(f"ERROR: Not a directory: {args.replay_dir}", file=sys.stderr)
        sys.exit(1)

    # Run extraction
    if not args.json:
        print(f"Extracting items from: {args.replay_dir}", file=sys.stderr)
        print("Using combined pattern strategies...", file=sys.stderr)
        print("", file=sys.stderr)

    extractor = ItemExtractor(args.replay_dir)
    report = extractor.extract_items()

    # Add player builds if requested
    if args.player_builds:
        report.player_builds = extractor.get_player_builds()

    # Output
    if args.json:
        # JSON output to stdout
        output = asdict(report)
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        # Human-readable summary to stderr + JSON to stdout
        print_summary(report, verbose=args.verbose)
        print("\n", file=sys.stderr)
        print(json.dumps(asdict(report), indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
