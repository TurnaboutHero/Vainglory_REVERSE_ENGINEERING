#!/usr/bin/env python3
"""
System Entity Analyzer - Special parser for Entity 0 and Entity 128
Investigates why Entity 0 (system) events are not being detected by standard parsing.

HYPOTHESIS: Entity 0 events have format `00 00 00 00 [ActionCode]` where the first
two bytes (entity ID = 0x0000) merge with the marker bytes (0x0000), making standard
marker detection fail.
"""

import sys
import json
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Tuple, Any

# Import VGRParser for player/truth data
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from vg.core.vgr_parser import VGRParser

# Known Entity 0 action codes to scan for
ENTITY_0_ACTIONS = {
    0xBC: "item_purchase",
    0x3E: "skill_levelup",
    0x05: "unknown_05",
    0x08: "unknown_08",
}

# Event structure: [EntityID 2B LE][00 00][ActionCode 1B][Payload ~32B] = 37 bytes
EVENT_SIZE = 37
ENTITY_ID_SIZE = 2
MARKER_SIZE = 2
ACTION_CODE_SIZE = 1
PAYLOAD_SIZE = 32


class SystemEntityAnalyzer:
    """Analyzer for Entity 0 and Entity 128 system events"""

    def __init__(self, replay_cache_path: str):
        self.replay_cache_path = Path(replay_cache_path)
        self.results = {
            "entity_0_events": [],
            "entity_128_events": [],
            "frame_summary": {},
            "death_frame_analysis": {},
            "low_entity_events": {},
            "statistics": {},
        }

        # Parse player data using VGRParser
        self.parser = VGRParser(str(self.replay_cache_path))
        self.parsed_data = self.parser.parse()

        # Extract player entity IDs
        self.player_entities = {}
        for team_name in ["left", "right"]:
            for player in self.parsed_data["teams"][team_name]:
                if player["entity_id"]:
                    self.player_entities[player["entity_id"]] = player["name"]

        print(f"[DATA] Loaded player entities: {self.player_entities}")

    def _find_frame_files(self) -> List[Path]:
        """Find all frame files in sorted order"""
        frames = list(self.replay_cache_path.glob("*.vgr"))
        def frame_index(path: Path) -> int:
            try:
                return int(path.stem.split('.')[-1])
            except ValueError:
                return 0
        frames.sort(key=frame_index)
        return frames

    def _scan_entity_0_events(self, data: bytes, frame_num: int) -> List[Dict[str, Any]]:
        """
        Scan for Entity 0 events using pattern: 00 00 00 00 [known_action_code]
        Don't rely on marker detection - scan for known action codes directly.
        """
        events = []

        # Pattern: 4 zero bytes followed by known action code
        for action_code, action_name in ENTITY_0_ACTIONS.items():
            pattern = b'\x00\x00\x00\x00' + bytes([action_code])
            idx = 0

            while True:
                idx = data.find(pattern, idx)
                if idx == -1:
                    break

                # Extract full event (37 bytes total)
                # [00 00][00 00][action_code][32 bytes payload]
                event_start = idx
                event_end = event_start + EVENT_SIZE

                if event_end <= len(data):
                    payload_start = idx + 5  # After 4 zeros + action code
                    payload = data[payload_start:payload_start + PAYLOAD_SIZE]

                    # Check if payload contains player entity IDs
                    player_refs = []
                    for entity_id, player_name in self.player_entities.items():
                        entity_bytes = entity_id.to_bytes(2, 'little')
                        if entity_bytes in payload:
                            player_refs.append({
                                "entity_id": entity_id,
                                "name": player_name,
                                "offset_in_payload": payload.find(entity_bytes)
                            })

                    events.append({
                        "frame": frame_num,
                        "offset": idx,
                        "action_code": f"0x{action_code:02X}",
                        "action_name": action_name,
                        "payload_hex": payload.hex(),
                        "player_references": player_refs,
                    })

                idx += 1

        return events

    def _scan_entity_128_events(self, data: bytes, frame_num: int) -> List[Dict[str, Any]]:
        """
        Scan for Entity 128 (0x80 0x00) events.
        Pattern: 80 00 00 00 [action_code] [32 bytes payload]
        """
        events = []
        pattern = b'\x80\x00\x00\x00'
        idx = 0

        while True:
            idx = data.find(pattern, idx)
            if idx == -1:
                break

            # Check if there's a valid action code after the pattern
            if idx + 5 <= len(data):
                action_code = data[idx + 4]

                # Extract payload
                payload_start = idx + 5
                payload_end = payload_start + PAYLOAD_SIZE

                if payload_end <= len(data):
                    payload = data[payload_start:payload_end]

                    # Check for player entity references
                    player_refs = []
                    for entity_id, player_name in self.player_entities.items():
                        entity_bytes = entity_id.to_bytes(2, 'little')
                        if entity_bytes in payload:
                            player_refs.append({
                                "entity_id": entity_id,
                                "name": player_name,
                                "offset_in_payload": payload.find(entity_bytes)
                            })

                    events.append({
                        "frame": frame_num,
                        "offset": idx,
                        "action_code": f"0x{action_code:02X}",
                        "payload_hex": payload.hex(),
                        "player_references": player_refs,
                    })

            idx += 1

        return events

    def _scan_low_entity_events(self, data: bytes, frame_num: int) -> Dict[int, int]:
        """
        Scan for events from entity IDs 1-10 (potential system broadcasts).
        Returns count of events per entity ID.
        """
        counts = defaultdict(int)

        for entity_id in range(1, 11):
            # Standard event pattern: [entity_id 2B LE][00 00][action_code]
            pattern = entity_id.to_bytes(2, 'little') + b'\x00\x00'
            count = data.count(pattern)
            if count > 0:
                counts[entity_id] = count

        return dict(counts)

    def analyze_all_frames(self) -> None:
        """Analyze all frames for Entity 0 and Entity 128 events"""
        print("[STAGE:begin:frame_analysis]")

        frames = self._find_frame_files()
        total_frames = len(frames)

        print(f"[DATA] Found {total_frames} frame files")

        entity_0_total = 0
        entity_128_total = 0

        # Get death frames from truth data if available
        death_frames = set()
        truth_source = self.parsed_data.get("truth_source")
        if truth_source:
            print(f"[DATA] Truth data loaded from: {truth_source}")
            # Extract death events from players
            for team in ["left", "right"]:
                for player in self.parsed_data["teams"][team]:
                    if player.get("deaths", 0) > 0:
                        print(f"[STAT:deaths_{player['name']}] {player['deaths']}")

        for frame_path in frames:
            frame_num = int(frame_path.stem.split('.')[-1])
            data = frame_path.read_bytes()

            # Scan for Entity 0 events
            entity_0_events = self._scan_entity_0_events(data, frame_num)
            entity_0_total += len(entity_0_events)

            # Scan for Entity 128 events
            entity_128_events = self._scan_entity_128_events(data, frame_num)
            entity_128_total += len(entity_128_events)

            # Scan for low entity ID events
            low_entity_counts = self._scan_low_entity_events(data, frame_num)

            # Store results
            self.results["entity_0_events"].extend(entity_0_events)
            self.results["entity_128_events"].extend(entity_128_events)

            # Frame summary
            self.results["frame_summary"][frame_num] = {
                "entity_0_count": len(entity_0_events),
                "entity_128_count": len(entity_128_events),
                "low_entity_counts": low_entity_counts,
                "frame_size_bytes": len(data),
            }

            # Progress indicator
            if frame_num % 10 == 0:
                print(f"[DATA] Processed frame {frame_num}/{total_frames-1}")

        print(f"[STAT:total_entity_0_events] {entity_0_total}")
        print(f"[STAT:total_entity_128_events] {entity_128_total}")
        print(f"[STAT:frames_analyzed] {total_frames}")

        print("[STAGE:status:success]")
        print("[STAGE:end:frame_analysis]")

    def analyze_death_frames(self) -> None:
        """
        Analyze if Entity 0 fires more events at frames where deaths occur.
        Compare death frames vs non-death frames.
        """
        print("[STAGE:begin:death_frame_analysis]")

        # For now, we'll identify frames with Entity 0 events and correlate
        # In a full implementation, we'd need death timestamps from truth data

        frames_with_entity_0 = defaultdict(int)
        for event in self.results["entity_0_events"]:
            frames_with_entity_0[event["frame"]] += 1

        # Identify frames with high Entity 0 activity
        high_activity_frames = {
            frame: count
            for frame, count in frames_with_entity_0.items()
            if count >= 3
        }

        if high_activity_frames:
            print(f"[FINDING] Found {len(high_activity_frames)} frames with 3+ Entity 0 events")
            print(f"[DATA] High activity frames: {sorted(high_activity_frames.keys())}")
        else:
            print("[FINDING] No frames with significant Entity 0 activity detected")

        self.results["death_frame_analysis"] = {
            "frames_with_entity_0_events": dict(frames_with_entity_0),
            "high_activity_frames": high_activity_frames,
        }

        print("[STAGE:status:success]")
        print("[STAGE:end:death_frame_analysis]")

    def analyze_event_patterns(self) -> None:
        """Analyze patterns in Entity 0 events"""
        print("[STAGE:begin:pattern_analysis]")

        # Action code distribution
        action_counts = Counter()
        for event in self.results["entity_0_events"]:
            action_counts[event["action_code"]] += 1

        print("[FINDING] Entity 0 action code distribution:")
        for action_code, count in action_counts.most_common():
            action_name = next(
                (name for code, name in ENTITY_0_ACTIONS.items()
                 if f"0x{code:02X}" == action_code),
                "unknown"
            )
            print(f"  [STAT:{action_code}_{action_name}] {count}")

        # Player reference analysis
        events_with_player_refs = [
            e for e in self.results["entity_0_events"]
            if e["player_references"]
        ]

        print(f"[STAT:entity_0_events_with_player_refs] {len(events_with_player_refs)}")

        if events_with_player_refs:
            print("[FINDING] Entity 0 events reference player entities:")
            player_ref_counts = Counter()
            for event in events_with_player_refs:
                for ref in event["player_references"]:
                    player_ref_counts[ref["name"]] += 1

            for player, count in player_ref_counts.most_common():
                print(f"  [STAT:refs_{player}] {count}")

        # Entity 128 analysis
        if self.results["entity_128_events"]:
            entity_128_actions = Counter()
            for event in self.results["entity_128_events"]:
                entity_128_actions[event["action_code"]] += 1

            print("[FINDING] Entity 128 action code distribution:")
            for action_code, count in entity_128_actions.most_common():
                print(f"  [STAT:{action_code}] {count}")

        # Low entity ID analysis
        low_entity_summary = defaultdict(int)
        for frame_data in self.results["frame_summary"].values():
            for entity_id, count in frame_data["low_entity_counts"].items():
                low_entity_summary[entity_id] += count

        if low_entity_summary:
            print("[FINDING] Events from low entity IDs (1-10):")
            for entity_id in sorted(low_entity_summary.keys()):
                count = low_entity_summary[entity_id]
                print(f"  [STAT:entity_{entity_id}_events] {count}")

            self.results["low_entity_events"] = dict(low_entity_summary)

        print("[STAGE:status:success]")
        print("[STAGE:end:pattern_analysis]")

    def generate_statistics(self) -> None:
        """Generate summary statistics"""
        print("[STAGE:begin:statistics]")

        total_entity_0 = len(self.results["entity_0_events"])
        total_entity_128 = len(self.results["entity_128_events"])
        total_frames = len(self.results["frame_summary"])

        self.results["statistics"] = {
            "total_entity_0_events": total_entity_0,
            "total_entity_128_events": total_entity_128,
            "total_frames_analyzed": total_frames,
            "avg_entity_0_per_frame": total_entity_0 / total_frames if total_frames > 0 else 0,
            "avg_entity_128_per_frame": total_entity_128 / total_frames if total_frames > 0 else 0,
            "player_entities": self.player_entities,
        }

        print(f"[STAT:avg_entity_0_per_frame] {self.results['statistics']['avg_entity_0_per_frame']:.2f}")
        print(f"[STAT:avg_entity_128_per_frame] {self.results['statistics']['avg_entity_128_per_frame']:.2f}")

        print("[STAGE:status:success]")
        print("[STAGE:end:statistics]")

    def save_results(self, output_path: str) -> None:
        """Save analysis results to JSON"""
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False)

        print(f"[FINDING] Results saved to {output_file}")


def main():
    """Main execution"""
    print("[OBJECTIVE] Identify Entity 0 and Entity 128 events using specialized parsing")

    replay_cache = "D:/Desktop/My Folder/Game/VG/vg replay/21.11.04/cache/"
    output_path = "D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/system_entity_analysis.json"

    analyzer = SystemEntityAnalyzer(replay_cache)

    # Run analysis stages
    analyzer.analyze_all_frames()
    analyzer.analyze_death_frames()
    analyzer.analyze_event_patterns()
    analyzer.generate_statistics()

    # Save results
    analyzer.save_results(output_path)

    print("[OBJECTIVE] Analysis complete - specialized Entity 0/128 parser executed")


if __name__ == "__main__":
    main()
