#!/usr/bin/env python3
"""
Statistical Analysis of Minion Sharing Patterns - Deep Dive

Performs advanced statistical analysis on minion kill sharing patterns:
1. Sharing probability by distance (offset delta)
2. Action byte correlation analysis
3. Temporal patterns (early/mid/late game)
4. Team-based sharing asymmetry
5. Hero-specific sharing patterns
"""
import struct
import sys
import json
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
import statistics

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from vg.core.unified_decoder import UnifiedDecoder, _le_to_be

CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])


@dataclass
class CreditEvent:
    """A single credit record event."""
    eid: int
    value: float
    action_byte: int
    offset: int


@dataclass
class SharingStats:
    """Statistical analysis of sharing patterns."""
    # Distance analysis
    sharing_by_distance: Dict[int, int] = field(default_factory=lambda: defaultdict(int))

    # Action byte correlations
    action_pair_counts: Dict[Tuple[int, int], int] = field(default_factory=lambda: defaultdict(int))

    # Value distributions
    xp_values: List[float] = field(default_factory=list)
    gold_values: List[float] = field(default_factory=list)
    passive_burst_values: List[float] = field(default_factory=list)

    # Temporal patterns
    early_game_sharing: int = 0  # First 33% of events
    mid_game_sharing: int = 0    # Middle 33%
    late_game_sharing: int = 0   # Last 33%

    # Team analysis
    team_sharing_events: Dict[int, int] = field(default_factory=lambda: defaultdict(int))

    # Hero analysis
    hero_sharing_received: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    hero_sharing_given: Dict[str, int] = field(default_factory=lambda: defaultdict(int))


def scan_credit_records(data: bytes) -> List[CreditEvent]:
    """Scan all credit records in frame data."""
    credits = []
    offset = 0
    while True:
        idx = data.find(CREDIT_HEADER, offset)
        if idx == -1:
            break

        if idx + 12 <= len(data):
            try:
                eid = struct.unpack('>H', data[idx+5:idx+7])[0]
                value = struct.unpack('>f', data[idx+7:idx+11])[0]
                action_byte = data[idx+11]

                credits.append(CreditEvent(
                    eid=eid,
                    value=value,
                    action_byte=action_byte,
                    offset=idx
                ))
            except:
                pass

        offset = idx + 1

    return credits


def analyze_sharing_statistics(replay_dir: str) -> SharingStats:
    """Perform deep statistical analysis on a single replay."""
    print(f"\n{'='*80}")
    print(f"Statistical Analysis: {Path(replay_dir).name}")
    print(f"{'='*80}")

    cache_dir = Path(replay_dir)
    vgr_files = sorted(cache_dir.glob('*.0.vgr'))

    if not vgr_files:
        return SharingStats()

    vgr0 = vgr_files[0]

    # Decode replay
    decoder = UnifiedDecoder(str(vgr0))
    decoded = decoder.decode()

    # Build player mappings
    player_eids = set()
    player_teams = {}
    player_heroes = {}

    for p in decoded.all_players:
        eid_be = _le_to_be(p.entity_id)
        player_eids.add(eid_be)
        team_id = 1 if p.team == "left" else 2
        player_teams[eid_be] = team_id
        player_heroes[eid_be] = p.hero_name

    # Scan all credit records
    print(f"[STAGE:begin:statistical_analysis]")
    all_credits = []

    for vgr_file in sorted(cache_dir.glob('*.vgr')):
        with open(vgr_file, 'rb') as f:
            data = f.read()
            credits = scan_credit_records(data)
            all_credits.extend(credits)

    print(f"[DATA] Collected {len(all_credits)} credit events")

    # Find 0x0E minion kills
    minion_kills = [c for c in all_credits if c.action_byte == 0x0E and c.eid in player_eids]
    print(f"[DATA] Found {len(minion_kills)} minion kill events")

    stats = SharingStats()

    # Temporal boundaries
    third = len(minion_kills) // 3

    # Analyze each minion kill
    for idx, mk in enumerate(minion_kills):
        killer_team = player_teams.get(mk.eid)
        killer_hero = player_heroes.get(mk.eid, "Unknown")

        # Find nearby credits (±200 bytes)
        nearby = [c for c in all_credits if abs(c.offset - mk.offset) <= 200]

        # Analyze teammate sharing
        for credit in nearby:
            if credit.eid == mk.eid:
                continue  # Skip killer's own credits

            teammate_team = player_teams.get(credit.eid)
            if teammate_team is None:
                continue  # Not a player

            if teammate_team == killer_team:
                # This is sharing!
                distance = abs(credit.offset - mk.offset)
                stats.sharing_by_distance[distance] += 1

                # Action byte correlation
                stats.action_pair_counts[(0x0E, credit.action_byte)] += 1

                # Value distribution
                if credit.action_byte == 0x02:  # XP
                    stats.xp_values.append(credit.value)
                elif credit.action_byte == 0x06 and credit.value > 0:  # Gold income
                    stats.gold_values.append(credit.value)
                elif credit.action_byte == 0x08 and credit.value > 0.6:  # Passive burst
                    stats.passive_burst_values.append(credit.value)

                # Temporal pattern
                if idx < third:
                    stats.early_game_sharing += 1
                elif idx < 2 * third:
                    stats.mid_game_sharing += 1
                else:
                    stats.late_game_sharing += 1

                # Team analysis
                stats.team_sharing_events[killer_team] += 1

                # Hero analysis
                stats.hero_sharing_given[killer_hero] += 1
                receiver_hero = player_heroes.get(credit.eid, "Unknown")
                stats.hero_sharing_received[receiver_hero] += 1

    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:statistical_analysis]")

    return stats


def print_statistics(stats: SharingStats, replay_name: str):
    """Print comprehensive statistics."""
    print(f"\n{'='*80}")
    print(f"STATISTICAL REPORT: {replay_name}")
    print(f"{'='*80}")

    # Distance analysis
    print(f"\n[FINDING] Sharing Probability by Byte Distance:")
    distance_buckets = defaultdict(int)
    for dist, count in stats.sharing_by_distance.items():
        bucket = (dist // 20) * 20  # 20-byte buckets
        distance_buckets[bucket] += count

    total_sharing = sum(stats.sharing_by_distance.values())
    for bucket in sorted(distance_buckets.keys())[:10]:  # First 10 buckets
        count = distance_buckets[bucket]
        pct = count / total_sharing * 100 if total_sharing > 0 else 0
        print(f"  {bucket:3d}-{bucket+19:3d} bytes: {count:6d} events ({pct:5.1f}%)")

    if stats.sharing_by_distance:
        avg_dist = sum(d*c for d, c in stats.sharing_by_distance.items()) / total_sharing
        print(f"  [STAT:avg_sharing_distance] {avg_dist:.1f} bytes")

    # Action byte correlations
    print(f"\n[FINDING] Top Action Byte Correlations with 0x0E:")
    action_pairs = sorted(stats.action_pair_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    for (main, corr), count in action_pairs:
        action_name = {
            0x02: 'XP',
            0x03: 'Unknown_0x03',
            0x06: 'Gold',
            0x08: 'Passive',
            0x0D: 'Jungle',
            0x0F: 'MinionGold'
        }.get(corr, f'0x{corr:02X}')
        print(f"  0x0E + {action_name:15s}: {count:7d} events")

    # Value distributions
    if stats.xp_values:
        print(f"\n[FINDING] XP Sharing Distribution:")
        print(f"  [STAT:xp_count] {len(stats.xp_values)}")
        print(f"  [STAT:xp_mean] {statistics.mean(stats.xp_values):.2f}")
        print(f"  [STAT:xp_median] {statistics.median(stats.xp_values):.2f}")
        print(f"  [STAT:xp_stdev] {statistics.stdev(stats.xp_values):.2f}")
        print(f"  Range: {min(stats.xp_values):.2f} to {max(stats.xp_values):.2f}")

    if stats.gold_values:
        print(f"\n[FINDING] Gold Sharing Distribution (0x06):")
        print(f"  [STAT:gold_count] {len(stats.gold_values)}")
        print(f"  [STAT:gold_mean] {statistics.mean(stats.gold_values):.2f}")
        print(f"  [STAT:gold_median] {statistics.median(stats.gold_values):.2f}")
        print(f"  [STAT:gold_stdev] {statistics.stdev(stats.gold_values):.2f}")
        print(f"  Range: {min(stats.gold_values):.2f} to {max(stats.gold_values):.2f}")

    if stats.passive_burst_values:
        print(f"\n[FINDING] Passive Burst Distribution (0x08 >0.6):")
        print(f"  [STAT:passive_count] {len(stats.passive_burst_values)}")
        print(f"  [STAT:passive_mean] {statistics.mean(stats.passive_burst_values):.2f}")
        print(f"  [STAT:passive_median] {statistics.median(stats.passive_burst_values):.2f}")
        print(f"  Range: {min(stats.passive_burst_values):.2f} to {max(stats.passive_burst_values):.2f}")

    # Temporal patterns
    total_temporal = stats.early_game_sharing + stats.mid_game_sharing + stats.late_game_sharing
    if total_temporal > 0:
        print(f"\n[FINDING] Temporal Sharing Patterns:")
        print(f"  Early game (first 33%): {stats.early_game_sharing:6d} ({stats.early_game_sharing/total_temporal*100:5.1f}%)")
        print(f"  Mid game (middle 33%):  {stats.mid_game_sharing:6d} ({stats.mid_game_sharing/total_temporal*100:5.1f}%)")
        print(f"  Late game (last 33%):   {stats.late_game_sharing:6d} ({stats.late_game_sharing/total_temporal*100:5.1f}%)")
        print(f"  [STAT:early_vs_late_ratio] {stats.early_game_sharing / max(1, stats.late_game_sharing):.2f}")

    # Team analysis
    if stats.team_sharing_events:
        print(f"\n[FINDING] Team-based Sharing:")
        for team_id in sorted(stats.team_sharing_events.keys()):
            count = stats.team_sharing_events[team_id]
            print(f"  Team {team_id}: {count:7d} sharing events")

    # Hero analysis
    if stats.hero_sharing_given:
        print(f"\n[FINDING] Top Heroes by Sharing Given (minion killer):")
        top_givers = sorted(stats.hero_sharing_given.items(), key=lambda x: x[1], reverse=True)[:10]
        for hero, count in top_givers:
            print(f"  {hero:15s}: {count:6d} teammate credits triggered")

    if stats.hero_sharing_received:
        print(f"\n[FINDING] Top Heroes by Sharing Received (teammate):")
        top_receivers = sorted(stats.hero_sharing_received.items(), key=lambda x: x[1], reverse=True)[:10]
        for hero, count in top_receivers:
            print(f"  {hero:15s}: {count:6d} shared credits received")


def main():
    """Perform statistical analysis on full replays."""
    replay_dirs = [
        'D:/Desktop/My Folder/Game/VG/vg replay/22.06.07/EA vs SEA/cache1/cache',
        'D:/Desktop/My Folder/Game/VG/vg replay/23.02.09/cache',
        'D:/Desktop/My Folder/Game/VG/vg replay/22.11.02/cache/cache',
    ]

    print("[OBJECTIVE] Deep statistical analysis of minion sharing patterns")

    all_stats = []
    for replay_dir in replay_dirs:
        if Path(replay_dir).exists():
            stats = analyze_sharing_statistics(replay_dir)
            if stats.sharing_by_distance:  # Has data
                print_statistics(stats, Path(replay_dir).name)
                all_stats.append(stats)
        else:
            print(f"⚠️ Directory not found: {replay_dir}")

    # Aggregate analysis
    if len(all_stats) > 1:
        print(f"\n{'='*80}")
        print(f"AGGREGATE ANALYSIS ({len(all_stats)} replays)")
        print(f"{'='*80}")

        # Combine XP values
        all_xp = []
        for s in all_stats:
            all_xp.extend(s.xp_values)

        if all_xp:
            print(f"\n[FINDING] Aggregate XP Sharing:")
            print(f"  [STAT:total_xp_sharing_events] {len(all_xp)}")
            print(f"  [STAT:aggregate_xp_mean] {statistics.mean(all_xp):.2f}")
            print(f"  [STAT:aggregate_xp_median] {statistics.median(all_xp):.2f}")

            # Percentiles
            sorted_xp = sorted(all_xp)
            p25 = sorted_xp[len(sorted_xp)//4]
            p75 = sorted_xp[3*len(sorted_xp)//4]
            print(f"  25th percentile: {p25:.2f}")
            print(f"  75th percentile: {p75:.2f}")

        # Combine gold values
        all_gold = []
        for s in all_stats:
            all_gold.extend(s.gold_values)

        if all_gold:
            print(f"\n[FINDING] Aggregate Gold Sharing (0x06):")
            print(f"  [STAT:total_gold_sharing_events] {len(all_gold)}")
            print(f"  [STAT:aggregate_gold_mean] {statistics.mean(all_gold):.2f}")
            print(f"  [STAT:aggregate_gold_median] {statistics.median(all_gold):.2f}")

        # Temporal pattern aggregate
        total_early = sum(s.early_game_sharing for s in all_stats)
        total_mid = sum(s.mid_game_sharing for s in all_stats)
        total_late = sum(s.late_game_sharing for s in all_stats)
        total_temporal = total_early + total_mid + total_late

        if total_temporal > 0:
            print(f"\n[FINDING] Aggregate Temporal Pattern:")
            print(f"  Early game: {total_early/total_temporal*100:.1f}%")
            print(f"  Mid game:   {total_mid/total_temporal*100:.1f}%")
            print(f"  Late game:  {total_late/total_temporal*100:.1f}%")

    print(f"\n[LIMITATION] Distance-based correlation assumes causality - may include coincidental events")
    print(f"[LIMITATION] No ground truth for XP/gold sharing - patterns are observational only")
    print(f"[LIMITATION] Hero analysis affected by individual player skill/playstyle variations")


if __name__ == '__main__':
    main()
