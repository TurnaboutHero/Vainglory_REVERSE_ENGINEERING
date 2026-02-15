#!/usr/bin/env python3
"""
Deep Payload Analyzer - Comprehensive analysis of VGR event payloads

Findings so far:
- Event structure: [EntityID 2B LE][00 00][ActionCode 1B][Payload ?B]
- Payload size varies by action code
- Cross-team entity IDs appear at distance 6, 24, 28, 40 bytes
- Need to determine actual payload sizes and find entity references within payloads
"""

import struct
import json
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Tuple, Any
import numpy as np


class DeepPayloadAnalyzer:
    """Comprehensive payload structure analysis"""

    # Team composition for 21.11.04
    TEAM_1 = {'Phinn': 56325, 'Yates': 56581, 'Caine': 56837}
    TEAM_2 = {'Petal': 57093, 'Karas': 57349, 'Baron': 57605}
    ALL_ENTITY_IDS = list(TEAM_1.values()) + list(TEAM_2.values())

    def __init__(self, cache_dir: str):
        self.cache_dir = Path(cache_dir)

    def load_frames(self, max_frames: int = 30) -> bytes:
        """Load frames"""
        vgr_files = sorted(self.cache_dir.glob("*.vgr"), key=lambda p: self._frame_index(p))
        data_chunks = []
        for frame_file in vgr_files[:max_frames]:
            with open(frame_file, 'rb') as f:
                data_chunks.append(f.read())
        combined = b''.join(data_chunks)
        print(f"[DATA] Loaded {len(data_chunks)} frames, total {len(combined):,} bytes")
        return combined

    @staticmethod
    def _frame_index(path: Path) -> int:
        try:
            return int(path.stem.split('.')[-1])
        except ValueError:
            return 0

    def determine_payload_sizes(self, data: bytes) -> Dict[int, List[int]]:
        """Determine payload size for each action code by looking at distances to next entity ID"""
        print(f"\n[STAGE:begin:payload_size_detection]")

        # Find all events [EntityID][00 00][Action]
        events = []
        for entity_id in self.ALL_ENTITY_IDS:
            entity_bytes = entity_id.to_bytes(2, 'little')
            pattern = entity_bytes + b'\x00\x00'

            idx = 0
            while True:
                idx = data.find(pattern, idx)
                if idx == -1:
                    break
                if idx + 5 <= len(data):
                    action = data[idx + 4]
                    events.append({'offset': idx, 'entity_id': entity_id, 'action': action})
                idx += 1

        # Sort by offset
        events.sort(key=lambda e: e['offset'])

        print(f"[FINDING] Found {len(events)} total events")

        # Calculate distances between consecutive events
        action_distances = defaultdict(list)

        for i in range(len(events) - 1):
            curr = events[i]
            next_event = events[i + 1]

            distance = next_event['offset'] - curr['offset']
            action_distances[curr['action']].append(distance)

        # Analyze distance distributions
        payload_sizes = {}

        print(f"\n[FINDING] Payload size analysis by action code:")
        for action in sorted(action_distances.keys()):
            distances = action_distances[action]
            counter = Counter(distances)

            # Most common distance = likely event size
            most_common_distance = counter.most_common(1)[0][0]
            payload_size = most_common_distance - 5  # Subtract header size (2+2+1)

            payload_sizes[action] = payload_size

            print(f"  Action 0x{action:02X}: {len(distances)} samples")
            print(f"    Most common distance: {most_common_distance} bytes")
            print(f"    Implied payload size: {payload_size} bytes")
            print(f"    Distance distribution: {dict(counter.most_common(5))}")

        print(f"[STAGE:status:success]")
        print(f"[STAGE:end:payload_size_detection]")

        return payload_sizes

    def extract_variable_events(self, data: bytes, payload_sizes: Dict[int, int]) -> Dict[int, List]:
        """Extract events with correct payload sizes"""
        print(f"\n[STAGE:begin:variable_event_extraction]")

        events_by_action = defaultdict(list)

        for entity_id in self.ALL_ENTITY_IDS:
            entity_bytes = entity_id.to_bytes(2, 'little')
            pattern = entity_bytes + b'\x00\x00'

            idx = 0
            while True:
                idx = data.find(pattern, idx)
                if idx == -1:
                    break

                if idx + 5 <= len(data):
                    action = data[idx + 4]

                    # Get payload size for this action
                    payload_size = payload_sizes.get(action, 32)  # Default 32 if unknown

                    # Check if we have enough data
                    if idx + 5 + payload_size <= len(data):
                        payload = data[idx + 5:idx + 5 + payload_size]

                        events_by_action[action].append({
                            'entity_id': entity_id,
                            'offset': idx,
                            'payload': payload,
                        })

                idx += 1

        total = sum(len(events) for events in events_by_action.values())
        print(f"[FINDING] Extracted {total:,} events across {len(events_by_action)} action codes")

        for action in sorted(events_by_action.keys()):
            count = len(events_by_action[action])
            size = payload_sizes.get(action, 32)
            print(f"  Action 0x{action:02X}: {count:,} events (payload {size}B)")

        print(f"[STAGE:status:success]")
        print(f"[STAGE:end:variable_event_extraction]")

        return events_by_action

    def analyze_payloads(self, events_by_action: Dict[int, List], payload_sizes: Dict[int, int]) -> Dict:
        """Analyze payload structure for each action code"""
        print(f"\n[STAGE:begin:payload_semantic_analysis]")

        results = {}

        for action, events in sorted(events_by_action.items()):
            if len(events) < 10:
                continue

            payload_size = payload_sizes.get(action, 32)
            print(f"\n[FINDING] Analyzing action 0x{action:02X} ({len(events)} events, payload {payload_size}B)")

            analysis = {
                'action_code': f"0x{action:02X}",
                'sample_count': len(events),
                'payload_size': payload_size,
                'entity_id_positions': [],
                'float32_positions': [],
            }

            # Scan for entity IDs at all positions
            for pos in range(0, payload_size - 1, 2):
                entity_matches = 0
                match_examples = []

                for event in events:
                    if pos + 2 <= len(event['payload']):
                        val = struct.unpack('<H', event['payload'][pos:pos+2])[0]
                        if val in self.ALL_ENTITY_IDS:
                            entity_matches += 1
                            if len(match_examples) < 3:
                                match_examples.append({
                                    'value': val,
                                    'actor': event['entity_id'],
                                })

                if entity_matches > 0:
                    match_ratio = entity_matches / len(events)
                    analysis['entity_id_positions'].append({
                        'offset': pos,
                        'matches': entity_matches,
                        'ratio': match_ratio,
                        'examples': match_examples,
                    })
                    print(f"  [FINDING] Offset +{pos}: {entity_matches}/{len(events)} entity IDs ({match_ratio*100:.1f}%)")
                    for ex in match_examples[:2]:
                        print(f"    Example: Entity {ex['value']} in event from {ex['actor']}")

            # Scan for float32 coordinates
            for pos in range(0, payload_size - 3, 4):
                valid_floats = []

                for event in events:
                    if pos + 4 <= len(event['payload']):
                        try:
                            val = struct.unpack('<f', event['payload'][pos:pos+4])[0]
                            if np.isfinite(val) and -1000 <= val <= 1000:  # Reasonable coordinate range
                                valid_floats.append(val)
                        except:
                            pass

                if len(valid_floats) > len(events) * 0.5:  # >50% valid
                    analysis['float32_positions'].append({
                        'offset': pos,
                        'count': len(valid_floats),
                        'min': float(np.min(valid_floats)),
                        'max': float(np.max(valid_floats)),
                        'mean': float(np.mean(valid_floats)),
                    })

                    if pos in [8, 12]:  # Known position coordinates
                        print(f"  [STAT:pos_{pos}] Float32 @+{pos}: [{np.min(valid_floats):.2f}, {np.max(valid_floats):.2f}] (KNOWN coordinate)")

            results[action] = analysis

        print(f"\n[STAGE:status:success]")
        print(f"[STAGE:end:payload_semantic_analysis]")

        return results

    def find_kill_events(self, events_by_action: Dict[int, List]) -> List[Dict]:
        """Find events containing cross-team entity IDs (kill candidates)"""
        print(f"\n[STAGE:begin:kill_event_detection]")

        kill_candidates = []

        for action, events in sorted(events_by_action.items()):
            for event in events:
                actor_id = event['entity_id']
                payload = event['payload']

                # Find all entity IDs in payload
                found_entities = []
                for pos in range(0, len(payload) - 1, 2):
                    val = struct.unpack('<H', payload[pos:pos+2])[0]
                    if val in self.ALL_ENTITY_IDS and val != actor_id:
                        found_entities.append({'id': val, 'pos': pos})

                # Check for cross-team references
                if found_entities:
                    actor_team = 1 if actor_id in self.TEAM_1.values() else 2

                    team1_entities = [e for e in found_entities if e['id'] in self.TEAM_1.values()]
                    team2_entities = [e for e in found_entities if e['id'] in self.TEAM_2.values()]

                    # Cross-team = kill candidate
                    if (actor_team == 1 and team2_entities) or (actor_team == 2 and team1_entities):
                        kill_candidates.append({
                            'action_code': f"0x{action:02X}",
                            'actor_id': actor_id,
                            'actor_team': actor_team,
                            'target_entities': found_entities,
                            'offset': event['offset'],
                            'payload_hex': payload.hex(),
                        })

        print(f"[FINDING] Found {len(kill_candidates)} kill candidate events")

        # Group by action
        by_action = defaultdict(list)
        for c in kill_candidates:
            by_action[c['action_code']].append(c)

        for action, candidates in sorted(by_action.items()):
            print(f"  {action}: {len(candidates)} candidates")
            if candidates:
                ex = candidates[0]
                targets = [e['id'] for e in ex['target_entities']]
                positions = [e['pos'] for e in ex['target_entities']]
                print(f"    Example: Actor {ex['actor_id']} (team {ex['actor_team']}) -> targets {targets} at offsets {positions}")

        print(f"[STAT:kill_candidate_count] {len(kill_candidates)}")
        print(f"[STAGE:status:success]")
        print(f"[STAGE:end:kill_event_detection]")

        return kill_candidates

    def run_analysis(self, output_path: str, max_frames: int = 30) -> None:
        """Run complete analysis pipeline"""
        print("[OBJECTIVE] Deep payload structure analysis with variable-size events")

        data = self.load_frames(max_frames)

        # Step 1: Determine payload sizes
        payload_sizes = self.determine_payload_sizes(data)

        # Step 2: Extract events with correct sizes
        events_by_action = self.extract_variable_events(data, payload_sizes)

        # Step 3: Analyze payload semantics
        analysis = self.analyze_payloads(events_by_action, payload_sizes)

        # Step 4: Find kill events
        kill_candidates = self.find_kill_events(events_by_action)

        # Step 5: Generate report
        report = {
            'metadata': {
                'replay': '21.11.04',
                'frames_analyzed': max_frames,
                'team_1': self.TEAM_1,
                'team_2': self.TEAM_2,
            },
            'payload_sizes': {f"0x{k:02X}": v for k, v in sorted(payload_sizes.items())},
            'payload_analysis': {f"0x{k:02X}": v for k, v in sorted(analysis.items())},
            'kill_candidates': kill_candidates,
            'kill_summary': {
                'total': len(kill_candidates),
                'by_action': {
                    action: len([c for c in kill_candidates if c['action_code'] == action])
                    for action in set(c['action_code'] for c in kill_candidates)
                },
            },
        }

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        print(f"\n[FINDING] Report saved to {output_file}")
        print(f"[STAT:file_size] {output_file.stat().st_size / 1024:.1f} KB")

        print("\n" + "="*60)
        print("[FINDING] Deep analysis complete")
        print(f"[STAT:unique_action_codes] {len(payload_sizes)}")
        print(f"[STAT:kill_candidates_found] {len(kill_candidates)}")
        print("="*60)


def main():
    cache_dir = "D:/Desktop/My Folder/Game/VG/vg replay/21.11.04/cache/"
    output_path = "D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/payload_semantic_map.json"

    analyzer = DeepPayloadAnalyzer(cache_dir)
    analyzer.run_analysis(output_path, max_frames=30)

    print("\n[LIMITATION] Payload size determination based on most common inter-event distance")
    print("[LIMITATION] Variable-length events may exist - analysis assumes fixed size per action code")


if __name__ == '__main__':
    main()
