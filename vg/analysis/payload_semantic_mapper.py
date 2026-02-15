#!/usr/bin/env python3
"""
Payload Semantic Mapper - Decode 32-byte payload structure in VGR events

Event structure: [EntityID 2B LE][00 00][ActionCode 1B][Payload 32B] = 37 bytes

Known facts:
- Payload offset +8: float32 position X
- Payload offset +12: float32 position Y
- Action 0x05: movement/position update
- Payload may contain other entity IDs (uint16 LE)

Goal: Map each byte position to semantic meaning and find KillActor events
"""

import struct
import json
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Tuple, Any
import numpy as np


class PayloadSemanticMapper:
    """Analyze payload structure across action codes"""

    # Team composition for 21.11.04
    TEAM_1 = {
        'Phinn': 56325,
        'Yates': 56581,
        'Caine': 56837,
    }
    TEAM_2 = {
        'Petal': 57093,
        'Karas': 57349,
        'Baron': 57605,
    }

    # All entity IDs
    ALL_ENTITY_IDS = list(TEAM_1.values()) + list(TEAM_2.values())

    # Action codes of interest
    TARGET_ACTIONS = [
        0x00, 0x05, 0x07, 0x10, 0x11, 0x12, 0x15, 0x17, 0x18,
        0x29, 0x3E, 0x3F, 0x42, 0x43, 0xBC
    ]

    def __init__(self, cache_dir: str):
        self.cache_dir = Path(cache_dir)
        self.events_by_action = defaultdict(list)
        self.payload_analysis = {}

    def load_frames(self, max_frames: int = 50) -> bytes:
        """Load first N frames for analysis"""
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
        """Extract frame number from filename"""
        try:
            return int(path.stem.split('.')[-1])
        except ValueError:
            return 0

    def extract_events(self, data: bytes) -> None:
        """Extract events matching pattern [EntityID 2B LE][00 00][ActionCode][Payload 32B]"""
        print(f"[STAGE:begin:event_extraction]")

        for entity_id in self.ALL_ENTITY_IDS:
            entity_bytes = entity_id.to_bytes(2, 'little')
            pattern_prefix = entity_bytes + b'\x00\x00'

            idx = 0
            while True:
                idx = data.find(pattern_prefix, idx)
                if idx == -1:
                    break

                # Check if we have enough bytes for full event (4 + 1 + 32 = 37)
                if idx + 37 > len(data):
                    idx += 1
                    continue

                action_code = data[idx + 4]

                # Only extract target action codes
                if action_code in self.TARGET_ACTIONS:
                    payload = data[idx + 5:idx + 37]  # 32 bytes

                    self.events_by_action[action_code].append({
                        'entity_id': entity_id,
                        'offset': idx,
                        'payload': payload,
                    })

                idx += 1

        # Report counts
        total = sum(len(events) for events in self.events_by_action.values())
        print(f"[FINDING] Extracted {total:,} events across {len(self.events_by_action)} action codes")

        for action_code in sorted(self.events_by_action.keys()):
            count = len(self.events_by_action[action_code])
            print(f"  Action 0x{action_code:02X}: {count:,} events")

        print(f"[STAGE:status:success]")
        print(f"[STAGE:end:event_extraction]")

    def analyze_payload_structure(self) -> None:
        """Analyze each byte position in payload for each action code"""
        print(f"[STAGE:begin:payload_analysis]")

        for action_code, events in sorted(self.events_by_action.items()):
            if len(events) < 10:
                continue  # Skip rare events

            print(f"\n[FINDING] Analyzing action 0x{action_code:02X} ({len(events)} samples)")

            analysis = {
                'action_code': f"0x{action_code:02X}",
                'sample_count': len(events),
                'byte_positions': {},
            }

            # Analyze each byte position (0-31)
            for pos in range(32):
                byte_values = [event['payload'][pos] for event in events]

                pos_analysis = {
                    'offset': pos,
                    'zero_ratio': sum(1 for v in byte_values if v == 0) / len(byte_values),
                    'unique_count': len(set(byte_values)),
                    'min': min(byte_values),
                    'max': max(byte_values),
                    'mean': np.mean(byte_values),
                    'std': np.std(byte_values),
                }

                analysis['byte_positions'][pos] = pos_analysis

            # Analyze uint16 LE at each even offset
            analysis['uint16_positions'] = {}
            for pos in range(0, 31, 2):
                uint16_values = []
                entity_id_examples = []

                for event in events:
                    val = struct.unpack('<H', event['payload'][pos:pos+2])[0]
                    uint16_values.append(val)

                    # Track which entity IDs appear
                    if val in self.ALL_ENTITY_IDS:
                        entity_id_examples.append({
                            'value': val,
                            'actor_entity_id': event['entity_id'],
                            'offset': event['offset'],
                        })

                # Check if entity IDs appear at this position
                entity_id_matches = sum(1 for v in uint16_values if v in self.ALL_ENTITY_IDS)

                analysis['uint16_positions'][pos] = {
                    'offset': pos,
                    'entity_id_match_count': entity_id_matches,
                    'entity_id_match_ratio': entity_id_matches / len(uint16_values),
                    'unique_count': len(set(uint16_values)),
                    'min': min(uint16_values),
                    'max': max(uint16_values),
                    'mean': np.mean(uint16_values),
                    'entity_id_examples': entity_id_examples[:10],  # First 10 examples
                }

                if entity_id_matches > 0:
                    print(f"  [FINDING] Position +{pos}: {entity_id_matches}/{len(events)} entity ID matches ({entity_id_matches/len(events)*100:.1f}%)")
                    if entity_id_examples:
                        ex = entity_id_examples[0]
                        print(f"    Example: Found entity {ex['value']} in event from actor {ex['actor_entity_id']}")

            # Analyze float32 at 4-byte aligned positions
            analysis['float32_positions'] = {}
            for pos in range(0, 29, 4):
                float_values = []
                valid_floats = []

                for event in events:
                    try:
                        val = struct.unpack('<f', event['payload'][pos:pos+4])[0]
                        # Filter out NaN/Inf and extremely large values (likely not coordinates)
                        if np.isfinite(val) and abs(val) < 10000:
                            float_values.append(val)
                            valid_floats.append(val)
                    except:
                        pass

                if valid_floats:
                    analysis['float32_positions'][pos] = {
                        'offset': pos,
                        'sample_count': len(valid_floats),
                        'min': float(np.min(valid_floats)),
                        'max': float(np.max(valid_floats)),
                        'mean': float(np.mean(valid_floats)),
                        'std': float(np.std(valid_floats)),
                    }

                    # Highlight position coordinates
                    if pos in [8, 12]:
                        print(f"  [STAT:pos_{pos}_range] Float32 @+{pos}: [{np.min(valid_floats):.2f}, {np.max(valid_floats):.2f}] (known position coord)")

            self.payload_analysis[action_code] = analysis

        print(f"\n[STAGE:status:success]")
        print(f"[STAGE:end:payload_analysis]")

    def find_kill_candidates(self) -> List[Dict[str, Any]]:
        """Find events with 2 different team entity IDs in same payload (kill candidates)"""
        print(f"\n[STAGE:begin:kill_candidate_search]")

        kill_candidates = []
        cross_team_events = []

        for action_code, events in sorted(self.events_by_action.items()):
            for event in events:
                payload = event['payload']
                actor_entity_id = event['entity_id']

                # Scan for uint16 LE entity IDs at all even offsets
                found_entities = []

                for pos in range(0, 31, 2):
                    val = struct.unpack('<H', payload[pos:pos+2])[0]
                    if val in self.ALL_ENTITY_IDS:
                        found_entities.append({
                            'entity_id': val,
                            'position': pos,
                        })

                # Check if we have any entity IDs at all
                if found_entities:
                    # Get teams
                    actor_team = 1 if actor_entity_id in self.TEAM_1.values() else 2

                    team1_found = [e for e in found_entities if e['entity_id'] in self.TEAM_1.values()]
                    team2_found = [e for e in found_entities if e['entity_id'] in self.TEAM_2.values()]

                    # Cross-team interaction (kill candidate)
                    if team1_found and team2_found:
                        kill_candidates.append({
                            'action_code': f"0x{action_code:02X}",
                            'actor_entity_id': actor_entity_id,
                            'actor_team': actor_team,
                            'found_entities': found_entities,
                            'team1_entities': team1_found,
                            'team2_entities': team2_found,
                            'offset': event['offset'],
                            'payload_hex': payload.hex(),
                        })

        print(f"[FINDING] Found {len(kill_candidates)} kill candidate events (cross-team entity references)")

        # Group by action code
        by_action = defaultdict(list)
        for candidate in kill_candidates:
            by_action[candidate['action_code']].append(candidate)

        for action_code, candidates in sorted(by_action.items()):
            print(f"  {action_code}: {len(candidates)} candidates")

            # Show first example
            if candidates:
                ex = candidates[0]
                entity_ids = [e['entity_id'] for e in ex['found_entities']]
                positions = [e['position'] for e in ex['found_entities']]
                print(f"    Example: Actor={ex['actor_entity_id']} (team {ex['actor_team']})")
                print(f"             Found: {entity_ids} at positions {positions}")

        print(f"[STAT:kill_candidate_count] {len(kill_candidates)}")
        print(f"[STAGE:status:success]")
        print(f"[STAGE:end:kill_candidate_search]")

        return kill_candidates

    def generate_report(self, output_path: str, kill_candidates: List[Dict[str, Any]]) -> None:
        """Generate JSON report with payload semantic mapping"""
        print(f"\n[STAGE:begin:report_generation]")

        report = {
            'metadata': {
                'replay': '21.11.04',
                'cache_dir': str(self.cache_dir),
                'team_1': {name: eid for name, eid in self.TEAM_1.items()},
                'team_2': {name: eid for name, eid in self.TEAM_2.items()},
                'target_actions': [f"0x{ac:02X}" for ac in self.TARGET_ACTIONS],
            },
            'event_counts': {
                f"0x{ac:02X}": len(events)
                for ac, events in sorted(self.events_by_action.items())
            },
            'payload_analysis': {
                f"0x{ac:02X}": analysis
                for ac, analysis in sorted(self.payload_analysis.items())
            },
            'kill_candidates': kill_candidates,
            'kill_candidate_summary': {
                'total_count': len(kill_candidates),
                'by_action_code': {
                    action_code: len([c for c in kill_candidates if c['action_code'] == action_code])
                    for action_code in set(c['action_code'] for c in kill_candidates)
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

    def run_analysis(self, output_path: str, max_frames: int = 50) -> None:
        """Run complete payload analysis pipeline"""
        print("[OBJECTIVE] Decode 32-byte payload structure and identify KillActor candidates")

        # Load data
        data = self.load_frames(max_frames)

        # Extract events
        self.extract_events(data)

        # Analyze payload structure
        self.analyze_payload_structure()

        # Find kill candidates
        kill_candidates = self.find_kill_candidates()

        # Generate report
        self.generate_report(output_path, kill_candidates)

        print("\n" + "="*60)
        print("[FINDING] Analysis complete")
        print(f"[STAT:total_events] {sum(len(e) for e in self.events_by_action.values())}")
        print(f"[STAT:action_codes_analyzed] {len(self.payload_analysis)}")
        print(f"[STAT:kill_candidates_found] {len(kill_candidates)}")
        print("="*60)


def main():
    cache_dir = "D:/Desktop/My Folder/Game/VG/vg replay/21.11.04/cache/"
    output_path = "D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/payload_semantic_map.json"

    mapper = PayloadSemanticMapper(cache_dir)
    mapper.run_analysis(output_path, max_frames=50)

    print(f"\n[LIMITATION] Analysis based on first 50 frames - combat events may occur later in replay")
    print("[LIMITATION] Kill candidate identification is heuristic - requires validation with API telemetry")
    print("[LIMITATION] Float32 analysis filtered to |value| < 10000 to focus on likely coordinates")


if __name__ == '__main__':
    main()
