#!/usr/bin/env python3
"""
Time-based Cluster Analysis - Phase 2.2
같은 프레임에서 발생하는 이벤트 클러스터 분석
킬러-피해자 관계 탐색
"""

import json
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any, Tuple, Set

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'core'))
from vgr_parser import VGRParser


def load_truth_data() -> Dict:
    """Load tournament truth data."""
    truth_path = Path(__file__).parent.parent / 'output' / 'tournament_truth.json'
    with open(truth_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def extract_all_events_by_frame(replay_dir: Path, replay_name: str,
                                  entity_ids: Set[int]) -> Dict[int, List[Dict]]:
    """Extract all events for given entities, grouped by frame."""
    events_by_frame = defaultdict(list)

    frame_files = sorted(replay_dir.glob(f"{replay_name}.*.vgr"),
                        key=lambda p: int(p.stem.split('.')[-1]))

    for frame_path in frame_files:
        frame_num = int(frame_path.stem.split('.')[-1])
        data = frame_path.read_bytes()

        for entity_id in entity_ids:
            entity_bytes = entity_id.to_bytes(2, 'little')
            pattern = entity_bytes + b'\x00\x00'
            idx = 0

            while True:
                idx = data.find(pattern, idx)
                if idx == -1:
                    break

                if idx + 36 <= len(data):
                    action = data[idx + 4]
                    payload = data[idx + 5:idx + 36]

                    # Check for other entity IDs in payload
                    related_entities = []
                    for other_id in entity_ids:
                        if other_id == entity_id:
                            continue
                        other_bytes = other_id.to_bytes(2, 'little')
                        pos = payload.find(other_bytes)
                        if pos != -1:
                            related_entities.append({
                                'entity_id': other_id,
                                'offset': pos
                            })

                    events_by_frame[frame_num].append({
                        'entity_id': entity_id,
                        'action': action,
                        'payload': payload.hex(),
                        'related_entities': related_entities
                    })
                idx += 1

    return events_by_frame


def find_death_clusters(events_by_frame: Dict[int, List[Dict]],
                        entity_to_info: Dict[int, Dict]) -> List[Dict]:
    """
    Find clusters of events that might indicate death.
    Look for frames where:
    1. Multiple entities have related events
    2. Cross-team interactions occur
    """
    clusters = []

    for frame, events in events_by_frame.items():
        # Group events by action code
        by_action = defaultdict(list)
        for e in events:
            by_action[e['action']].append(e)

        # Find events with cross-team entity references
        for action, action_events in by_action.items():
            for e in action_events:
                if not e['related_entities']:
                    continue

                source_info = entity_to_info.get(e['entity_id'], {})
                source_team = source_info.get('team')

                for rel in e['related_entities']:
                    target_info = entity_to_info.get(rel['entity_id'], {})
                    target_team = target_info.get('team')

                    if source_team and target_team and source_team != target_team:
                        clusters.append({
                            'frame': frame,
                            'action': action,
                            'source_entity': e['entity_id'],
                            'source_name': source_info.get('name'),
                            'source_team': source_team,
                            'target_entity': rel['entity_id'],
                            'target_name': target_info.get('name'),
                            'target_team': target_team,
                            'target_offset': rel['offset']
                        })

    return clusters


def analyze_0x44_pattern(replay_dir: Path, replay_name: str,
                          entity_to_info: Dict[int, Dict]) -> Dict[str, Any]:
    """
    Specifically analyze 0x44 events with offset 11 killer pattern.
    """
    results = {
        'events': [],
        'kill_candidates': defaultdict(lambda: defaultdict(int))
    }

    entity_ids = set(entity_to_info.keys())

    frame_files = sorted(replay_dir.glob(f"{replay_name}.*.vgr"),
                        key=lambda p: int(p.stem.split('.')[-1]))

    for frame_path in frame_files:
        frame_num = int(frame_path.stem.split('.')[-1])
        data = frame_path.read_bytes()

        for entity_id in entity_ids:
            entity_bytes = entity_id.to_bytes(2, 'little')
            pattern = entity_bytes + b'\x00\x00'
            idx = 0

            while True:
                idx = data.find(pattern, idx)
                if idx == -1:
                    break

                if idx + 36 <= len(data):
                    action = data[idx + 4]

                    if action == 0x44:
                        payload = data[idx + 5:idx + 36]

                        # Check offset 11 for killer entity
                        if len(payload) > 12:
                            potential_killer = payload[11] | (payload[12] << 8)

                            if potential_killer in entity_ids:
                                victim_info = entity_to_info.get(entity_id, {})
                                killer_info = entity_to_info.get(potential_killer, {})

                                # Check if cross-team
                                if (victim_info.get('team') and killer_info.get('team') and
                                    victim_info.get('team') != killer_info.get('team')):

                                    results['events'].append({
                                        'frame': frame_num,
                                        'victim': victim_info.get('name'),
                                        'victim_entity': entity_id,
                                        'killer': killer_info.get('name'),
                                        'killer_entity': potential_killer,
                                        'payload': payload.hex()
                                    })

                                    # Count kills per player
                                    killer_name = killer_info.get('name', 'unknown')
                                    victim_name = victim_info.get('name', 'unknown')
                                    results['kill_candidates'][killer_name][victim_name] += 1

                idx += 1

    return results


def main():
    print("=" * 60)
    print("Time-based Cluster Analysis")
    print("=" * 60)
    print()

    truth = load_truth_data()

    # Analyze first few matches in detail
    total_0x44_kills = defaultdict(lambda: {'detected': 0, 'truth': 0})

    for match_idx, match in enumerate(truth['matches'][:5]):  # First 5 matches
        replay_file = match['replay_file']
        replay_dir = Path(replay_file).parent
        replay_name = match['replay_name']

        print(f"\n{'=' * 60}")
        print(f"Match {match_idx + 1}: {replay_name[:40]}...")
        print(f"{'=' * 60}")

        # Parse replay to get entity IDs
        parser = VGRParser(replay_file, auto_truth=False)
        parsed = parser.parse()

        # Build entity mapping
        entity_to_info = {}
        for team in ('left', 'right'):
            for player in parsed['teams'][team]:
                entity_id = player.get('entity_id')
                player_name = player['name']
                truth_player = match['players'].get(player_name, {})

                if entity_id:
                    entity_to_info[entity_id] = {
                        'name': player_name,
                        'team': team,
                        'kills': truth_player.get('kills', 0),
                        'deaths': truth_player.get('deaths', 0),
                        'assists': truth_player.get('assists', 0)
                    }

        print(f"\nPlayers: {len(entity_to_info)}")

        # Analyze 0x44 pattern specifically
        print("\n--- 0x44 Analysis (offset 11 = killer) ---")
        result_0x44 = analyze_0x44_pattern(replay_dir, replay_name, entity_to_info)

        print(f"Found {len(result_0x44['events'])} cross-team 0x44 events")

        if result_0x44['events']:
            print("\nSample events:")
            for e in result_0x44['events'][:5]:
                print(f"  Frame {e['frame']}: {e['killer']} -> {e['victim']}")

        # Compare detected kills vs truth
        print("\n--- Kill Count Comparison ---")
        print(f"{'Player':<20} {'Detected':>10} {'Truth':>10} {'Match':>10}")
        print("-" * 55)

        for entity_id, info in entity_to_info.items():
            player_name = info['name']
            detected = sum(result_0x44['kill_candidates'].get(player_name, {}).values())
            truth_kills = info['kills']

            match_str = "OK" if detected == truth_kills else f"DIFF({detected - truth_kills:+d})"
            print(f"{player_name:<20} {detected:>10} {truth_kills:>10} {match_str:>10}")

            total_0x44_kills[player_name]['detected'] += detected
            total_0x44_kills[player_name]['truth'] += truth_kills

        # General cluster analysis
        print("\n--- Cross-team Event Clusters ---")
        events_by_frame = extract_all_events_by_frame(replay_dir, replay_name, set(entity_to_info.keys()))
        clusters = find_death_clusters(events_by_frame, entity_to_info)

        # Count by action code
        action_counts = defaultdict(int)
        for c in clusters:
            action_counts[c['action']] += 1

        print("Action codes with cross-team entity references:")
        for action, count in sorted(action_counts.items(), key=lambda x: -x[1])[:10]:
            print(f"  0x{action:02X}: {count} occurrences")

    # Overall summary
    print("\n" + "=" * 60)
    print("Overall 0x44 Kill Detection Summary (5 matches)")
    print("=" * 60)

    total_detected = 0
    total_truth = 0
    exact_matches = 0

    for player, counts in total_0x44_kills.items():
        total_detected += counts['detected']
        total_truth += counts['truth']
        if counts['detected'] == counts['truth']:
            exact_matches += 1

    print(f"Total detected: {total_detected}")
    print(f"Total truth: {total_truth}")
    print(f"Exact matches: {exact_matches}/{len(total_0x44_kills)} players")

    if total_truth > 0:
        accuracy = total_detected / total_truth * 100
        print(f"Detection rate: {accuracy:.1f}%")


if __name__ == "__main__":
    main()
