#!/usr/bin/env python3
"""
Gold & XP Sharing Analysis - Credit Record Action Byte Pattern Analysis

Analyzes credit record [10 04 1D] action bytes to validate game mechanics:
1. Action 0x08 (passive gold): Equal distribution across all players?
2. Action 0x0F (minion gold): Shared among nearby teammates?
3. Action 0x0D (jungle gold): Single recipient only?
4. Action 0x02 (XP?): Sharing pattern identification
5. Action 0x03: Event correlation analysis

Credit Record Structure: [10 04 1D][00 00][eid BE 2B][value f32 BE][action_byte 1B] (12 bytes)
"""

import sys
from pathlib import Path
from collections import defaultdict, Counter
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple
import struct
import json

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from vg.core.unified_decoder import UnifiedDecoder, _le_to_be


@dataclass
class CreditRecord:
    """Single credit record"""
    offset: int
    entity_id_be: int
    value: float
    action_byte: int
    timestamp_approx: float  # Approximate based on offset


def extract_all_credits(data: bytes) -> List[CreditRecord]:
    """Extract all credit records from replay binary"""
    CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])
    credits = []

    i = 0
    while i < len(data) - 12:
        if data[i:i+3] == CREDIT_HEADER:
            offset = i
            # Parse: [10 04 1D][00 00][eid BE 2B][value f32 BE][action 1B]
            eid_be = struct.unpack('>H', data[i+5:i+7])[0]
            value = struct.unpack('>f', data[i+7:i+11])[0]
            action = data[i+11]

            # Approximate timestamp based on offset (very rough)
            timestamp_approx = offset / 1_000_000  # ~1MB per 100 seconds

            credits.append(CreditRecord(
                offset=offset,
                entity_id_be=eid_be,
                value=value,
                action_byte=action,
                timestamp_approx=timestamp_approx
            ))
            i += 12
        else:
            i += 1

    return credits


def analyze_action_0x08_passive_gold(credits: List[CreditRecord], player_eids: Set[int]) -> Dict:
    """Analyze action 0x08 - expected to be passive gold (equal across players)"""
    action_08 = [c for c in credits if c.action_byte == 0x08 and c.entity_id_be in player_eids]

    per_player = defaultdict(list)
    for c in action_08:
        per_player[c.entity_id_be].append(c.value)

    result = {
        "total_events": len(action_08),
        "per_player_count": {str(eid): len(vals) for eid, vals in per_player.items()},
        "per_player_sum": {str(eid): sum(vals) for eid, vals in per_player.items()},
        "value_distribution": dict(Counter([round(c.value, 2) for c in action_08]).most_common(10)),
        "is_uniform_count": len(set(len(vals) for vals in per_player.values())) == 1,
        "is_uniform_sum": len(set(round(sum(vals), 0) for vals in per_player.values())) <= 2  # Allow rounding diff
    }

    return result


def find_simultaneous_credits(credits: List[CreditRecord], action_byte: int,
                               player_eids: Set[int], window_bytes: int = 100) -> List[List[CreditRecord]]:
    """Find clusters of same-action credits occurring within a byte window (simultaneous events)"""
    action_credits = [c for c in credits if c.action_byte == action_byte and c.entity_id_be in player_eids]
    action_credits.sort(key=lambda c: c.offset)

    clusters = []
    current_cluster = []

    for c in action_credits:
        if not current_cluster:
            current_cluster.append(c)
        elif c.offset - current_cluster[-1].offset <= window_bytes:
            current_cluster.append(c)
        else:
            if len(current_cluster) >= 2:  # Only keep clusters with 2+ players
                clusters.append(current_cluster)
            current_cluster = [c]

    if len(current_cluster) >= 2:
        clusters.append(current_cluster)

    return clusters


def analyze_action_0x0F_minion_gold(credits: List[CreditRecord], player_eids: Set[int]) -> Dict:
    """Analyze action 0x0F - expected to be minion gold (shared among nearby teammates)"""
    clusters = find_simultaneous_credits(credits, 0x0F, player_eids, window_bytes=100)

    cluster_sizes = Counter([len(c) for c in clusters])

    # Sample clusters
    sample_clusters = []
    for cluster in clusters[:10]:  # First 10 clusters
        sample_clusters.append({
            "offset_range": f"{cluster[0].offset}-{cluster[-1].offset}",
            "player_count": len(cluster),
            "entity_ids": [c.entity_id_be for c in cluster],
            "values": [round(c.value, 2) for c in cluster]
        })

    result = {
        "total_events": len([c for c in credits if c.action_byte == 0x0F and c.entity_id_be in player_eids]),
        "simultaneous_clusters": len(clusters),
        "cluster_size_distribution": dict(cluster_sizes),
        "sharing_detected": len([c for c in clusters if len(c) >= 2]) > 0,
        "sample_clusters": sample_clusters
    }

    return result


def analyze_action_0x0D_jungle_gold(credits: List[CreditRecord], player_eids: Set[int]) -> Dict:
    """Analyze action 0x0D - expected to be jungle gold (single recipient)"""
    clusters = find_simultaneous_credits(credits, 0x0D, player_eids, window_bytes=100)

    cluster_sizes = Counter([len(c) for c in clusters])

    result = {
        "total_events": len([c for c in credits if c.action_byte == 0x0D and c.entity_id_be in player_eids]),
        "simultaneous_clusters": len(clusters),
        "cluster_size_distribution": dict(cluster_sizes),
        "isolated_events": cluster_sizes.get(1, 0),
        "sharing_detected": len([c for c in clusters if len(c) >= 2]) > 0
    }

    return result


def analyze_action_0x02_xp_candidate(credits: List[CreditRecord], player_eids: Set[int]) -> Dict:
    """Analyze action 0x02 - XP candidate (check for sharing pattern)"""
    action_02 = [c for c in credits if c.action_byte == 0x02 and c.entity_id_be in player_eids]

    clusters = find_simultaneous_credits(credits, 0x02, player_eids, window_bytes=100)
    cluster_sizes = Counter([len(c) for c in clusters])

    value_dist = Counter([round(c.value, 2) for c in action_02])

    result = {
        "total_events": len(action_02),
        "simultaneous_clusters": len(clusters),
        "cluster_size_distribution": dict(cluster_sizes),
        "value_range": f"{min(c.value for c in action_02):.2f}-{max(c.value for c in action_02):.2f}" if action_02 else "N/A",
        "value_distribution": dict(value_dist.most_common(15)),
        "sharing_detected": len([c for c in clusters if len(c) >= 2]) > 0
    }

    return result


def analyze_action_0x03_mystery(credits: List[CreditRecord], player_eids: Set[int]) -> Dict:
    """Analyze action 0x03 - always 1.0, purpose unknown"""
    action_03 = [c for c in credits if c.action_byte == 0x03 and c.entity_id_be in player_eids]

    # Check temporal correlation with other events
    # Look for 0x0E (minion kill count) and 0x0F (minion gold) nearby
    temporal_correlation = []

    for c in action_03[:20]:  # Sample first 20
        # Check ±200 bytes window
        nearby_0E = len([cr for cr in credits
                        if cr.action_byte == 0x0E
                        and abs(cr.offset - c.offset) <= 200
                        and cr.entity_id_be == c.entity_id_be])
        nearby_0F = len([cr for cr in credits
                        if cr.action_byte == 0x0F
                        and abs(cr.offset - c.offset) <= 200
                        and cr.entity_id_be == c.entity_id_be])
        nearby_0D = len([cr for cr in credits
                        if cr.action_byte == 0x0D
                        and abs(cr.offset - c.offset) <= 200
                        and cr.entity_id_be == c.entity_id_be])

        temporal_correlation.append({
            "offset": c.offset,
            "nearby_0x0E": nearby_0E,
            "nearby_0x0F": nearby_0F,
            "nearby_0x0D": nearby_0D
        })

    value_dist = Counter([round(c.value, 2) for c in action_03])

    result = {
        "total_events": len(action_03),
        "value_distribution": dict(value_dist),
        "temporal_correlation_sample": temporal_correlation
    }

    return result


def analyze_all_action_bytes(credits: List[CreditRecord], player_eids: Set[int]) -> Dict:
    """Overview of all action bytes"""
    action_counts = Counter([c.action_byte for c in credits if c.entity_id_be in player_eids])

    result = {
        "total_player_credits": len([c for c in credits if c.entity_id_be in player_eids]),
        "action_byte_distribution": {f"0x{ab:02X}": count for ab, count in action_counts.most_common()}
    }

    return result


def main():
    # Load first replay from tournament truth
    truth_path = Path(__file__).parent.parent / "output" / "tournament_truth.json"
    with open(truth_path) as f:
        truth_data = json.load(f)

    # Use first match
    match = truth_data['matches'][0]
    replay_path = Path(match['replay_file'])

    print(f"[OBJECTIVE] Analyze credit record action byte patterns to identify game mechanics")
    print(f"[DATA] Analyzing: {replay_path.name}")
    print(f"[DATA] Match duration: {match['match_info']['duration_seconds']}s")
    print()

    # Load replay and extract player entity IDs
    decoder = UnifiedDecoder(str(replay_path))
    decoded = decoder.decode()

    player_eids_be = {_le_to_be(p.entity_id) for p in decoded.all_players}
    print(f"[DATA] Player entity IDs (BE): {sorted(player_eids_be)}")
    print()

    # Load binary data
    with open(replay_path, 'rb') as f:
        data = f.read()

    print(f"[DATA] Replay file size: {len(data):,} bytes")

    # Extract all credits
    all_credits = extract_all_credits(data)
    print(f"[DATA] Total credit records: {len(all_credits):,}")
    print()

    # ===== ANALYSIS =====

    print("=" * 80)
    print("ACTION BYTE OVERVIEW")
    print("=" * 80)
    overview = analyze_all_action_bytes(all_credits, player_eids_be)
    print(json.dumps(overview, indent=2))
    print()

    print("=" * 80)
    print("ACTION 0x08 - PASSIVE GOLD (Expected: Equal distribution)")
    print("=" * 80)
    result_08 = analyze_action_0x08_passive_gold(all_credits, player_eids_be)
    print(json.dumps(result_08, indent=2))
    print()
    print(f"[FINDING] Action 0x08 uniform count: {result_08['is_uniform_count']}")
    print(f"[FINDING] Action 0x08 uniform sum: {result_08['is_uniform_sum']}")
    print()

    print("=" * 80)
    print("ACTION 0x0F - MINION GOLD (Expected: Shared distribution)")
    print("=" * 80)
    result_0F = analyze_action_0x0F_minion_gold(all_credits, player_eids_be)
    print(json.dumps(result_0F, indent=2))
    print()
    print(f"[FINDING] Action 0x0F sharing detected: {result_0F['sharing_detected']}")
    print(f"[FINDING] Action 0x0F simultaneous clusters: {result_0F['simultaneous_clusters']}")
    print()

    print("=" * 80)
    print("ACTION 0x0D - JUNGLE GOLD (Expected: Isolated/single recipient)")
    print("=" * 80)
    result_0D = analyze_action_0x0D_jungle_gold(all_credits, player_eids_be)
    print(json.dumps(result_0D, indent=2))
    print()
    print(f"[FINDING] Action 0x0D sharing detected: {result_0D['sharing_detected']}")
    print(f"[FINDING] Action 0x0D isolated events: {result_0D['isolated_events']}/{result_0D['total_events']}")
    print()

    print("=" * 80)
    print("ACTION 0x02 - XP CANDIDATE (Testing: Shared distribution?)")
    print("=" * 80)
    result_02 = analyze_action_0x02_xp_candidate(all_credits, player_eids_be)
    print(json.dumps(result_02, indent=2))
    print()
    print(f"[FINDING] Action 0x02 sharing detected: {result_02['sharing_detected']}")
    print(f"[FINDING] Action 0x02 value range: {result_02['value_range']}")
    print()

    print("=" * 80)
    print("ACTION 0x03 - MYSTERY (Always 1.0)")
    print("=" * 80)
    result_03 = analyze_action_0x03_mystery(all_credits, player_eids_be)
    print(json.dumps(result_03, indent=2))
    print()

    # ===== SUMMARY =====
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)

    print(f"[STAT:total_credits] {len(all_credits):,}")
    print(f"[STAT:action_0x08_events] {result_08['total_events']}")
    print(f"[STAT:action_0x0F_events] {result_0F['total_events']}")
    print(f"[STAT:action_0x0D_events] {result_0D['total_events']}")
    print(f"[STAT:action_0x02_events] {result_02['total_events']}")
    print(f"[STAT:action_0x03_events] {result_03['total_events']}")
    print()

    print("[LIMITATION] Timestamp approximation is very rough (based on byte offset)")
    print("[LIMITATION] Window size for 'simultaneous' detection is heuristic (100 bytes)")
    print("[LIMITATION] Single match analyzed - patterns should be validated across multiple matches")


if __name__ == '__main__':
    main()
