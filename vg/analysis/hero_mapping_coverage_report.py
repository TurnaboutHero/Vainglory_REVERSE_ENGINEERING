#!/usr/bin/env python3
"""
Hero Mapping Coverage Report
Analyzes coverage of BINARY_HERO_ID_MAP vs complete hero roster (56 heroes)
Shows which heroes are mapped vs unmapped, and which were confirmed by tournament data.
"""

import json
import sys
import io
from pathlib import Path

# Fix Windows console encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Import existing mapping
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.vgr_mapping import BINARY_HERO_ID_MAP, HERO_ID_MAP

def main():
    print("="*80)
    print("HERO MAPPING COVERAGE REPORT")
    print("="*80)

    # Load tournament confirmation data
    analysis_file = Path("D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/hero_mapping_analysis.json")
    with open(analysis_file, 'r', encoding='utf-8') as f:
        analysis = json.load(f)

    confirmed_heroes = set(analysis['confirmed_mappings'].values())

    # Get all hero names from HERO_ID_MAP (complete roster)
    all_heroes = {info['name'] for info in HERO_ID_MAP.values()}

    # Get mapped hero names from BINARY_HERO_ID_MAP
    mapped_heroes = set(BINARY_HERO_ID_MAP.values())

    # Calculate sets
    confirmed = confirmed_heroes
    mapped_unconfirmed = mapped_heroes - confirmed_heroes
    unmapped = all_heroes - mapped_heroes

    print(f"\n[STAT:total_heroes] {len(all_heroes)} (complete VG roster)")
    print(f"[STAT:mapped_heroes] {len(mapped_heroes)} ({len(mapped_heroes)/len(all_heroes)*100:.1f}%)")
    print(f"[STAT:confirmed_by_tournament] {len(confirmed)} ({len(confirmed)/len(all_heroes)*100:.1f}%)")
    print(f"[STAT:mapped_unconfirmed] {len(mapped_unconfirmed)} ({len(mapped_unconfirmed)/len(all_heroes)*100:.1f}%)")
    print(f"[STAT:unmapped] {len(unmapped)} ({len(unmapped)/len(all_heroes)*100:.1f}%)")

    # Confirmed heroes (tournament validated)
    print(f"\n{'='*80}")
    print(f"CONFIRMED HEROES ({len(confirmed)}) - Tournament Validated")
    print(f"{'='*80}")
    for i, hero in enumerate(sorted(confirmed), 1):
        # Find binary ID
        bin_id = next((f"0x{bid:04X}" for bid, name in BINARY_HERO_ID_MAP.items() if name == hero), "???")
        print(f"{i:2d}. {hero:20s} {bin_id}")

    # Mapped but unconfirmed (no tournament data)
    print(f"\n{'='*80}")
    print(f"MAPPED BUT UNCONFIRMED ({len(mapped_unconfirmed)}) - No Tournament Data")
    print(f"{'='*80}")
    if mapped_unconfirmed:
        for i, hero in enumerate(sorted(mapped_unconfirmed), 1):
            bin_id = next((f"0x{bid:04X}" for bid, name in BINARY_HERO_ID_MAP.items() if name == hero), "???")
            # Check if it's marked as inferred in mapping
            status = "inferred" if any(hero in str(BINARY_HERO_ID_MAP.get(bid, ""))
                                       for bid in BINARY_HERO_ID_MAP.keys()) else "unknown"
            print(f"{i:2d}. {hero:20s} {bin_id:8s} (confidence: medium - no tournament validation)")
    else:
        print("None - all mapped heroes confirmed by tournament data")

    # Unmapped heroes
    print(f"\n{'='*80}")
    print(f"UNMAPPED HEROES ({len(unmapped)}) - Binary ID Unknown")
    print(f"{'='*80}")
    if unmapped:
        # Find hero IDs from HERO_ID_MAP
        unmapped_with_ids = []
        for hero_id, info in HERO_ID_MAP.items():
            if info['name'] in unmapped:
                unmapped_with_ids.append((hero_id, info['name'], info['role']))

        unmapped_with_ids.sort(key=lambda x: x[0])
        for i, (hero_id, hero_name, role) in enumerate(unmapped_with_ids, 1):
            print(f"{i:2d}. ID {hero_id:2d}: {hero_name:20s} ({role})")
    else:
        print("None - complete mapping achieved!")

    # Summary by role
    print(f"\n{'='*80}")
    print(f"UNMAPPED HEROES BY ROLE")
    print(f"{'='*80}")

    unmapped_by_role = {}
    for hero_id, info in HERO_ID_MAP.items():
        if info['name'] in unmapped:
            role = info['role']
            if role not in unmapped_by_role:
                unmapped_by_role[role] = []
            unmapped_by_role[role].append(info['name'])

    if unmapped_by_role:
        for role in sorted(unmapped_by_role.keys()):
            heroes = sorted(unmapped_by_role[role])
            print(f"\n{role} ({len(heroes)}):")
            for hero in heroes:
                print(f"  - {hero}")
    else:
        print("No unmapped heroes!")

    # Coverage progress
    print(f"\n{'='*80}")
    print(f"COVERAGE PROGRESS")
    print(f"{'='*80}")
    print(f"Tournament Coverage:  {len(confirmed)}/{len(all_heroes)} ({len(confirmed)/len(all_heroes)*100:.1f}%)")
    print(f"Total Mapping:        {len(mapped_heroes)}/{len(all_heroes)} ({len(mapped_heroes)/len(all_heroes)*100:.1f}%)")
    print(f"Remaining:            {len(unmapped)}/{len(all_heroes)} ({len(unmapped)/len(all_heroes)*100:.1f}%)")

    print(f"\n{'='*80}")
    print(f"RECOMMENDATIONS")
    print(f"{'='*80}")

    if len(unmapped) > 0:
        print(f"[LIMITATION] {len(unmapped)} heroes not yet mapped - need replay files containing these heroes:")
        unmapped_sorted = sorted([info['name'] for hero_id, info in HERO_ID_MAP.items()
                                  if info['name'] in unmapped])
        for hero in unmapped_sorted:
            print(f"  - {hero}")
        print(f"\nTo expand mapping, collect replays featuring these {len(unmapped)} heroes.")
    else:
        print("[FINDING] Complete mapping achieved - all 56 heroes mapped!")

    if len(mapped_unconfirmed) > 0:
        print(f"\n[LIMITATION] {len(mapped_unconfirmed)} mapped heroes not confirmed by tournament data")
        print("These mappings are inferred from patterns but lack empirical validation.")
        print("Consider collecting replays to validate these mappings.")

    # Save report
    report_file = Path("D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/hero_mapping_coverage_report.txt")
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(f"BINARY_HERO_ID_MAP Coverage Report\n")
        f.write(f"{'='*80}\n\n")
        f.write(f"Total Heroes: {len(all_heroes)}\n")
        f.write(f"Mapped: {len(mapped_heroes)} ({len(mapped_heroes)/len(all_heroes)*100:.1f}%)\n")
        f.write(f"Confirmed by Tournament: {len(confirmed)} ({len(confirmed)/len(all_heroes)*100:.1f}%)\n")
        f.write(f"Unmapped: {len(unmapped)} ({len(unmapped)/len(all_heroes)*100:.1f}%)\n\n")

        if unmapped:
            f.write(f"Unmapped Heroes:\n")
            for hero_id, info in sorted(HERO_ID_MAP.items()):
                if info['name'] in unmapped:
                    f.write(f"  ID {hero_id:2d}: {info['name']} ({info['role']})\n")

    print(f"\n[FINDING] Report saved to {report_file}")

if __name__ == '__main__':
    main()
