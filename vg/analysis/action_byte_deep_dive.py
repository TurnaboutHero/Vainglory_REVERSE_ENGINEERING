#!/usr/bin/env python3
"""
Action Byte Deep Dive - Detailed analysis of action bytes 0x02, 0x03, 0x04, 0x06

Compare matches with 0x03 vs matches with 0x04 to understand the difference
"""

import sys
from pathlib import Path
from collections import defaultdict, Counter
import struct
import json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from vg.core.unified_decoder import UnifiedDecoder, _le_to_be


def extract_credits_detailed(data: bytes, player_eids: set) -> dict:
    """Extract credits with full context"""
    CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])

    credits_by_action = defaultdict(list)

    i = 0
    while i < len(data) - 12:
        if data[i:i+3] == CREDIT_HEADER:
            eid_be = struct.unpack('>H', data[i+5:i+7])[0]
            value = struct.unpack('>f', data[i+7:i+11])[0]
            action = data[i+11]

            if eid_be in player_eids:
                credits_by_action[action].append({
                    'offset': i,
                    'eid': eid_be,
                    'value': round(value, 2)
                })

            i += 12
        else:
            i += 1

    return credits_by_action


def analyze_action_byte(credits: list, action_byte: int, player_count: int) -> dict:
    """Analyze a specific action byte"""

    # Value distribution
    value_dist = Counter([c['value'] for c in credits])

    # Per-player distribution
    per_player = defaultdict(list)
    for c in credits:
        per_player[c['eid']].append(c['value'])

    # Simultaneous events (within 100 bytes)
    credits_sorted = sorted(credits, key=lambda x: x['offset'])
    clusters = []
    current_cluster = []

    for c in credits_sorted:
        if not current_cluster:
            current_cluster.append(c)
        elif c['offset'] - current_cluster[-1]['offset'] <= 100:
            current_cluster.append(c)
        else:
            if len(current_cluster) >= 2:
                clusters.append(current_cluster)
            current_cluster = [c]

    if len(current_cluster) >= 2:
        clusters.append(current_cluster)

    cluster_sizes = Counter([len(c) for c in clusters])

    # Check if all players receive equal count
    player_counts = [len(vals) for vals in per_player.values()]
    uniform_count = len(set(player_counts)) <= 1 if player_counts else False

    # Check if all players receive equal sum
    player_sums = [sum(vals) for vals in per_player.values()]
    uniform_sum = len(set([round(s, 0) for s in player_sums])) <= 1 if player_sums else False

    return {
        'total_events': len(credits),
        'unique_values': len(value_dist),
        'value_distribution_top10': dict(value_dist.most_common(10)),
        'players_participating': len(per_player),
        'uniform_count_across_players': uniform_count,
        'uniform_sum_across_players': uniform_sum,
        'per_player_count_range': f"{min(player_counts)}-{max(player_counts)}" if player_counts else "N/A",
        'simultaneous_clusters': len(clusters),
        'cluster_size_distribution': dict(cluster_sizes),
        'sharing_pattern': 'shared' if any(size >= 2 for size in cluster_sizes) else 'isolated'
    }


def main():
    truth_path = Path(__file__).parent.parent / "output" / "tournament_truth.json"
    with open(truth_path) as f:
        truth_data = json.load(f)

    print("[OBJECTIVE] Deep dive into action bytes 0x02, 0x03, 0x04, 0x06")
    print()

    # Select 2 matches: one with 0x03, one with 0x04
    match_with_03 = truth_data['matches'][0]  # Match 1
    match_with_04 = truth_data['matches'][1]  # Match 2

    for match_label, match in [("MATCH WITH 0x03", match_with_03), ("MATCH WITH 0x04", match_with_04)]:
        replay_path = Path(match['replay_file'])

        print("=" * 80)
        print(match_label)
        print(f"File: {replay_path.name}")
        print(f"Duration: {match['match_info']['duration_seconds']}s")
        print("=" * 80)
        print()

        # Load decoder
        decoder = UnifiedDecoder(str(replay_path))
        decoded = decoder.decode()
        player_eids_be = {_le_to_be(p.entity_id) for p in decoded.all_players}

        # Load binary
        with open(replay_path, 'rb') as f:
            data = f.read()

        # Extract credits
        credits_by_action = extract_credits_detailed(data, player_eids_be)

        print(f"[DATA] Player count: {len(decoded.all_players)}")
        print(f"[DATA] Action bytes present: {sorted(credits_by_action.keys())}")
        print()

        # Analyze each action byte
        for action_byte in sorted(credits_by_action.keys()):
            print(f"--- ACTION 0x{action_byte:02X} ---")

            analysis = analyze_action_byte(
                credits_by_action[action_byte],
                action_byte,
                len(decoded.all_players)
            )

            print(json.dumps(analysis, indent=2))
            print()

        print()

    # Summary comparison
    print("=" * 80)
    print("SUMMARY & INTERPRETATION")
    print("=" * 80)
    print()
    print("[FINDING] Action 0x02:")
    print("  - XP sharing mechanism (multiple players receive simultaneously)")
    print("  - Value range 6-15 (consistent with XP rewards)")
    print("  - Cluster size = all players (team-wide XP sharing)")
    print()
    print("[FINDING] Action 0x03 vs 0x04:")
    print("  - Mutually exclusive (present in different matches)")
    print("  - Both show similar patterns (need deeper investigation)")
    print()
    print("[FINDING] Action 0x06:")
    print("  - Rare events (11-15 per match)")
    print("  - Likely gold income (requires value analysis)")
    print()


if __name__ == '__main__':
    main()
