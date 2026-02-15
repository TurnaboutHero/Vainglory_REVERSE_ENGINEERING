#!/usr/bin/env python3
"""
Entity 0 Kill/Death Broadcast Explorer
Searches for kill/death event patterns in Entity 0 system broadcasts.

HYPOTHESIS: Entity 0 broadcasts kill/death events similar to how it broadcasts
item purchases (0xBC) and skill levelups (0x3E).

TRUTH DATA (21.11.04 replay):
- Phinn (Entity 56325): 2K/0D/6A
- Yates (Entity 56581): 1K/4D/4A
- Caine (Entity 56837): 3K/4D/3A
- Petal (Entity 57093): 3K/2D/3A
- Karas (Entity 57349): 0K/3D/2A
- Baron (Entity 57605): 6K/2D/6A
Total: 15 kills, 15 deaths
"""

import sys
import json
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Tuple, Any

# Event structure constants
EVENT_SIZE = 37
PAYLOAD_SIZE = 32

# Known Entity 0 action codes
KNOWN_ACTIONS = {
    0xBC: "item_purchase",
    0x3E: "skill_levelup",
}

# Truth data for validation
TRUTH_DATA = {
    56325: {"name": "Phinn", "kills": 2, "deaths": 0, "assists": 6},
    56581: {"name": "Yates", "kills": 1, "deaths": 4, "assists": 4},
    56837: {"name": "Caine", "kills": 3, "deaths": 4, "assists": 3},
    57093: {"name": "Petal", "kills": 3, "deaths": 2, "assists": 3},
    57349: {"name": "Karas", "kills": 0, "deaths": 3, "assists": 2},
    57605: {"name": "Baron", "kills": 6, "deaths": 2, "assists": 6},
}

TOTAL_KILLS = 15
TOTAL_DEATHS = 15


class Entity0DeathSearcher:
    """Analyzer for Entity 0 kill/death broadcasts"""

    def __init__(self, replay_cache_path: str):
        self.replay_cache_path = Path(replay_cache_path)
        self.player_entities = {eid: data["name"] for eid, data in TRUTH_DATA.items()}

        self.results = {
            "entity_0_all_events": [],
            "entity_0_with_player_refs": [],
            "unknown_action_codes": [],
            "action_code_distribution": {},
            "potential_death_events": [],
            "potential_kill_events": [],
            "statistics": {},
        }

        print(f"[DATA] Player entities: {self.player_entities}")
        print(f"[DATA] Expected kills: {TOTAL_KILLS}, deaths: {TOTAL_DEATHS}")

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

    def _scan_all_entity_0_events(self, data: bytes, frame_num: int) -> List[Dict[str, Any]]:
        """
        Scan for ALL Entity 0 events by searching for pattern: 00 00 00 00 [any_byte]
        Then validate if it's a real event by checking payload structure.
        """
        events = []
        pattern = b'\x00\x00\x00\x00'
        idx = 0

        while True:
            idx = data.find(pattern, idx)
            if idx == -1:
                break

            # Check if there's room for action code + payload
            if idx + 5 + PAYLOAD_SIZE > len(data):
                idx += 1
                continue

            action_code = data[idx + 4]

            # Skip if action code is 0x00 (likely not an event)
            if action_code == 0x00:
                idx += 1
                continue

            # Extract payload
            payload_start = idx + 5
            payload = data[payload_start:payload_start + PAYLOAD_SIZE]

            # Check for player entity references in payload
            player_refs = []
            for entity_id, player_name in self.player_entities.items():
                entity_bytes = entity_id.to_bytes(2, 'little')
                positions = []
                offset = 0
                while True:
                    pos = payload.find(entity_bytes, offset)
                    if pos == -1:
                        break
                    positions.append(pos)
                    offset = pos + 1

                if positions:
                    player_refs.append({
                        "entity_id": entity_id,
                        "name": player_name,
                        "positions": positions,
                    })

            event_data = {
                "frame": frame_num,
                "offset": idx,
                "action_code": f"0x{action_code:02X}",
                "action_code_int": action_code,
                "action_name": KNOWN_ACTIONS.get(action_code, "unknown"),
                "payload_hex": payload.hex(),
                "player_references": player_refs,
                "has_player_refs": len(player_refs) > 0,
            }

            events.append(event_data)
            idx += 1

        return events

    def analyze_all_frames(self) -> None:
        """Scan all frames for Entity 0 events"""
        print("[STAGE:begin:entity_0_scan]")

        frames = self._find_frame_files()
        total_frames = len(frames)

        print(f"[DATA] Found {total_frames} frame files")

        for frame_path in frames:
            frame_num = int(frame_path.stem.split('.')[-1])
            data = frame_path.read_bytes()

            # Scan for all Entity 0 events
            entity_0_events = self._scan_all_entity_0_events(data, frame_num)

            self.results["entity_0_all_events"].extend(entity_0_events)

            # Filter events with player references
            events_with_refs = [e for e in entity_0_events if e["has_player_refs"]]
            self.results["entity_0_with_player_refs"].extend(events_with_refs)

            # Progress
            if frame_num % 50 == 0:
                print(f"[DATA] Processed frame {frame_num}/{total_frames-1}")

        print(f"[STAT:total_entity_0_events] {len(self.results['entity_0_all_events'])}")
        print(f"[STAT:entity_0_with_player_refs] {len(self.results['entity_0_with_player_refs'])}")

        print("[STAGE:status:success]")
        print("[STAGE:end:entity_0_scan]")

    def analyze_action_codes(self) -> None:
        """Analyze distribution of Entity 0 action codes"""
        print("[STAGE:begin:action_code_analysis]")

        # Count all action codes
        action_counts = Counter()
        for event in self.results["entity_0_all_events"]:
            action_counts[event["action_code"]] += 1

        # Sort by frequency
        sorted_actions = action_counts.most_common()

        print("[FINDING] Entity 0 action code distribution:")
        for action_code, count in sorted_actions:
            action_int = int(action_code, 16)
            action_name = KNOWN_ACTIONS.get(action_int, "unknown")
            print(f"  {action_code} ({action_name}): {count} events")

        # Store distribution
        self.results["action_code_distribution"] = {
            code: count for code, count in sorted_actions
        }

        # Find unknown action codes
        unknown_codes = [
            (code, count) for code, count in sorted_actions
            if int(code, 16) not in KNOWN_ACTIONS
        ]

        if unknown_codes:
            print(f"[FINDING] Found {len(unknown_codes)} unknown action codes")
            for code, count in unknown_codes[:10]:  # Top 10
                print(f"  {code}: {count} events")

            self.results["unknown_action_codes"] = [
                {"action_code": code, "count": count}
                for code, count in unknown_codes
            ]

        print("[STAGE:status:success]")
        print("[STAGE:end:action_code_analysis]")

    def search_death_patterns(self) -> None:
        """
        Search for death event patterns in unknown action codes.
        Expected: 15 death events total.
        """
        print("[STAGE:begin:death_pattern_search]")

        # Get events with unknown action codes that have player references
        unknown_with_refs = [
            e for e in self.results["entity_0_with_player_refs"]
            if e["action_code_int"] not in KNOWN_ACTIONS
        ]

        print(f"[DATA] Unknown events with player refs: {len(unknown_with_refs)}")

        # Group by action code
        by_action = defaultdict(list)
        for event in unknown_with_refs:
            by_action[event["action_code"]].append(event)

        # Look for action codes with count close to 15 (deaths) or 15 (kills)
        print("[FINDING] Unknown action codes with player refs (potential death/kill candidates):")

        candidates = []
        for action_code, events in sorted(by_action.items(), key=lambda x: len(x[1]), reverse=True):
            count = len(events)
            print(f"  {action_code}: {count} events")

            if 10 <= count <= 20:  # Near expected death/kill count
                candidates.append({
                    "action_code": action_code,
                    "event_count": count,
                    "events": events,
                })

        if candidates:
            print(f"[FINDING] Found {len(candidates)} candidate action codes for death/kill events")

            for candidate in candidates:
                action_code = candidate["action_code"]
                count = candidate["event_count"]

                # Analyze player distribution
                player_counts = Counter()
                for event in candidate["events"]:
                    for ref in event["player_references"]:
                        player_counts[ref["name"]] += 1

                print(f"\n[FINDING] Action code {action_code} ({count} events) - Player distribution:")
                for player, pcount in player_counts.most_common():
                    expected_deaths = TRUTH_DATA[next(k for k, v in TRUTH_DATA.items() if v["name"] == player)]["deaths"]
                    expected_kills = TRUTH_DATA[next(k for k, v in TRUTH_DATA.items() if v["name"] == player)]["kills"]
                    print(f"  {player}: {pcount} events (expected D={expected_deaths}, K={expected_kills})")

            self.results["potential_death_events"] = candidates

        else:
            print("[LIMITATION] No action codes with event count near expected death/kill count (15)")

        print("[STAGE:status:success]")
        print("[STAGE:end:death_pattern_search]")

    def analyze_payload_patterns(self) -> None:
        """Analyze payload structure for potential death events"""
        print("[STAGE:begin:payload_analysis]")

        if not self.results["potential_death_events"]:
            print("[LIMITATION] No candidate death events to analyze")
            print("[STAGE:status:success]")
            print("[STAGE:end:payload_analysis]")
            return

        for candidate in self.results["potential_death_events"]:
            action_code = candidate["action_code"]
            events = candidate["events"]

            print(f"\n[FINDING] Payload analysis for action code {action_code}:")

            # Analyze entity ID positions in payload
            position_analysis = defaultdict(int)
            for event in events:
                for ref in event["player_references"]:
                    for pos in ref["positions"]:
                        position_analysis[pos] += 1

            print(f"  Entity ID positions in payload (byte offset -> count):")
            for pos in sorted(position_analysis.keys()):
                count = position_analysis[pos]
                print(f"    Offset {pos}: {count} occurrences")

            # Show sample payloads
            print(f"\n  Sample payloads (first 3):")
            for i, event in enumerate(events[:3]):
                player_names = [ref["name"] for ref in event["player_references"]]
                print(f"    Frame {event['frame']}: {event['payload_hex']}")
                print(f"      Players: {', '.join(player_names)}")

        print("[STAGE:status:success]")
        print("[STAGE:end:payload_analysis]")

    def generate_statistics(self) -> None:
        """Generate summary statistics"""
        print("[STAGE:begin:statistics]")

        total_events = len(self.results["entity_0_all_events"])
        total_with_refs = len(self.results["entity_0_with_player_refs"])
        unique_actions = len(self.results["action_code_distribution"])
        unknown_actions = len(self.results["unknown_action_codes"])

        self.results["statistics"] = {
            "total_entity_0_events": total_events,
            "events_with_player_refs": total_with_refs,
            "unique_action_codes": unique_actions,
            "unknown_action_codes": unknown_actions,
            "expected_deaths": TOTAL_DEATHS,
            "expected_kills": TOTAL_KILLS,
            "candidate_death_action_codes": len(self.results["potential_death_events"]),
        }

        print(f"[STAT:unique_action_codes] {unique_actions}")
        print(f"[STAT:unknown_action_codes] {unknown_actions}")
        print(f"[STAT:candidate_death_codes] {len(self.results['potential_death_events'])}")

        print("[STAGE:status:success]")
        print("[STAGE:end:statistics]")

    def save_results(self, output_path: str) -> None:
        """Save analysis results to JSON"""
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Convert to serializable format (limit payload size)
        compact_results = {
            "statistics": self.results["statistics"],
            "action_code_distribution": self.results["action_code_distribution"],
            "unknown_action_codes": self.results["unknown_action_codes"],
            "potential_death_events": self.results["potential_death_events"],
            "truth_data": TRUTH_DATA,
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(compact_results, f, indent=2, ensure_ascii=False)

        print(f"[FINDING] Results saved to {output_file}")


def main():
    """Main execution"""
    print("[OBJECTIVE] Detect kill/death broadcast patterns in Entity 0 system events")

    replay_cache = "D:/Desktop/My Folder/Game/VG/vg replay/21.11.04/cache/"
    output_path = "D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/entity0_death_broadcast.json"

    searcher = Entity0DeathSearcher(replay_cache)

    # Run analysis pipeline
    searcher.analyze_all_frames()
    searcher.analyze_action_codes()
    searcher.search_death_patterns()
    searcher.analyze_payload_patterns()
    searcher.generate_statistics()

    # Save results
    searcher.save_results(output_path)

    print("\n[OBJECTIVE] Entity 0 death broadcast search complete")


if __name__ == "__main__":
    main()
