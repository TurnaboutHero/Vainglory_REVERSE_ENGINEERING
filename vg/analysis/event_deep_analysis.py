#!/usr/bin/env python3
"""
Deep event analysis for Vainglory replays.
Extracts event sequences with timestamps and payload analysis.
"""

import argparse
import json
from pathlib import Path
from typing import Dict, Any, List, Tuple
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict

from vgr_parser import VGRParser


@dataclass
class EventRecord:
    """Single event record with full context."""
    frame: int
    offset: int
    entity_id: int
    action: int
    action_hex: str
    payload: bytes
    payload_hex: str

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['payload'] = list(self.payload)
        return d


def extract_events_from_frame(data: bytes, frame_num: int, entity_ids: List[int]) -> List[EventRecord]:
    """
    Extract all events for given entity IDs from a single frame.
    Pattern: [EntityID(2B LE)][00 00][Action(1B)][Payload...]
    """
    events = []

    for entity_id in entity_ids:
        base = entity_id.to_bytes(2, 'little') + b'\x00\x00'
        idx = 0

        while True:
            idx = data.find(base, idx)
            if idx == -1:
                break

            if idx + 5 <= len(data):
                action = data[idx + 4]
                # Extract payload (next 20 bytes or until end)
                payload_end = min(idx + 25, len(data))
                payload = data[idx + 5:payload_end]

                events.append(EventRecord(
                    frame=frame_num,
                    offset=idx,
                    entity_id=entity_id,
                    action=action,
                    action_hex=f"0x{action:02X}",
                    payload=payload,
                    payload_hex=payload.hex()
                ))

            idx += 1

    return events


def analyze_action_context(events: List[EventRecord]) -> Dict[str, Any]:
    """
    Analyze the context around each action type.
    Look for patterns in payload bytes.
    """
    action_contexts = defaultdict(list)

    for event in events:
        action_contexts[event.action_hex].append({
            'frame': event.frame,
            'offset': event.offset,
            'payload_first_4': list(event.payload[:4]) if len(event.payload) >= 4 else list(event.payload),
            'payload_hex': event.payload_hex[:16]  # First 8 bytes
        })

    # Summarize each action
    summary = {}
    for action, contexts in action_contexts.items():
        # Find common payload patterns
        first_bytes = Counter(tuple(c['payload_first_4']) for c in contexts)

        summary[action] = {
            'count': len(contexts),
            'frames': sorted(set(c['frame'] for c in contexts)),
            'common_payload_start': [
                {'bytes': list(pattern), 'count': count}
                for pattern, count in first_bytes.most_common(3)
            ],
            'samples': contexts[:5]  # First 5 samples
        }

    return summary


def find_entity_interactions(events: List[EventRecord], all_entity_ids: List[int]) -> List[Dict]:
    """
    Look for other entity IDs in event payloads.
    This might reveal killer/victim relationships.
    """
    interactions = []

    for event in events:
        payload = event.payload

        # Look for other entity IDs in payload
        for other_id in all_entity_ids:
            if other_id == event.entity_id:
                continue

            other_bytes = other_id.to_bytes(2, 'little')
            if other_bytes in payload:
                pos = payload.find(other_bytes)
                interactions.append({
                    'frame': event.frame,
                    'source_entity': event.entity_id,
                    'action': event.action_hex,
                    'target_entity': other_id,
                    'target_offset_in_payload': pos,
                    'full_payload': event.payload_hex
                })

    return interactions


def analyze_frame_sequence(replay_dir: Path, replay_name: str, entity_ids: List[int]) -> Dict[str, Any]:
    """
    Analyze events across all frames in sequence.
    """
    frames = sorted(replay_dir.glob(f"{replay_name}.*.vgr"),
                   key=lambda p: int(p.stem.split('.')[-1]))

    all_events = []
    frame_summaries = []

    for frame_path in frames:
        frame_num = int(frame_path.stem.split('.')[-1])
        data = frame_path.read_bytes()

        events = extract_events_from_frame(data, frame_num, entity_ids)
        all_events.extend(events)

        # Frame summary
        action_counts = Counter(e.action_hex for e in events)
        frame_summaries.append({
            'frame': frame_num,
            'file_size': len(data),
            'event_count': len(events),
            'action_counts': dict(action_counts)
        })

    # Overall analysis
    action_context = analyze_action_context(all_events)
    interactions = find_entity_interactions(all_events, entity_ids)

    return {
        'replay_name': replay_name,
        'total_frames': len(frames),
        'total_events': len(all_events),
        'entity_ids': entity_ids,
        'frame_summaries': frame_summaries,
        'action_context': action_context,
        'entity_interactions': interactions,
        'events_timeline': [e.to_dict() for e in all_events[:100]]  # First 100 events
    }


def summarize_interactions(interactions: List[Dict], entity_to_name: Dict[int, str]) -> Dict[str, Any]:
    """
    Summarize entity interactions by player and action type.
    """
    # Count interactions by (source, target, action)
    interaction_counts = Counter()
    for inter in interactions:
        src = inter['source_entity']
        tgt = inter['target_entity']
        act = inter['action']
        interaction_counts[(src, tgt, act)] += 1

    # Group by source player
    by_source = defaultdict(list)
    for (src, tgt, act), count in interaction_counts.items():
        src_name = entity_to_name.get(src, f"Entity_{src}")
        tgt_name = entity_to_name.get(tgt, f"Entity_{tgt}")
        by_source[src_name].append({
            "target": tgt_name,
            "target_id": tgt,
            "action": act,
            "count": count
        })

    # Sort each player's interactions by count
    for name in by_source:
        by_source[name].sort(key=lambda x: -x['count'])

    # Group by target player (who received the interaction)
    by_target = defaultdict(list)
    for (src, tgt, act), count in interaction_counts.items():
        src_name = entity_to_name.get(src, f"Entity_{src}")
        tgt_name = entity_to_name.get(tgt, f"Entity_{tgt}")
        by_target[tgt_name].append({
            "source": src_name,
            "source_id": src,
            "action": act,
            "count": count
        })

    for name in by_target:
        by_target[name].sort(key=lambda x: -x['count'])

    return {
        "by_source": dict(by_source),
        "by_target": dict(by_target),
        "total_interactions": len(interactions)
    }


def load_truth_data(truth_path: str, replay_name: str) -> Dict[str, Dict[str, Any]]:
    """
    Load truth data for a specific replay.
    Returns dict mapping player name to their stats.
    """
    with open(truth_path, 'r', encoding='utf-8') as f:
        truth = json.load(f)

    for match in truth.get('matches', []):
        if match.get('replay_name') == replay_name:
            return match.get('players', {})

    return {}


def correlate_interactions_with_kda(
    interactions: List[Dict],
    entity_to_name: Dict[int, str],
    truth_players: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Correlate entity interactions with K/D/A from truth data.
    Look for patterns that might indicate kills/deaths.
    """
    # Build team mapping
    player_team = {}
    for player_name, stats in truth_players.items():
        player_team[player_name] = stats.get('team', 'unknown')

    # Count outgoing and incoming interactions per player
    # Separate by same-team (friendly) vs cross-team (hostile)
    outgoing_by_player = defaultdict(lambda: defaultdict(int))  # player -> action -> count
    incoming_by_player = defaultdict(lambda: defaultdict(int))  # player -> action -> count
    outgoing_hostile = defaultdict(lambda: defaultdict(int))    # cross-team only
    incoming_hostile = defaultdict(lambda: defaultdict(int))    # cross-team only

    for inter in interactions:
        src_name = entity_to_name.get(inter['source_entity'], f"Entity_{inter['source_entity']}")
        tgt_name = entity_to_name.get(inter['target_entity'], f"Entity_{inter['target_entity']}")
        action = inter['action']

        outgoing_by_player[src_name][action] += 1
        incoming_by_player[tgt_name][action] += 1

        # Track cross-team interactions (hostile)
        src_team = player_team.get(src_name)
        tgt_team = player_team.get(tgt_name)
        if src_team and tgt_team and src_team != tgt_team:
            outgoing_hostile[src_name][action] += 1
            incoming_hostile[tgt_name][action] += 1

    # Build correlation table
    correlation_data = []
    for player_name, stats in truth_players.items():
        kills = stats.get('kills', 0)
        deaths = stats.get('deaths', 0)
        assists = stats.get('assists', 0)

        outgoing = dict(outgoing_by_player.get(player_name, {}))
        incoming = dict(incoming_by_player.get(player_name, {}))
        out_hostile = dict(outgoing_hostile.get(player_name, {}))
        in_hostile = dict(incoming_hostile.get(player_name, {}))

        correlation_data.append({
            'player': player_name,
            'team': player_team.get(player_name, 'unknown'),
            'kills': kills,
            'deaths': deaths,
            'assists': assists,
            'outgoing_interactions': outgoing,
            'incoming_interactions': incoming,
            'outgoing_hostile': out_hostile,
            'incoming_hostile': in_hostile,
            'total_outgoing': sum(outgoing.values()),
            'total_incoming': sum(incoming.values()),
            'total_outgoing_hostile': sum(out_hostile.values()),
            'total_incoming_hostile': sum(in_hostile.values())
        })

    # Look for specific action codes that might correlate with K/D/A
    action_correlations = defaultdict(lambda: {'kills': [], 'deaths': [], 'assists': []})

    for data in correlation_data:
        # Check outgoing interactions vs kills
        for action, count in data['outgoing_interactions'].items():
            action_correlations[f"outgoing_{action}"]['kills'].append((count, data['kills']))
            action_correlations[f"outgoing_{action}"]['deaths'].append((count, data['deaths']))
            action_correlations[f"outgoing_{action}"]['assists'].append((count, data['assists']))

        # Check incoming interactions vs deaths
        for action, count in data['incoming_interactions'].items():
            action_correlations[f"incoming_{action}"]['kills'].append((count, data['kills']))
            action_correlations[f"incoming_{action}"]['deaths'].append((count, data['deaths']))
            action_correlations[f"incoming_{action}"]['assists'].append((count, data['assists']))

        # Check HOSTILE (cross-team) outgoing vs kills - key hypothesis!
        for action, count in data['outgoing_hostile'].items():
            action_correlations[f"hostile_out_{action}"]['kills'].append((count, data['kills']))
            action_correlations[f"hostile_out_{action}"]['assists'].append((count, data['assists']))

        # Check HOSTILE incoming vs deaths - key hypothesis!
        for action, count in data['incoming_hostile'].items():
            action_correlations[f"hostile_in_{action}"]['deaths'].append((count, data['deaths']))

    # Calculate simple correlation (ratio analysis)
    action_analysis = {}
    for action_key, stat_data in action_correlations.items():
        analysis = {}
        for stat_name, pairs in stat_data.items():
            if pairs and len(pairs) >= 2:
                counts = [p[0] for p in pairs]
                stats = [p[1] for p in pairs]

                # Check if counts match stats
                matches = sum(1 for c, s in pairs if c == s)
                close_matches = sum(1 for c, s in pairs if abs(c - s) <= 1)

                analysis[stat_name] = {
                    'exact_matches': matches,
                    'close_matches': close_matches,
                    'total_samples': len(pairs),
                    'avg_count': sum(counts) / len(counts) if counts else 0,
                    'avg_stat': sum(stats) / len(stats) if stats else 0,
                    'sample_pairs': pairs[:5]  # First 5 samples
                }

        if analysis:
            action_analysis[action_key] = analysis

    return {
        'player_data': correlation_data,
        'action_analysis': action_analysis
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Deep event analysis for VGR replays")
    parser.add_argument("path", help="Replay folder containing .vgr files")
    parser.add_argument("--output", default="deep_analysis.json", help="Output JSON path")
    parser.add_argument("--entity", type=int, action='append', help="Entity ID to analyze (can specify multiple)")
    parser.add_argument("--truth", help="Truth JSON path (optional)")
    args = parser.parse_args()

    replay_dir = Path(args.path)

    # Find replay name from first .0.vgr file
    vgr_files = list(replay_dir.glob("*.0.vgr"))
    if not vgr_files:
        print("No .0.vgr file found")
        return 1

    replay_name = vgr_files[0].stem.rsplit('.', 1)[0]
    print(f"Analyzing replay: {replay_name}")

    # Parse replay to get entity IDs and player names
    parser_obj = VGRParser(str(vgr_files[0]), auto_truth=False)
    parsed = parser_obj.parse()

    entity_to_name = {}
    if args.entity:
        entity_ids = args.entity
    else:
        entity_ids = []
        for team in ('left', 'right'):
            for player in parsed['teams'][team]:
                if player.get('entity_id'):
                    entity_ids.append(player['entity_id'])
                    entity_to_name[player['entity_id']] = player['name']
        print(f"Found entity IDs: {entity_ids}")

    if not entity_ids:
        print("No entity IDs found")
        return 1

    # Run analysis
    result = analyze_frame_sequence(replay_dir, replay_name, entity_ids)

    # Print summary
    print(f"\n=== Deep Analysis Summary ===")
    print(f"Total frames: {result['total_frames']}")
    print(f"Total events: {result['total_events']}")
    print(f"\nAction types found:")
    for action, ctx in sorted(result['action_context'].items(), key=lambda x: -x[1]['count']):
        print(f"  {action}: {ctx['count']} times across frames {ctx['frames']}")

    if result['entity_interactions']:
        print(f"\nEntity interactions found: {len(result['entity_interactions'])}")
        for inter in result['entity_interactions'][:5]:
            src_name = entity_to_name.get(inter['source_entity'], str(inter['source_entity']))
            tgt_name = entity_to_name.get(inter['target_entity'], str(inter['target_entity']))
            print(f"  Frame {inter['frame']}: {src_name} -> {tgt_name} (action {inter['action']})")

        # Add interaction summary
        result['interaction_summary'] = summarize_interactions(
            result['entity_interactions'], entity_to_name
        )

        print(f"\n=== Interaction Summary by Player ===")
        for player, targets in result['interaction_summary']['by_source'].items():
            total = sum(t['count'] for t in targets)
            print(f"  {player}: {total} outgoing interactions")
            for t in targets[:3]:
                print(f"    -> {t['target']} ({t['action']}): {t['count']}x")

    # Load truth data if provided
    truth_players = {}
    if args.truth:
        truth_players = load_truth_data(args.truth, replay_name)
        if truth_players:
            print(f"\nLoaded truth data for {len(truth_players)} players")

            # Correlate interactions with K/D/A
            if result['entity_interactions']:
                kda_correlation = correlate_interactions_with_kda(
                    result['entity_interactions'],
                    entity_to_name,
                    truth_players
                )
                result['kda_correlation'] = kda_correlation

                # Print correlation analysis
                print(f"\n=== K/D/A Correlation Analysis ===")
                print(f"Player interaction data (hostile = cross-team only):")
                for pdata in kda_correlation['player_data']:
                    print(f"  {pdata['player']} [{pdata['team']}]: K={pdata['kills']} D={pdata['deaths']} A={pdata['assists']}")
                    print(f"    Hostile OUT: {pdata['outgoing_hostile']}")
                    print(f"    Hostile IN:  {pdata['incoming_hostile']}")

                # Find best correlating actions
                print(f"\n=== Best Correlating Actions ===")
                for action_key, analysis in kda_correlation['action_analysis'].items():
                    for stat, data in analysis.items():
                        if data['exact_matches'] > 0 or data['close_matches'] >= data['total_samples'] // 2:
                            print(f"  {action_key} -> {stat}: "
                                  f"{data['exact_matches']}/{data['total_samples']} exact, "
                                  f"{data['close_matches']}/{data['total_samples']} close")
        else:
            print(f"\nWarning: No truth data found for replay {replay_name}")

    # Add truth data if available
    result['players_info'] = []
    for team in ('left', 'right'):
        for player in parsed['teams'][team]:
            player_truth = truth_players.get(player['name'], {})
            result['players_info'].append({
                'name': player['name'],
                'team': team,
                'entity_id': player.get('entity_id'),
                'kills': player_truth.get('kills', player.get('kills', 0)),
                'deaths': player_truth.get('deaths', player.get('deaths', 0)),
                'assists': player_truth.get('assists', player.get('assists', 0))
            })

    # Save results
    Path(args.output).write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(f"\nWrote detailed results to {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
