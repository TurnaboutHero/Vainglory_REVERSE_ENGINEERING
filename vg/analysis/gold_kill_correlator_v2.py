#!/usr/bin/env python3
"""
Gold Kill Correlator V2 - Event-structured approach

Strategy refinement:
1. Parse player entities from frame 0 (using VGRParser logic)
2. Scan for entity_id based events: [entity_id:uint16][00 00][action_type:uint8][payload:27 bytes]
3. Extract only events where action_type suggests combat (0x80 death, etc.)
4. Within those 27-byte payloads, scan for uint16 values in 150-500 range
5. Correlate with truth data kill counts per player
"""

import struct
import json
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Tuple, Optional
from datetime import datetime

# Truth data for 21.11.04 match
TRUTH_DATA = {
    "total_kills": 15,
    "total_deaths": 15,
    "players": {
        56325: {"name": "Phinn", "entity_id": 56325, "kills": 2, "deaths": 0},
        56581: {"name": "Yates", "entity_id": 56581, "kills": 1, "deaths": 4},
        56837: {"name": "Caine", "entity_id": 56837, "kills": 3, "deaths": 4},
        57093: {"name": "Petal", "entity_id": 57093, "kills": 3, "deaths": 2},
        57349: {"name": "Karas", "entity_id": 57349, "kills": 0, "deaths": 3},
        57605: {"name": "Baron", "entity_id": 57605, "kills": 6, "deaths": 2},
    }
}

HERO_KILL_GOLD_RANGE = (150, 500)
MINION_GOLD_RANGE = (35, 80)


class EventBasedGoldCorrelator:
    """Scan structured events for gold encoding"""

    def __init__(self, replay_cache_path: str):
        self.replay_path = Path(replay_cache_path)
        self.frames_data = b""
        self.entity_events = defaultdict(list)

    def load_all_frames(self) -> None:
        """Load all .vgr frames"""
        print(f"[STAGE:begin:data_loading]")
        start_time = datetime.now()

        vgr_files = sorted(self.replay_path.glob("*.vgr"))

        def get_frame_index(path: Path) -> int:
            parts = path.stem.split('.')
            try:
                return int(parts[-1])
            except (ValueError, IndexError):
                return 0

        vgr_files.sort(key=get_frame_index)
        print(f"[DATA] Found {len(vgr_files)} frame files")

        self.frames_data = b"".join(f.read_bytes() for f in vgr_files)

        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"[DATA] Loaded {len(self.frames_data):,} bytes from {len(vgr_files)} frames")
        print(f"[STAGE:status:success]")
        print(f"[STAGE:time:{elapsed:.2f}]")
        print(f"[STAGE:end:data_loading]")

    def extract_entity_events(self, entity_id: int) -> List[Dict]:
        """
        Extract events for specific entity using pattern:
        [entity_id:uint16 LE][00 00][action_type:uint8][payload:27 bytes]
        Total: 32 bytes per event
        """
        pattern = struct.pack('<HH', entity_id, 0x0000)  # entity_id + 00 00
        events = []

        idx = 0
        while True:
            idx = self.frames_data.find(pattern, idx)
            if idx == -1:
                break

            # Extract full 32-byte event (if available)
            if idx + 32 <= len(self.frames_data):
                event_data = self.frames_data[idx:idx + 32]
                action_type = event_data[4]  # 5th byte
                payload = event_data[5:]     # Remaining 27 bytes

                events.append({
                    'absolute_position': idx,
                    'entity_id': entity_id,
                    'action_type': action_type,
                    'action_hex': f"0x{action_type:02X}",
                    'full_event_hex': event_data.hex(),
                    'payload_bytes': list(payload),
                })

            idx += 1

        return events

    def scan_events_for_gold(self, events: List[Dict],
                            min_gold: int = 150,
                            max_gold: int = 500) -> List[Dict]:
        """Scan event payloads for gold values (uint16 LE)"""
        gold_events = []

        for event in events:
            payload = bytes(event['payload_bytes'])

            # Check all 2-byte positions in payload (0-25 for 27-byte payload)
            for offset in range(len(payload) - 1):
                try:
                    value = struct.unpack_from('<H', payload, offset)[0]
                    if min_gold <= value <= max_gold:
                        gold_events.append({
                            **event,
                            'gold_offset': offset,
                            'gold_value': value,
                        })
                        break  # Only record first gold value per event
                except struct.error:
                    continue

        return gold_events

    def analyze_all_entities(self) -> Dict:
        """Analyze events for all known player entities"""
        print(f"\n[STAGE:begin:entity_event_extraction]")
        start_time = datetime.now()

        results = {}

        for entity_id, player_info in TRUTH_DATA['players'].items():
            print(f"\n[DATA] Analyzing entity {entity_id} ({player_info['name']})")

            # Extract all events for this entity
            events = self.extract_entity_events(entity_id)
            print(f"  Total events: {len(events)}")

            # Count action types
            action_counts = Counter(e['action_type'] for e in events)
            top_actions = action_counts.most_common(10)
            print(f"  Top action types:")
            for action, count in top_actions:
                print(f"    0x{action:02X}: {count:4d} times")

            # Scan for gold values
            gold_events = self.scan_events_for_gold(events)
            print(f"  Events with gold (150-500): {len(gold_events)}")

            # Analyze gold offset distribution
            gold_offset_counts = Counter(e['gold_offset'] for e in gold_events)
            if gold_offset_counts:
                print(f"  Gold offset distribution:")
                for offset, count in gold_offset_counts.most_common(5):
                    print(f"    Offset {offset:2d}: {count:3d} times")

            results[entity_id] = {
                'player_name': player_info['name'],
                'truth_kills': player_info['kills'],
                'truth_deaths': player_info['deaths'],
                'total_events': len(events),
                'action_type_counts': dict(action_counts),
                'gold_events_count': len(gold_events),
                'gold_offset_distribution': dict(gold_offset_counts),
                'sample_gold_events': gold_events[:10],  # First 10 samples
            }

        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"\n[STAT:total_entities_analyzed] {len(results)}")
        print(f"[STAGE:status:success]")
        print(f"[STAGE:time:{elapsed:.2f}]")
        print(f"[STAGE:end:entity_event_extraction]")

        return results

    def correlate_with_kills(self, results: Dict) -> None:
        """Correlate event counts with truth data kills/deaths"""
        print(f"\n[STAGE:begin:kill_correlation]")
        start_time = datetime.now()

        print(f"[OBJECTIVE] Correlate event action types with kill/death counts")
        print(f"\nPlayer-wise correlation:")
        print(f"{'Player':<10} {'Kills':<6} {'Deaths':<7} {'Gold Events':<12} {'Action 0x80':<12}")
        print("-" * 60)

        for entity_id, data in results.items():
            name = data['player_name']
            kills = data['truth_kills']
            deaths = data['truth_deaths']
            gold_events = data['gold_events_count']
            action_80 = data['action_type_counts'].get(0x80, 0)

            print(f"{name:<10} {kills:<6} {deaths:<7} {gold_events:<12} {action_80:<12}")

        # Check if any action type correlates with kills
        print(f"\n[FINDING] Checking action type correlation with kills:")

        # Collect all action types seen
        all_action_types = set()
        for data in results.values():
            all_action_types.update(data['action_type_counts'].keys())

        # For each action type, check correlation
        for action in sorted(all_action_types):
            action_counts = []
            kill_counts = []

            for entity_id, data in results.items():
                count = data['action_type_counts'].get(action, 0)
                kills = data['truth_kills']

                action_counts.append(count)
                kill_counts.append(kills)

            # Simple correlation check: do they match exactly?
            if action_counts == kill_counts:
                print(f"  [FINDING] Action 0x{action:02X} EXACTLY matches kill counts!")
                for entity_id, data in results.items():
                    count = data['action_type_counts'].get(action, 0)
                    print(f"    {data['player_name']}: {count} events = {data['truth_kills']} kills")

        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"[STAGE:status:success]")
        print(f"[STAGE:time:{elapsed:.2f}]")
        print(f"[STAGE:end:kill_correlation]")

    def save_results(self, results: Dict, output_path: str) -> None:
        """Save analysis results"""
        print(f"\n[STAGE:begin:save_results]")
        start_time = datetime.now()

        output = {
            'metadata': {
                'replay_path': str(self.replay_path),
                'total_bytes': len(self.frames_data),
                'analysis_timestamp': datetime.now().isoformat(),
                'truth_data': TRUTH_DATA,
                'version': 'v2_event_based',
            },
            'entity_analysis': results,
        }

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"[FINDING] Results saved to {output_path}")
        print(f"[STAGE:status:success]")
        print(f"[STAGE:time:{elapsed:.2f}]")
        print(f"[STAGE:end:save_results]")


def main():
    """Execute event-based gold kill correlation analysis"""
    print("[OBJECTIVE] Identify Gold field in KillActor events using entity-based event extraction")
    print(f"[DATA] Analyzing replay: 21.11.04")
    print(f"[DATA] Truth data: {TRUTH_DATA['total_kills']} kills across 6 players\n")

    replay_cache = "D:/Desktop/My Folder/Game/VG/vg replay/21.11.04/cache/"
    output_path = "D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/gold_kill_correlation_v2.json"

    correlator = EventBasedGoldCorrelator(replay_cache)

    # Phase 1: Load frames
    correlator.load_all_frames()

    # Phase 2: Extract and analyze events for all entities
    results = correlator.analyze_all_entities()

    # Phase 3: Correlate with truth data
    correlator.correlate_with_kills(results)

    # Phase 4: Save results
    correlator.save_results(results, output_path)

    print(f"\n[FINDING] Analysis complete")
    print(f"[LIMITATION] Assumes event structure: [entity_id:2][0000:2][action:1][payload:27]")
    print(f"[LIMITATION] May need to adjust event size or structure if pattern doesn't match")


if __name__ == '__main__':
    main()
