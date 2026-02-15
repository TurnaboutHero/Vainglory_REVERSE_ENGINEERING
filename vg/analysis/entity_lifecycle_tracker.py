#!/usr/bin/env python3
"""
Entity Lifecycle Tracker - Kill/Death/Assist Detection via Event Analysis

This script builds a comprehensive timeline of ALL entity events in a replay
to identify death markers through:
1. Complete action code discovery (beyond 0x42/43/44)
2. Payload analysis for entity ID pairs (attacker→victim relationships)
3. Event burst pattern detection (sudden activity changes)
4. Statistical analysis of event frequency distributions

Key Hypothesis: Death events are encoded in:
- Specific action codes that appear sporadically (not every frame)
- Payload fields in 0x44 events with multiple player entity IDs
- Event pattern changes (burst followed by silence)
"""

import sys
import json
import struct
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Tuple, Set, Optional
from datetime import datetime


class EntityLifecycleTracker:
    """Track entity events frame-by-frame to detect kill/death patterns."""

    # Player entity ID range based on observations
    # Narrowed to actual player range (not minions/projectiles)
    PLAYER_ENTITY_MIN = 56000
    PLAYER_ENTITY_MAX = 59000

    # System entity broadcasts events for all entities
    SYSTEM_ENTITY_ID = 0

    # Known phase marker action codes (may not be exhaustive)
    KNOWN_PHASE_CODES = {0x42, 0x43, 0x44}

    # Event structure: [EntityID 2B LE][00 00][ActionCode 1B][Payload 32B]
    EVENT_HEADER_SIZE = 5  # 2 + 2 + 1
    PAYLOAD_SIZE = 32
    FULL_EVENT_SIZE = EVENT_HEADER_SIZE + PAYLOAD_SIZE  # 37 bytes

    def __init__(self, replay_dir: str):
        """
        Initialize tracker with replay directory.

        Args:
            replay_dir: Path to replay cache folder containing .vgr files
        """
        self.replay_dir = Path(replay_dir)
        self.frames: List[bytes] = []
        self.frame_count = 0

        # Event tracking
        self.entity_events: Dict[int, List[dict]] = defaultdict(list)
        self.action_code_stats: Counter = Counter()
        self.unique_action_codes: Set[int] = set()

        # Player entity tracking
        self.player_entities: Set[int] = set()

        # Combat interaction tracking (entity pairs in same event)
        self.entity_interactions: List[dict] = []

    def load_frames(self) -> None:
        """Load all replay frames in sequential order."""
        # Find all .vgr files
        vgr_files = list(self.replay_dir.glob("*.vgr"))

        if not vgr_files:
            raise FileNotFoundError(f"No .vgr files found in {self.replay_dir}")

        # Extract frame number from filename (format: uuid.N.vgr)
        def get_frame_number(path: Path) -> int:
            try:
                return int(path.stem.split('.')[-1])
            except (ValueError, IndexError):
                return 0

        # Sort by frame number
        vgr_files.sort(key=get_frame_number)

        # Load frames
        print(f"[DATA] Loading {len(vgr_files)} frames from {self.replay_dir}")
        for vgr_file in vgr_files:
            with open(vgr_file, 'rb') as f:
                frame_data = f.read()
                self.frames.append(frame_data)

        self.frame_count = len(self.frames)
        print(f"[DATA] Loaded {self.frame_count} frames, total size: {sum(len(f) for f in self.frames):,} bytes")

    def is_player_entity(self, entity_id: int) -> bool:
        """Check if entity ID is in player range."""
        return self.PLAYER_ENTITY_MIN <= entity_id <= self.PLAYER_ENTITY_MAX

    def extract_events_from_frame(self, frame_num: int, frame_data: bytes) -> List[dict]:
        """
        Extract ALL events from a frame using the pattern:
        [EntityID 2B LE][00 00][ActionCode 1B][Payload 32B]

        Args:
            frame_num: Frame number
            frame_data: Raw frame binary data

        Returns:
            List of event dictionaries
        """
        events = []
        offset = 0

        while offset + self.FULL_EVENT_SIZE <= len(frame_data):
            # Extract header
            entity_id = struct.unpack('<H', frame_data[offset:offset+2])[0]
            marker = frame_data[offset+2:offset+4]
            action_code = frame_data[offset+4]

            # Check for event marker pattern [00 00]
            if marker == b'\x00\x00':
                # Extract 32-byte payload
                payload_start = offset + self.EVENT_HEADER_SIZE
                payload = frame_data[payload_start:payload_start + self.PAYLOAD_SIZE]

                # Create event record (exclude payload_bytes for JSON serialization)
                event = {
                    'frame': frame_num,
                    'offset': offset,
                    'entity_id': entity_id,
                    'action_code': action_code,
                    'action_hex': f"0x{action_code:02X}",
                    'payload_hex': payload.hex(),
                }

                # Store payload_bytes separately for internal processing
                event_with_bytes = event.copy()
                event_with_bytes['payload_bytes'] = payload

                events.append(event_with_bytes)

                # Track statistics
                self.action_code_stats[action_code] += 1
                self.unique_action_codes.add(action_code)

                # Track player entities
                if self.is_player_entity(entity_id):
                    self.player_entities.add(entity_id)

                # Advance by full event size
                offset += self.FULL_EVENT_SIZE
            else:
                # Not an event header, advance by 1 byte
                offset += 1

        return events

    def parse_payload_entity_ids(self, payload: bytes) -> List[int]:
        """
        Parse payload for entity IDs at known offsets.
        Payload structure from previous analysis:
        - 12 uint16 LE fields at offsets 0,2,4,6,8,10,12,14,16,18,20,22

        Args:
            payload: 32-byte payload

        Returns:
            List of entity IDs found in payload (excluding 0)
        """
        entity_ids = []

        # Extract 12 uint16 fields
        for i in range(12):
            offset = i * 2
            if offset + 2 <= len(payload):
                value = struct.unpack('<H', payload[offset:offset+2])[0]
                if value != 0:  # Ignore null/zero fields
                    entity_ids.append(value)

        return entity_ids

    def analyze_frame(self, frame_num: int) -> None:
        """
        Analyze a single frame and extract all events.

        Args:
            frame_num: Frame number to analyze
        """
        frame_data = self.frames[frame_num]
        events = self.extract_events_from_frame(frame_num, frame_data)

        # Store events by entity
        for event in events:
            entity_id = event['entity_id']
            self.entity_events[entity_id].append(event)

            # For 0x44 events, parse payload for entity interactions
            if event['action_code'] == 0x44:
                payload_entities = self.parse_payload_entity_ids(event['payload_bytes'])

                # Check for player entity interactions
                player_entities_in_payload = [
                    e for e in payload_entities if self.is_player_entity(e)
                ]

                # If multiple player entities in same event → potential combat
                if len(player_entities_in_payload) >= 2:
                    interaction = {
                        'frame': frame_num,
                        'source_entity': entity_id,
                        'player_entities': player_entities_in_payload,
                        'action_code': event['action_code'],
                        'payload_hex': event['payload_hex'],
                    }
                    self.entity_interactions.append(interaction)

    def analyze_all_frames(self) -> None:
        """Analyze all frames sequentially."""
        print(f"\n[STAGE:begin:frame_analysis]")
        print(f"[OBJECTIVE] Analyze {self.frame_count} frames to extract all entity events")

        for frame_num in range(self.frame_count):
            self.analyze_frame(frame_num)

            # Progress report every 50 frames
            if (frame_num + 1) % 50 == 0:
                print(f"  Processed {frame_num + 1}/{self.frame_count} frames...")

        print(f"[DATA] Extracted {sum(len(events) for events in self.entity_events.values()):,} total events")
        print(f"[DATA] Found {len(self.player_entities)} player entities: {sorted(self.player_entities)}")
        print(f"[DATA] Found {len(self.unique_action_codes)} unique action codes")
        print(f"[STAGE:end:frame_analysis]")

    def build_player_timelines(self) -> Dict[int, List[dict]]:
        """
        Build event timeline for each player entity.

        Returns:
            Dictionary mapping player_entity_id -> list of events
        """
        player_timelines = {}

        for entity_id in sorted(self.player_entities):
            events = self.entity_events.get(entity_id, [])
            player_timelines[entity_id] = sorted(events, key=lambda e: e['frame'])

        return player_timelines

    def analyze_action_code_distribution(self) -> dict:
        """
        Analyze action code frequency distribution to identify:
        - Common codes (appear every frame or nearly every frame)
        - Sporadic codes (appear occasionally - potential death markers)
        - Rare codes (very infrequent events)

        Returns:
            Statistical analysis of action codes
        """
        total_events = sum(self.action_code_stats.values())

        # Calculate frequency stats
        code_analysis = {}
        for code, count in self.action_code_stats.items():
            frequency = count / total_events if total_events > 0 else 0

            # Determine category
            if frequency > 0.1:
                category = "very_common"
            elif frequency > 0.01:
                category = "common"
            elif frequency > 0.001:
                category = "sporadic"
            else:
                category = "rare"

            code_analysis[f"0x{code:02X}"] = {
                'code': code,
                'count': count,
                'frequency': frequency,
                'category': category,
                'is_known_phase_code': code in self.KNOWN_PHASE_CODES,
            }

        # Sort by frequency (descending)
        sorted_codes = sorted(
            code_analysis.items(),
            key=lambda x: x[1]['count'],
            reverse=True
        )

        return {
            'total_events': total_events,
            'unique_codes': len(self.unique_action_codes),
            'codes': dict(sorted_codes),
            'known_phase_codes': [f"0x{c:02X}" for c in self.KNOWN_PHASE_CODES],
            'unknown_codes': [
                f"0x{c:02X}" for c in self.unique_action_codes
                if c not in self.KNOWN_PHASE_CODES
            ],
        }

    def detect_event_bursts(self, entity_id: int, window_size: int = 10) -> List[dict]:
        """
        Detect event bursts for an entity (sudden increase in event rate).
        A burst may indicate combat or death.

        Args:
            entity_id: Entity to analyze
            window_size: Number of frames to use as sliding window

        Returns:
            List of detected bursts with frame ranges
        """
        events = self.entity_events.get(entity_id, [])
        if not events:
            return []

        # Count events per frame
        events_per_frame = defaultdict(int)
        for event in events:
            events_per_frame[event['frame']] += 1

        # Calculate baseline (median events per frame)
        all_counts = list(events_per_frame.values())
        all_counts.sort()
        baseline = all_counts[len(all_counts) // 2] if all_counts else 0

        # Detect bursts (frames with >2x baseline activity)
        bursts = []
        threshold = max(baseline * 2, 5)  # At least 5 events to be a burst

        for frame, count in events_per_frame.items():
            if count >= threshold:
                bursts.append({
                    'frame': frame,
                    'event_count': count,
                    'baseline': baseline,
                    'multiplier': count / baseline if baseline > 0 else count,
                })

        return sorted(bursts, key=lambda b: b['frame'])

    def generate_report(self) -> dict:
        """
        Generate comprehensive analysis report.

        Returns:
            Report dictionary with all analysis results
        """
        print(f"\n[STAGE:begin:report_generation]")

        # Build player timelines
        player_timelines = self.build_player_timelines()

        # Action code distribution
        action_code_dist = self.analyze_action_code_distribution()

        # Event burst detection for each player
        player_burst_analysis = {}
        for entity_id in self.player_entities:
            bursts = self.detect_event_bursts(entity_id)
            player_burst_analysis[entity_id] = bursts

        # Build report
        report = {
            'metadata': {
                'replay_dir': str(self.replay_dir),
                'analyzed_at': datetime.now().isoformat(),
                'frame_count': self.frame_count,
                'total_replay_size_bytes': sum(len(f) for f in self.frames),
            },
            'player_entities': {
                'count': len(self.player_entities),
                'entity_ids': sorted(self.player_entities),
                'entity_id_range': f"{self.PLAYER_ENTITY_MIN}-{self.PLAYER_ENTITY_MAX}",
            },
            'action_code_analysis': action_code_dist,
            'player_timelines': {
                entity_id: {
                    'entity_id': entity_id,
                    'total_events': len(timeline),
                    'frames_active': len(set(e['frame'] for e in timeline)),
                    'action_code_distribution': dict(Counter(e['action_hex'] for e in timeline)),
                    'first_frame': timeline[0]['frame'] if timeline else None,
                    'last_frame': timeline[-1]['frame'] if timeline else None,
                    # Remove payload_bytes from events before JSON serialization
                    'events': [
                        {k: v for k, v in event.items() if k != 'payload_bytes'}
                        for event in timeline[:100]
                    ],
                }
                for entity_id, timeline in player_timelines.items()
            },
            'event_bursts': {
                entity_id: bursts
                for entity_id, bursts in player_burst_analysis.items()
                if bursts  # Only include entities with detected bursts
            },
            'entity_interactions': {
                'total_interactions': len(self.entity_interactions),
                'interactions': self.entity_interactions[:100],  # First 100
            },
        }

        print(f"[DATA] Generated report with {len(player_timelines)} player timelines")
        print(f"[STAGE:end:report_generation]")

        return report

    def save_report(self, output_path: str) -> None:
        """
        Save analysis report to JSON file.

        Args:
            output_path: Path to output JSON file
        """
        report = self.generate_report()

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        print(f"\n[FINDING] Analysis report saved to {output_path}")

    def print_summary(self) -> None:
        """Print a summary of findings to console."""
        print("\n" + "="*80)
        print("ENTITY LIFECYCLE ANALYSIS SUMMARY")
        print("="*80)

        print(f"\n[DATA] Player Entities Found: {len(self.player_entities)}")
        for entity_id in sorted(self.player_entities):
            events = self.entity_events.get(entity_id, [])
            action_dist = Counter(e['action_hex'] for e in events)
            print(f"  Entity {entity_id}: {len(events)} events, {len(action_dist)} unique action codes")

        print(f"\n[DATA] Action Code Distribution:")
        action_analysis = self.analyze_action_code_distribution()

        print(f"  Total unique action codes: {action_analysis['unique_codes']}")
        print(f"  Known phase codes: {', '.join(action_analysis['known_phase_codes'])}")
        print(f"  Unknown codes ({len(action_analysis['unknown_codes'])}): {', '.join(action_analysis['unknown_codes'][:20])}")

        print(f"\n[DATA] Top 20 Most Frequent Action Codes:")
        sorted_codes = sorted(
            action_analysis['codes'].items(),
            key=lambda x: x[1]['count'],
            reverse=True
        )
        for i, (code_hex, data) in enumerate(sorted_codes[:20], 1):
            category = data['category']
            count = data['count']
            freq = data['frequency']
            known = " (KNOWN PHASE)" if data['is_known_phase_code'] else ""
            print(f"  {i:2d}. {code_hex}: {count:6,} events ({freq:6.2%}) - {category}{known}")

        print(f"\n[FINDING] Sporadic/Rare action codes (potential death markers):")
        sporadic = [
            (code, data) for code, data in action_analysis['codes'].items()
            if data['category'] in ('sporadic', 'rare')
        ]
        for code_hex, data in sorted(sporadic, key=lambda x: x[1]['count'], reverse=True)[:30]:
            print(f"  {code_hex}: {data['count']:5,} events ({data['frequency']:.4%}) - {data['category']}")

        print(f"\n[DATA] Entity Interactions (multiple players in same event):")
        print(f"  Total interactions detected: {len(self.entity_interactions)}")
        if self.entity_interactions:
            print(f"  Sample interactions (first 5):")
            for i, interaction in enumerate(self.entity_interactions[:5], 1):
                print(f"    {i}. Frame {interaction['frame']}: "
                      f"Source={interaction['source_entity']}, "
                      f"Players={interaction['player_entities']}, "
                      f"Action={interaction['action_code']:02X}")

        print("\n" + "="*80)


def main():
    """Main execution function."""
    if len(sys.argv) < 2:
        print("Usage: python entity_lifecycle_tracker.py <replay_dir> [output_json]")
        print("\nExample:")
        print('  python entity_lifecycle_tracker.py "D:/Desktop/My Folder/Game/VG/vg replay/21.11.04/cache/"')
        sys.exit(1)

    replay_dir = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) >= 3 else "vg/output/entity_lifecycle_analysis.json"

    print("[OBJECTIVE] Track entity lifecycle to detect kill/death/assist events")
    print(f"[DATA] Replay directory: {replay_dir}")
    print(f"[DATA] Output path: {output_path}")

    # Create tracker
    tracker = EntityLifecycleTracker(replay_dir)

    # Load frames
    tracker.load_frames()

    # Analyze all frames
    tracker.analyze_all_frames()

    # Print summary
    tracker.print_summary()

    # Save report
    tracker.save_report(output_path)

    print("\n[LIMITATION] This analysis identifies event patterns but requires manual inspection")
    print("[LIMITATION] to confirm which action codes correspond to actual kill/death events")
    print("[LIMITATION] Recommend: inspect sporadic/rare action codes and entity interactions")

    print("\n[FINDING] Analysis complete - review output JSON for detailed timeline data")


if __name__ == "__main__":
    main()
