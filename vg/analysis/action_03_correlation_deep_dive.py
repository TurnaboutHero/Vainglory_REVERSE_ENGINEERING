#!/usr/bin/env python3
"""
Action 0x03 Deep Dive: Hero-Specific Passive Analysis

Key findings from initial analysis:
1. Action 0x03 is 100% PLAYER-ONLY (never minions/structures)
2. TWO hero patterns detected:
   - Lance: 100% of records (2/3 replays), values 1.25-3.60, mostly 2.50-2.60
   - Blackfeather: 59.4% in mixed replay, values 1.00 dominant (56%)
3. High autocorrelation: 0x03 often followed by 0x03 (offset ±1 shows 0x03 > 50%)

Hypothesis: Action 0x03 = HERO PASSIVE PROC
- Lance passive: Impale damage reduction stacks (explains 2.5-2.6 repeated values)
- Blackfeather passive: Heartthrob stacks or On Point damage (explains 1.0 procs)

This script:
1. Identifies which heroes receive 0x03 across ALL replays
2. Analyzes value patterns per hero
3. Investigates temporal clustering (burst vs sustained)
4. Correlates with combat events (kills, deaths nearby)
"""

import struct
import sys
from collections import defaultdict, Counter
from pathlib import Path
from typing import Dict, List, Tuple
import statistics

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from vg.core.unified_decoder import UnifiedDecoder, _le_to_be

CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])
KILL_HEADER = bytes([0x18, 0x04, 0x1C])
DEATH_HEADER = bytes([0x08, 0x04, 0x31])

def extract_player_entities(cache_dir: Path) -> Dict[int, str]:
    """Extract player entity IDs from .0.vgr file."""
    vgr0 = list(cache_dir.glob('*.0.vgr'))[0]
    decoder = UnifiedDecoder(str(vgr0))
    decoded = decoder.decode()
    return {_le_to_be(p.entity_id): p.hero_name for p in decoded.all_players}

def load_all_frames(cache_dir: Path) -> bytes:
    """Load all frame data from .vgr files."""
    vgr_files = sorted(
        cache_dir.glob('*.vgr'),
        key=lambda f: int(f.stem.split('.')[-1]) if f.stem.split('.')[-1].isdigit() else 0
    )
    return b''.join(f.read_bytes() for f in vgr_files)

def find_kills_deaths(data: bytes) -> Tuple[List[int], List[int]]:
    """Find positions of kill and death events."""
    kills = []
    deaths = []

    idx = 0
    while idx < len(data) - 20:
        if data[idx:idx+3] == KILL_HEADER:
            kills.append(idx)
        elif data[idx:idx+3] == DEATH_HEADER:
            deaths.append(idx)
        idx += 1

    return kills, deaths

def analyze_hero_patterns(data: bytes, player_eids: Dict[int, str]) -> dict:
    """Detailed per-hero analysis of 0x03 patterns."""

    hero_stats = defaultdict(lambda: {
        'count': 0,
        'values': [],
        'value_counter': Counter(),
        'intervals': [],  # Time between consecutive 0x03 for same hero
        'burst_clusters': 0,  # Count of rapid sequences (< 100 bytes apart)
        'positions': []
    })

    # Find all 0x03 credits
    idx = 0
    last_pos_by_hero = {}

    while idx < len(data) - 12:
        if data[idx:idx+3] == CREDIT_HEADER:
            try:
                eid = struct.unpack('>H', data[idx+5:idx+7])[0]
                value = struct.unpack('>f', data[idx+7:idx+11])[0]
                action = data[idx+11]

                if action == 0x03 and eid in player_eids:
                    hero = player_eids[eid]

                    hero_stats[hero]['count'] += 1
                    hero_stats[hero]['values'].append(value)
                    hero_stats[hero]['value_counter'][round(value, 2)] += 1
                    hero_stats[hero]['positions'].append(idx)

                    # Calculate interval from last occurrence
                    if hero in last_pos_by_hero:
                        interval = idx - last_pos_by_hero[hero]
                        hero_stats[hero]['intervals'].append(interval)

                        # Detect burst clusters (< 100 bytes = rapid succession)
                        if interval < 100:
                            hero_stats[hero]['burst_clusters'] += 1

                    last_pos_by_hero[hero] = idx

            except struct.error:
                pass

            idx += 12
        else:
            idx += 1

    return hero_stats

def analyze_combat_correlation(data: bytes, hero_stats: dict, player_eids: Dict[int, str]) -> dict:
    """Check if 0x03 events correlate with kills/deaths."""

    kills, deaths = find_kills_deaths(data)

    combat_correlation = defaultdict(lambda: {
        'near_kills': 0,  # 0x03 within 5000 bytes of a kill
        'near_deaths': 0,  # 0x03 within 5000 bytes of a death
    })

    for hero, stats in hero_stats.items():
        for pos in stats['positions']:
            # Check proximity to kills
            for kill_pos in kills:
                if abs(pos - kill_pos) < 5000:
                    combat_correlation[hero]['near_kills'] += 1
                    break

            # Check proximity to deaths
            for death_pos in deaths:
                if abs(pos - death_pos) < 5000:
                    combat_correlation[hero]['near_deaths'] += 1
                    break

    return combat_correlation

def print_hero_analysis(replay_name: str, hero_stats: dict, combat_corr: dict):
    """Print comprehensive per-hero analysis."""

    print(f"\n{'='*80}")
    print(f"[OBJECTIVE] Hero-Specific Passive Analysis - {replay_name}")
    print(f"{'='*80}\n")

    total_0x03 = sum(stats['count'] for stats in hero_stats.values())
    print(f"[STAT:total_0x03] {total_0x03:,}")
    print(f"[STAT:unique_heroes] {len(hero_stats)}")

    print(f"\n[FINDING] Heroes Receiving 0x03:")
    for hero in sorted(hero_stats.keys(), key=lambda h: -hero_stats[h]['count']):
        stats = hero_stats[hero]
        pct = 100 * stats['count'] / total_0x03
        print(f"  {hero:20s}: {stats['count']:6,} ({pct:5.1f}%)")

    # Detailed per-hero breakdown
    for hero in sorted(hero_stats.keys(), key=lambda h: -hero_stats[h]['count']):
        stats = hero_stats[hero]

        print(f"\n{'─'*80}")
        print(f"[FINDING] {hero} - Detailed Pattern Analysis")
        print(f"{'─'*80}")

        print(f"[STAT:{hero}_count] {stats['count']:,}")

        if stats['values']:
            print(f"[STAT:{hero}_value_mean] {statistics.mean(stats['values']):.4f}")
            print(f"[STAT:{hero}_value_median] {statistics.median(stats['values']):.4f}")
            print(f"[STAT:{hero}_value_min] {min(stats['values']):.4f}")
            print(f"[STAT:{hero}_value_max] {max(stats['values']):.4f}")

        # Top values
        print(f"\nTop Value Distribution:")
        for value, count in stats['value_counter'].most_common(10):
            pct = 100 * count / stats['count']
            print(f"  {value:8.2f}: {count:6,} ({pct:5.1f}%)")

        # Interval analysis
        if stats['intervals']:
            print(f"\nInterval Statistics (bytes between consecutive 0x03):")
            print(f"  Mean interval:   {statistics.mean(stats['intervals']):8,.1f} bytes")
            print(f"  Median interval: {statistics.median(stats['intervals']):8,.1f} bytes")
            print(f"  Min interval:    {min(stats['intervals']):8,} bytes")
            print(f"  Max interval:    {max(stats['intervals']):8,} bytes")
            print(f"  Burst clusters:  {stats['burst_clusters']:6,} (<100 bytes apart)")
            burst_pct = 100 * stats['burst_clusters'] / len(stats['intervals'])
            print(f"  Burst rate:      {burst_pct:5.1f}%")

        # Combat correlation
        if hero in combat_corr:
            corr = combat_corr[hero]
            near_kill_pct = 100 * corr['near_kills'] / stats['count']
            near_death_pct = 100 * corr['near_deaths'] / stats['count']
            print(f"\nCombat Correlation (±5000 bytes):")
            print(f"  Near kills:  {corr['near_kills']:6,} ({near_kill_pct:5.1f}%)")
            print(f"  Near deaths: {corr['near_deaths']:6,} ({near_death_pct:5.1f}%)")

def main():
    print("[STAGE:begin:hero_passive_analysis]")

    replay_dirs = [
        Path('D:/Desktop/My Folder/Game/VG/vg replay/22.06.07/EA vs SEA/cache1/cache'),  # 216 frames
        Path('D:/Desktop/My Folder/Game/VG/vg replay/23.02.09/cache'),  # 206 frames
        Path('D:/Desktop/My Folder/Game/VG/vg replay/22.11.02/cache/cache'),  # 195 frames
    ]

    all_heroes_0x03 = set()

    for replay_dir in replay_dirs:
        if not replay_dir.exists():
            print(f"[LIMITATION] Replay directory not found: {replay_dir}")
            continue

        try:
            player_eids = extract_player_entities(replay_dir)
            all_data = load_all_frames(replay_dir)

            hero_stats = analyze_hero_patterns(all_data, player_eids)
            combat_corr = analyze_combat_correlation(all_data, hero_stats, player_eids)

            all_heroes_0x03.update(hero_stats.keys())

            print_hero_analysis(replay_dir.parent.name, hero_stats, combat_corr)

        except Exception as e:
            print(f"[LIMITATION] Error analyzing {replay_dir.name}: {e}")
            import traceback
            traceback.print_exc()

    # Cross-replay summary
    print(f"\n{'='*80}")
    print(f"[FINDING] Cross-Replay Summary")
    print(f"{'='*80}\n")
    print(f"[STAT:total_unique_heroes_with_0x03] {len(all_heroes_0x03)}")
    print(f"Heroes with 0x03 events: {sorted(all_heroes_0x03)}")

    print(f"\n[STAGE:status:success]")
    print(f"[STAGE:end:hero_passive_analysis]")

if __name__ == '__main__':
    main()
