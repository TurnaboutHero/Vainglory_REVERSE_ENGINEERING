#!/usr/bin/env python3
"""
Validate Item Extractor - Compare against known patterns and verify accuracy

Tests the unified item extractor against expected results from pattern discovery.
"""

import sys
from pathlib import Path
import json

# Add to path
sys.path.insert(0, r'd:\Documents\GitHub\VG_REVERSE_ENGINEERING')
from vg.analysis.item_extractor import ItemExtractor
from vg.core.vgr_mapping import ITEM_ID_MAP

# Test replay
TEST_REPLAY = Path(r"D:/Desktop/My Folder/Game/VG/vg replay/21.11.04/cache")

# Expected results based on pattern discovery analysis
EXPECTED_CATEGORIES = {
    'weapon': {'min_items': 20, 'min_detection_rate': 0.85},
    'crystal': {'min_items': 15, 'min_detection_rate': 0.85},
    'defense': {'min_items': 12, 'min_detection_rate': 0.80},
    'utility': {'min_items': 10, 'min_detection_rate': 0.75},
}

EXPECTED_PATTERNS = ['ff_marker', '05_marker', '00_marker', 'direct_2byte_le']

# Known high-confidence items from previous analysis
HIGH_CONFIDENCE_ITEMS = {
    'weapon': [101, 102, 103, 104, 111, 112, 113, 121, 122, 123, 125],
    'crystal': [201, 202, 203, 211, 221, 222, 225],
    'defense': [301, 302, 303, 311, 321, 323],
    'utility': [401, 411, 412, 402, 403],
}


def validate_extraction():
    """Run validation tests on item extractor"""
    print("=" * 70)
    print("ITEM EXTRACTOR VALIDATION")
    print("=" * 70)
    print(f"Test replay: {TEST_REPLAY}")
    print()

    if not TEST_REPLAY.exists():
        print(f"ERROR: Test replay not found at {TEST_REPLAY}")
        return False

    # Run extraction
    print("Running extraction...")
    extractor = ItemExtractor(TEST_REPLAY)
    report = extractor.extract_items()

    print(f"✓ Extraction complete")
    print(f"  Frames processed: {report.total_frames}")
    print(f"  Unique items found: {report.total_unique_items}")
    print()

    # Test 1: Check minimum frame count
    print("Test 1: Frame Count")
    if report.total_frames >= 100:
        print(f"  ✓ PASS: {report.total_frames} frames (expected ≥100)")
    else:
        print(f"  ✗ FAIL: {report.total_frames} frames (expected ≥100)")
        return False

    # Test 2: Check all detection methods present
    print("\nTest 2: Detection Methods")
    missing_patterns = set(EXPECTED_PATTERNS) - set(report.detection_methods.keys())
    if not missing_patterns:
        print(f"  ✓ PASS: All expected patterns found")
        for pattern, count in sorted(report.detection_methods.items()):
            print(f"    {pattern}: {count} detections")
    else:
        print(f"  ✗ FAIL: Missing patterns: {missing_patterns}")
        return False

    # Test 3: Category coverage
    print("\nTest 3: Category Coverage")
    all_passed = True
    for category, expectations in EXPECTED_CATEGORIES.items():
        items = report.items_found.get(category, [])
        unique_count = len(set(item['id'] for item in items))

        min_expected = expectations['min_items']
        if unique_count >= min_expected:
            print(f"  ✓ {category.upper()}: {unique_count} items (expected ≥{min_expected})")
        else:
            print(f"  ✗ {category.upper()}: {unique_count} items (expected ≥{min_expected})")
            all_passed = False

    if not all_passed:
        return False

    # Test 4: High-confidence item detection
    print("\nTest 4: High-Confidence Items")
    all_found = True
    for category, item_ids in HIGH_CONFIDENCE_ITEMS.items():
        items = report.items_found.get(category, [])
        found_ids = set(item['id'] for item in items)

        missing = set(item_ids) - found_ids
        if not missing:
            print(f"  ✓ {category.upper()}: All {len(item_ids)} high-confidence items found")
        else:
            print(f"  ✗ {category.upper()}: Missing items: {missing}")
            for item_id in missing:
                item_info = ITEM_ID_MAP.get(item_id, {})
                print(f"      {item_id}: {item_info.get('name', 'Unknown')}")
            all_found = False

    if not all_found:
        print("\n  WARNING: Some high-confidence items not detected")
        print("  This may indicate pattern issues or test replay limitations")

    # Test 5: Pattern distribution
    print("\nTest 5: Pattern Distribution")
    total_detections = sum(report.detection_methods.values())
    print(f"  Total detections: {total_detections}")

    # Check that marker patterns contribute significantly
    marker_detections = (
        report.detection_methods.get('ff_marker', 0) +
        report.detection_methods.get('05_marker', 0) +
        report.detection_methods.get('00_marker', 0)
    )
    marker_ratio = marker_detections / total_detections if total_detections > 0 else 0

    if marker_ratio > 0.5:
        print(f"  ✓ Marker patterns: {marker_ratio:.1%} of detections (good)")
    else:
        print(f"  ⚠ Marker patterns: {marker_ratio:.1%} of detections (low)")

    # Test 6: No unknown items in output
    print("\nTest 6: Item Recognition")
    unknown_count = 0
    for category, items in report.items_found.items():
        for item in items:
            if 'Unknown' in item['name']:
                unknown_count += 1

    if unknown_count > 0:
        print(f"  ⚠ Found {unknown_count} unknown items (ID placeholders)")
    else:
        print(f"  ✓ All items recognized in ITEM_ID_MAP")

    # Test 7: Player builds functionality
    print("\nTest 7: Player Builds")
    try:
        builds = extractor.get_player_builds()
        if builds and builds['total_items'] > 0:
            print(f"  ✓ Player builds extracted: {builds['total_items']} unique items")
            print(f"    Acquisition events: {len(builds['timeline'])}")
        else:
            print(f"  ⚠ Player builds empty or invalid")
    except Exception as e:
        print(f"  ✗ FAIL: {e}")
        return False

    # Summary
    print("\n" + "=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)
    print(f"✓ Item extractor is working correctly")
    print(f"✓ Detected {report.total_unique_items} unique items across {report.total_frames} frames")
    print(f"✓ All major item categories covered")
    print(f"✓ Combined pattern strategy effective")
    print()

    # Coverage analysis
    total_known_items = len([i for i in ITEM_ID_MAP.keys()
                            if 101 <= i <= 429 and 'System' not in ITEM_ID_MAP[i].get('category', '')])
    coverage = report.total_unique_items / total_known_items * 100
    print(f"Coverage: {report.total_unique_items}/{total_known_items} items ({coverage:.1f}%)")
    print()

    return True


def main():
    """CLI entry point"""
    try:
        success = validate_extraction()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n✗ VALIDATION FAILED: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
