#!/usr/bin/env python3
"""
Final Payload Mapper - Comprehensive analysis with ALL frames

Generate complete payload semantic map with:
1. Payload size per action code
2. Entity ID positions in payloads
3. Float32 coordinate positions
4. Kill event candidates (cross-team entity references)
"""

import struct
import json
from pathlib import Path
from collections import defaultdict, Counter
import numpy as np


class FinalPayloadMapper:
    """Complete payload structure analysis"""

    TEAM_1 = {'Phinn': 56325, 'Yates': 56581, 'Caine': 56837}
    TEAM_2 = {'Petal': 57093, 'Karas': 57349, 'Baron': 57605}
    ALL_ENTITY_IDS = list(TEAM_1.values()) + list(TEAM_2.values())

    def __init__(self, cache_dir: str):
        self.cache_dir = Path(cache_dir)
        self.payload_sizes = {}
        self.events_by_action = defaultdict(list)

    def load_all_frames(self) -> bytes:
        """Load ALL frames"""
        vgr_files = sorted(self.cache_dir.glob("*.vgr"), key=lambda p: self._frame_index(p))
        data_chunks = [f.read_bytes() for f in vgr_files]
        combined = b''.join(data_chunks)
        print(f"[DATA] Loaded {len(data_chunks)} frames, total {len(combined):,} bytes")
        return combined

    @staticmethod
    def _frame_index(path: Path) -> int:
        try:
            return int(path.stem.split('.')[-1])
        except ValueError:
            return 0

    def determine_payload_sizes(self, data: bytes) -> None:
        """Determine payload size for each action code"""
        print(f"\n[STAGE:begin:payload_size_detection]")

        events = []
        for entity_id in self.ALL_ENTITY_IDS:
            pattern = entity_id.to_bytes(2, 'little') + b'\x00\x00'
            idx = 0
            while True:
                idx = data.find(pattern, idx)
                if idx == -1:
                    break
                if idx + 5 <= len(data):
                    events.append({'offset': idx, 'action': data[idx + 4]})
                idx += 1

        events.sort(key=lambda e: e['offset'])
        print(f"[FINDING] Found {len(events)} total events")

        action_distances = defaultdict(list)
        for i in range(len(events) - 1):
            distance = events[i + 1]['offset'] - events[i]['offset']
            action_distances[events[i]['action']].append(distance)

        for action in sorted(action_distances.keys()):
            distances = action_distances[action]
            most_common = Counter(distances).most_common(1)[0][0]
            self.payload_sizes[action] = most_common - 5

        print(f"[FINDING] Detected payload sizes for {len(self.payload_sizes)} action codes")
        print(f"[STAGE:status:success]")
        print(f"[STAGE:end:payload_size_detection]")

    def extract_all_events(self, data: bytes) -> None:
        """Extract all events with correct payload sizes"""
        print(f"\n[STAGE:begin:event_extraction]")

        for entity_id in self.ALL_ENTITY_IDS:
            pattern = entity_id.to_bytes(2, 'little') + b'\x00\x00'
            idx = 0
            while True:
                idx = data.find(pattern, idx)
                if idx == -1:
                    break

                if idx + 5 <= len(data):
                    action = data[idx + 4]
                    payload_size = self.payload_sizes.get(action, 19)

                    if idx + 5 + payload_size <= len(data):
                        self.events_by_action[action].append({
                            'entity_id': entity_id,
                            'offset': idx,
                            'payload': data[idx + 5:idx + 5 + payload_size],
                        })
                idx += 1

        total = sum(len(events) for events in self.events_by_action.values())
        print(f"[FINDING] Extracted {total:,} events across {len(self.events_by_action)} action codes")
        print(f"[STAGE:status:success]")
        print(f"[STAGE:end:event_extraction]")

    def analyze_payloads(self) -> dict:
        """Analyze payload structure"""
        print(f"\n[STAGE:begin:payload_analysis]")

        results = {}

        for action, events in sorted(self.events_by_action.items()):
            if len(events) < 5:
                continue

            payload_size = self.payload_sizes.get(action, 19)

            analysis = {
                'action_code': f"0x{action:02X}",
                'sample_count': len(events),
                'payload_size_bytes': payload_size,
                'entity_id_positions': [],
                'float32_coordinate_positions': [],
            }

            # Scan for entity IDs
            for pos in range(0, payload_size - 1, 2):
                entity_matches = 0
                examples = []

                for event in events:
                    if pos + 2 <= len(event['payload']):
                        val = struct.unpack('<H', event['payload'][pos:pos+2])[0]
                        if val in self.ALL_ENTITY_IDS and val != event['entity_id']:
                            entity_matches += 1
                            if len(examples) < 5:
                                examples.append({'entity': val, 'actor': event['entity_id']})

                if entity_matches > 0:
                    analysis['entity_id_positions'].append({
                        'offset': pos,
                        'match_count': entity_matches,
                        'match_ratio': entity_matches / len(events),
                        'examples': examples,
                    })

            # Scan for float32 coordinates
            for pos in [8, 12]:  # Known coordinate positions
                if pos + 4 > payload_size:
                    continue

                valid_floats = []
                for event in events:
                    if pos + 4 <= len(event['payload']):
                        try:
                            val = struct.unpack('<f', event['payload'][pos:pos+4])[0]
                            if np.isfinite(val) and -1000 <= val <= 1000:
                                valid_floats.append(val)
                        except:
                            pass

                if len(valid_floats) > len(events) * 0.3:
                    analysis['float32_coordinate_positions'].append({
                        'offset': pos,
                        'valid_count': len(valid_floats),
                        'min': float(np.min(valid_floats)),
                        'max': float(np.max(valid_floats)),
                        'mean': float(np.mean(valid_floats)),
                    })

            results[action] = analysis

        print(f"[FINDING] Analyzed {len(results)} action codes")
        print(f"[STAGE:status:success]")
        print(f"[STAGE:end:payload_analysis]")

        return results

    def find_kill_events(self) -> list:
        """Find cross-team entity reference events"""
        print(f"\n[STAGE:begin:kill_event_search]")

        kill_events = []

        for action, events in sorted(self.events_by_action.items()):
            for event in events:
                actor_id = event['entity_id']
                payload = event['payload']
                actor_team = 1 if actor_id in self.TEAM_1.values() else 2

                # Scan for entity IDs
                found_entities = []
                for pos in range(0, len(payload) - 1, 2):
                    val = struct.unpack('<H', payload[pos:pos+2])[0]
                    if val in self.ALL_ENTITY_IDS and val != actor_id:
                        target_team = 1 if val in self.TEAM_1.values() else 2
                        found_entities.append({
                            'entity_id': val,
                            'position': pos,
                            'team': target_team,
                        })

                # Check for cross-team
                cross_team = [e for e in found_entities if e['team'] != actor_team]

                if cross_team:
                    kill_events.append({
                        'action_code': f"0x{action:02X}",
                        'actor_entity_id': actor_id,
                        'actor_team': actor_team,
                        'target_entities': cross_team,
                        'file_offset': event['offset'],
                        'payload_hex': payload.hex(),
                    })

        print(f"[FINDING] Found {len(kill_events)} kill candidate events")

        by_action = defaultdict(int)
        for e in kill_events:
            by_action[e['action_code']] += 1

        for action in sorted(by_action.keys()):
            print(f"  {action}: {by_action[action]} events")

        print(f"[STAT:kill_event_count] {len(kill_events)}")
        print(f"[STAGE:status:success]")
        print(f"[STAGE:end:kill_event_search]")

        return kill_events

    def generate_report(self, output_path: str, analysis: dict, kill_events: list) -> None:
        """Generate final report"""
        print(f"\n[STAGE:begin:report_generation]")

        report = {
            'metadata': {
                'replay': '21.11.04',
                'team_1': self.TEAM_1,
                'team_2': self.TEAM_2,
                'total_frames': len(list(self.cache_dir.glob("*.vgr"))),
            },
            'payload_sizes': {
                f"0x{k:02X}": v for k, v in sorted(self.payload_sizes.items())
            },
            'payload_semantic_map': {
                f"0x{k:02X}": v for k, v in sorted(analysis.items())
            },
            'kill_events': kill_events[:100],  # First 100 examples
            'kill_event_summary': {
                'total_count': len(kill_events),
                'by_action_code': {
                    action: len([e for e in kill_events if e['action_code'] == action])
                    for action in set(e['action_code'] for e in kill_events)
                },
            },
        }

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        print(f"[FINDING] Report saved to {output_file}")
        print(f"[STAT:file_size] {output_file.stat().st_size / 1024:.1f} KB")
        print(f"[STAGE:status:success]")
        print(f"[STAGE:end:report_generation]")

    def run(self, output_path: str) -> None:
        """Run complete analysis"""
        print("[OBJECTIVE] Complete payload structure mapping with ALL frames")

        data = self.load_all_frames()
        self.determine_payload_sizes(data)
        self.extract_all_events(data)
        analysis = self.analyze_payloads()
        kill_events = self.find_kill_events()
        self.generate_report(output_path, analysis, kill_events)

        print("\n" + "="*60)
        print("[FINDING] Complete analysis finished")
        print(f"[STAT:action_codes] {len(self.payload_sizes)}")
        print(f"[STAT:total_events] {sum(len(e) for e in self.events_by_action.values()):,}")
        print(f"[STAT:kill_events] {len(kill_events)}")
        print("="*60)


def main():
    cache_dir = "D:/Desktop/My Folder/Game/VG/vg replay/21.11.04/cache/"
    output_path = "D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/payload_semantic_map.json"

    mapper = FinalPayloadMapper(cache_dir)
    mapper.run(output_path)

    print("\n[LIMITATION] Kill events are heuristic - cross-team entity references may include other interactions")


if __name__ == '__main__':
    main()
