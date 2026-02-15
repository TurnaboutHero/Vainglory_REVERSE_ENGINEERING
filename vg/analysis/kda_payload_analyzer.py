#!/usr/bin/env python3
"""
KDA Payload Analyzer - Deep Analysis of Death/Kill Event Encoding

This script performs deep payload analysis on suspected death/kill events:
1. 0x80 action code analysis (death marker candidate)
2. Burst frame analysis (frames 72, 85, 97)
3. Combat code payload comparison (0x29, 0x3C, 0x46)
4. Player-specific event profiling
5. Correlation with ground truth KDA data

Truth Data for this replay:
- Blue Team: Baron(6/2/4), Petal(3/2/4), Phinn(2/0/8)
- Red Team: Caine(3/4/1), Yates(1/4/2), Amael(0/3/4)
- Total deaths: 15 (Blue: 4, Red: 11)
"""

import sys
import json
import struct
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Tuple, Set, Optional
from datetime import datetime


class KDAPayloadAnalyzer:
    """Analyze payload patterns for KDA event detection."""

    # Player entity ID range
    PLAYER_ENTITY_MIN = 50000
    PLAYER_ENTITY_MAX = 60000

    # Event structure
    EVENT_HEADER_SIZE = 5  # [EntityID 2B LE][00 00][ActionCode 1B]
    PAYLOAD_SIZE = 32
    FULL_EVENT_SIZE = EVENT_HEADER_SIZE + PAYLOAD_SIZE  # 37 bytes

    # Target action codes
    DEATH_CANDIDATE = 0x80
    COMBAT_CODES = [0x29, 0x3C, 0x46]
    BURST_FRAMES = [72, 85, 97]

    # Ground truth KDA (from match data)
    TRUTH_KDA = {
        'Baron': {'kills': 6, 'deaths': 2, 'assists': 4, 'team': 'Blue'},
        'Petal': {'kills': 3, 'deaths': 2, 'assists': 4, 'team': 'Blue'},
        'Phinn': {'kills': 2, 'deaths': 0, 'assists': 8, 'team': 'Blue'},
        'Caine': {'kills': 3, 'deaths': 4, 'assists': 1, 'team': 'Red'},
        'Yates': {'kills': 1, 'deaths': 4, 'assists': 2, 'team': 'Red'},
        'Amael': {'kills': 0, 'deaths': 3, 'assists': 4, 'team': 'Red'},
    }

    def __init__(self, replay_dir: str):
        """Initialize analyzer with replay directory."""
        self.replay_dir = Path(replay_dir)
        self.frames: List[bytes] = []
        self.frame_count = 0

        # Analysis results
        self.death_events: List[dict] = []  # 0x80 events
        self.combat_events: Dict[int, List[dict]] = defaultdict(list)  # By action code
        self.burst_events: Dict[int, List[dict]] = defaultdict(list)  # By frame
        self.player_profiles: Dict[int, dict] = defaultdict(lambda: {
            'entity_id': 0,
            'action_distribution': Counter(),
            'total_events': 0,
            'frames_active': set(),
        })

        # Player entity tracking
        self.player_entities: Set[int] = set()

    def load_frames(self) -> None:
        """Load all replay frames in sequential order."""
        vgr_files = list(self.replay_dir.glob("*.vgr"))
        if not vgr_files:
            raise FileNotFoundError(f"No .vgr files found in {self.replay_dir}")

        def get_frame_number(path: Path) -> int:
            try:
                return int(path.stem.split('.')[-1])
            except (ValueError, IndexError):
                return 0

        vgr_files.sort(key=get_frame_number)

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

    def extract_uint16_fields(self, payload: bytes) -> List[int]:
        """Extract all uint16 LE fields from payload (16 fields)."""
        fields = []
        for i in range(16):  # 32 bytes / 2 = 16 uint16 fields
            offset = i * 2
            if offset + 2 <= len(payload):
                value = struct.unpack('<H', payload[offset:offset+2])[0]
                fields.append(value)
        return fields

    def find_entity_ids_in_payload(self, payload: bytes) -> List[Tuple[int, int]]:
        """
        Find potential entity IDs in payload.
        Returns list of (offset, entity_id) tuples for values in player range.
        """
        entity_refs = []
        for i in range(16):
            offset = i * 2
            if offset + 2 <= len(payload):
                value = struct.unpack('<H', payload[offset:offset+2])[0]
                if self.is_player_entity(value):
                    entity_refs.append((offset, value))
        return entity_refs

    def extract_events_from_frame(self, frame_num: int, frame_data: bytes) -> List[dict]:
        """Extract all events from a frame."""
        events = []
        offset = 0

        while offset + self.FULL_EVENT_SIZE <= len(frame_data):
            entity_id = struct.unpack('<H', frame_data[offset:offset+2])[0]
            marker = frame_data[offset+2:offset+4]
            action_code = frame_data[offset+4]

            if marker == b'\x00\x00':
                payload_start = offset + self.EVENT_HEADER_SIZE
                payload = frame_data[payload_start:payload_start + self.PAYLOAD_SIZE]

                event = {
                    'frame': frame_num,
                    'offset': offset,
                    'entity_id': entity_id,
                    'action_code': action_code,
                    'action_hex': f"0x{action_code:02X}",
                    'payload_hex': payload.hex(),
                    'payload_bytes': payload,
                    'payload_uint16s': self.extract_uint16_fields(payload),
                    'entity_refs': self.find_entity_ids_in_payload(payload),
                }

                events.append(event)

                # Track player entities
                if self.is_player_entity(entity_id):
                    self.player_entities.add(entity_id)

                offset += self.FULL_EVENT_SIZE
            else:
                offset += 1

        return events

    def analyze_0x80_events(self) -> None:
        """Extract and analyze all 0x80 events (death candidate)."""
        print(f"\n[STAGE:begin:death_marker_analysis]")
        print(f"[OBJECTIVE] Analyze 0x80 action code events for death marker patterns")

        for frame_num in range(self.frame_count):
            events = self.extract_events_from_frame(frame_num, self.frames[frame_num])

            for event in events:
                if event['action_code'] == self.DEATH_CANDIDATE:
                    self.death_events.append(event)

        print(f"[DATA] Found {len(self.death_events)} total 0x80 events")
        print(f"[DATA] Expected deaths from truth data: 15")
        print(f"[FINDING] 0x80 event count / expected deaths ratio: {len(self.death_events) / 15:.2f}")

        # Analyze entity IDs in payloads
        events_with_entity_refs = [e for e in self.death_events if e['entity_refs']]
        print(f"[FINDING] {len(events_with_entity_refs)} 0x80 events contain player entity IDs in payload")

        print(f"[STAGE:end:death_marker_analysis]")

    def analyze_burst_frames(self) -> None:
        """Analyze events in burst frames (72, 85, 97)."""
        print(f"\n[STAGE:begin:burst_frame_analysis]")
        print(f"[OBJECTIVE] Extract all events from burst frames {self.BURST_FRAMES}")

        for frame_num in self.BURST_FRAMES:
            if frame_num >= self.frame_count:
                print(f"[LIMITATION] Frame {frame_num} exceeds replay length ({self.frame_count})")
                continue

            events = self.extract_events_from_frame(frame_num, self.frames[frame_num])

            # Filter player events
            player_events = [e for e in events if self.is_player_entity(e['entity_id'])]

            self.burst_events[frame_num] = player_events

            print(f"[DATA] Frame {frame_num}: {len(events)} total events, {len(player_events)} player events")

            # Action code distribution
            action_dist = Counter(e['action_hex'] for e in player_events)
            print(f"  Top action codes: {action_dist.most_common(5)}")

        print(f"[STAGE:end:burst_frame_analysis]")

    def analyze_combat_codes(self) -> None:
        """Analyze payload patterns for combat codes (0x29, 0x3C, 0x46)."""
        print(f"\n[STAGE:begin:combat_code_analysis]")
        print(f"[OBJECTIVE] Compare payload structures for combat codes {[f'0x{c:02X}' for c in self.COMBAT_CODES]}")

        for frame_num in range(self.frame_count):
            events = self.extract_events_from_frame(frame_num, self.frames[frame_num])

            for event in events:
                if event['action_code'] in self.COMBAT_CODES:
                    self.combat_events[event['action_code']].append(event)

        # Analyze each combat code
        for code in self.COMBAT_CODES:
            events = self.combat_events[code]
            print(f"\n[FINDING] Action code 0x{code:02X}: {len(events)} occurrences")

            if events:
                # Check for entity references in payloads
                events_with_refs = [e for e in events if e['entity_refs']]
                print(f"  {len(events_with_refs)} events contain player entity IDs in payload")

                # Sample payload patterns
                print(f"  Sample payload patterns (first 5):")
                for i, event in enumerate(events[:5], 1):
                    entity_refs = ', '.join([f"offset {off}: entity {eid}" for off, eid in event['entity_refs']])
                    print(f"    {i}. Frame {event['frame']}, Entity {event['entity_id']}: [{entity_refs}]")

        print(f"[STAGE:end:combat_code_analysis]")

    def build_player_profiles(self) -> None:
        """Build event profiles for each player entity."""
        print(f"\n[STAGE:begin:player_profiling]")
        print(f"[OBJECTIVE] Build comprehensive event profiles for each player entity")

        for frame_num in range(self.frame_count):
            events = self.extract_events_from_frame(frame_num, self.frames[frame_num])

            for event in events:
                entity_id = event['entity_id']
                if self.is_player_entity(entity_id):
                    profile = self.player_profiles[entity_id]
                    profile['entity_id'] = entity_id
                    profile['action_distribution'][event['action_hex']] += 1
                    profile['total_events'] += 1
                    profile['frames_active'].add(frame_num)

        print(f"[DATA] Built profiles for {len(self.player_profiles)} player entities")

        # Correlate with truth data (if possible)
        print(f"\n[FINDING] Player entity event profiles:")
        for entity_id in sorted(self.player_profiles.keys()):
            profile = self.player_profiles[entity_id]
            print(f"\n  Entity {entity_id}:")
            print(f"    Total events: {profile['total_events']}")
            print(f"    Frames active: {len(profile['frames_active'])}")
            print(f"    Top 10 action codes:")
            for action_hex, count in profile['action_distribution'].most_common(10):
                print(f"      {action_hex}: {count}")

        print(f"[STAGE:end:player_profiling]")

    def analyze_kda_correlation(self) -> dict:
        """Analyze correlation between event patterns and truth KDA."""
        print(f"\n[STAGE:begin:kda_correlation]")
        print(f"[OBJECTIVE] Correlate event patterns with ground truth KDA")

        correlation_data = {
            'total_deaths_truth': sum(p['deaths'] for p in self.TRUTH_KDA.values()),
            'total_0x80_events': len(self.death_events),
            'ratio': len(self.death_events) / sum(p['deaths'] for p in self.TRUTH_KDA.values()),
        }

        print(f"[STAT:total_deaths_truth] {correlation_data['total_deaths_truth']}")
        print(f"[STAT:total_0x80_events] {correlation_data['total_0x80_events']}")
        print(f"[STAT:ratio] {correlation_data['ratio']:.2f}")

        # Analyze 0x80 events by frame
        death_frames = [e['frame'] for e in self.death_events]
        death_frame_dist = Counter(death_frames)

        print(f"\n[FINDING] 0x80 events distributed across {len(death_frame_dist)} frames")
        print(f"[FINDING] Frames with multiple 0x80 events (potential multi-kills):")
        multi_death_frames = {f: c for f, c in death_frame_dist.items() if c > 1}
        for frame, count in sorted(multi_death_frames.items())[:10]:
            print(f"  Frame {frame}: {count} events")

        correlation_data['death_frame_distribution'] = dict(death_frame_dist)
        correlation_data['multi_death_frames'] = multi_death_frames

        print(f"[STAGE:end:kda_correlation]")

        return correlation_data

    def generate_report(self) -> dict:
        """Generate comprehensive analysis report."""
        print(f"\n[STAGE:begin:report_generation]")

        # Convert sets to lists for JSON serialization
        player_profiles_serializable = {}
        for entity_id, profile in self.player_profiles.items():
            player_profiles_serializable[entity_id] = {
                'entity_id': profile['entity_id'],
                'action_distribution': dict(profile['action_distribution']),
                'total_events': profile['total_events'],
                'frames_active': sorted(list(profile['frames_active'])),
                'frame_count': len(profile['frames_active']),
            }

        report = {
            'metadata': {
                'replay_dir': str(self.replay_dir),
                'analyzed_at': datetime.now().isoformat(),
                'frame_count': self.frame_count,
                'player_entity_range': f"{self.PLAYER_ENTITY_MIN}-{self.PLAYER_ENTITY_MAX}",
            },
            'ground_truth': self.TRUTH_KDA,
            'death_marker_analysis': {
                'action_code': f"0x{self.DEATH_CANDIDATE:02X}",
                'total_events': len(self.death_events),
                'expected_deaths': sum(p['deaths'] for p in self.TRUTH_KDA.values()),
                'events': [
                    {k: v for k, v in e.items() if k != 'payload_bytes'}
                    for e in self.death_events
                ],
            },
            'burst_frame_analysis': {
                'target_frames': self.BURST_FRAMES,
                'frames': {
                    frame: {
                        'total_events': len(events),
                        'events': [
                            {k: v for k, v in e.items() if k != 'payload_bytes'}
                            for e in events
                        ],
                    }
                    for frame, events in self.burst_events.items()
                },
            },
            'combat_code_analysis': {
                'codes': [f"0x{c:02X}" for c in self.COMBAT_CODES],
                'events_by_code': {
                    f"0x{code:02X}": {
                        'total_events': len(events),
                        'events_with_entity_refs': len([e for e in events if e['entity_refs']]),
                        'sample_events': [
                            {k: v for k, v in e.items() if k != 'payload_bytes'}
                            for e in events[:20]
                        ],
                    }
                    for code, events in self.combat_events.items()
                },
            },
            'player_profiles': player_profiles_serializable,
        }

        print(f"[DATA] Generated comprehensive analysis report")
        print(f"[STAGE:end:report_generation]")

        return report

    def generate_findings_markdown(self, correlation_data: dict) -> str:
        """Generate human-readable findings document."""
        md = f"""# KDA Payload Analysis - Findings Report

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Executive Summary

This analysis examined {self.frame_count} frames from the test replay to identify death/kill event encoding patterns in VGR payload data.

**Key Finding**: Action code 0x80 appears {len(self.death_events)} times vs. {correlation_data['total_deaths_truth']} expected deaths (ratio: {correlation_data['ratio']:.2f}x).

## Ground Truth Data

| Player | Team | Kills | Deaths | Assists |
|--------|------|-------|--------|---------|
"""
        for hero, kda in self.TRUTH_KDA.items():
            md += f"| {hero} | {kda['team']} | {kda['kills']} | {kda['deaths']} | {kda['assists']} |\n"

        md += f"""
**Total Deaths**: {correlation_data['total_deaths_truth']}

## Death Marker Analysis (0x80)

**Total 0x80 Events**: {len(self.death_events)}

**Hypothesis**: 0x80 may be a death/state-change marker.
- Ratio: {correlation_data['ratio']:.2f}x expected deaths
- Distribution: {len(correlation_data['death_frame_distribution'])} unique frames

### 0x80 Event Details

"""
        for i, event in enumerate(self.death_events[:10], 1):
            md += f"#### Event {i}\n"
            md += f"- Frame: {event['frame']}\n"
            md += f"- Entity ID: {event['entity_id']}\n"
            md += f"- Payload: `{event['payload_hex']}`\n"
            if event['entity_refs']:
                md += f"- Entity References in Payload:\n"
                for offset, entity_id in event['entity_refs']:
                    md += f"  - Offset {offset}: Entity {entity_id}\n"
            md += "\n"

        if len(self.death_events) > 10:
            md += f"... ({len(self.death_events) - 10} more events)\n\n"

        md += f"""## Burst Frame Analysis

Frames with abnormal entity activity: {self.BURST_FRAMES}

"""
        for frame_num in self.BURST_FRAMES:
            if frame_num in self.burst_events:
                events = self.burst_events[frame_num]
                md += f"### Frame {frame_num}\n"
                md += f"- Player events: {len(events)}\n"
                action_dist = Counter(e['action_hex'] for e in events)
                md += f"- Action code distribution:\n"
                for action_hex, count in action_dist.most_common(10):
                    md += f"  - {action_hex}: {count} events\n"
                md += "\n"

        md += f"""## Combat Code Payload Analysis

Target codes: {', '.join([f'0x{c:02X}' for c in self.COMBAT_CODES])}

"""
        for code in self.COMBAT_CODES:
            events = self.combat_events[code]
            md += f"### Action Code 0x{code:02X}\n"
            md += f"- Total occurrences: {len(events)}\n"
            events_with_refs = [e for e in events if e['entity_refs']]
            md += f"- Events with player entity IDs: {len(events_with_refs)}\n"

            if events:
                md += f"\n**Sample Payloads**:\n\n"
                for i, event in enumerate(events[:5], 1):
                    md += f"{i}. Frame {event['frame']}, Entity {event['entity_id']}:\n"
                    md += f"   - Payload: `{event['payload_hex']}`\n"
                    if event['entity_refs']:
                        md += f"   - Entity refs: {event['entity_refs']}\n"
            md += "\n"

        md += f"""## Player Entity Profiles

Discovered {len(self.player_profiles)} player entities in range {self.PLAYER_ENTITY_MIN}-{self.PLAYER_ENTITY_MAX}.

"""
        for entity_id in sorted(self.player_profiles.keys()):
            profile = self.player_profiles[entity_id]
            md += f"### Entity {entity_id}\n"
            md += f"- Total events: {profile['total_events']}\n"
            md += f"- Frames active: {len(profile['frames_active'])}\n"
            md += f"- Top action codes:\n"
            for action_hex, count in profile['action_distribution'].most_common(10):
                md += f"  - {action_hex}: {count}\n"
            md += "\n"

        md += f"""## Limitations

- **Sample Size**: Single replay analysis; patterns may not generalize
- **Entity Mapping**: Cannot definitively map entity IDs to specific heroes without additional markers
- **Payload Interpretation**: uint16 field interpretation is speculative without format specification
- **Event Context**: Missing temporal context (frame timestamps, game state)

## Recommendations

1. **0x80 Investigation**: Examine if 0x80 ratio ({correlation_data['ratio']:.2f}) suggests:
   - Each death triggers multiple 0x80 events (e.g., death + respawn)
   - 0x80 includes non-death state changes
   - Payload contains killer/victim relationship

2. **Multi-Replay Validation**: Analyze multiple replays to confirm:
   - 0x80 count correlates consistently with deaths
   - Combat codes appear in combat scenarios
   - Player entity ID ranges are stable

3. **Payload Field Mapping**: Focus on:
   - Offset 0-2: Frequently contains entity IDs
   - Identify which field indicates killer vs victim
   - Look for damage/ability ID fields

4. **Frame Context**: Correlate burst frames with:
   - In-game timestamps
   - Known combat events (teamfights, objective fights)
   - Multi-kill scenarios

---
*Generated by KDAPayloadAnalyzer*
"""
        return md

    def save_results(self, output_dir: str) -> None:
        """Save analysis results to JSON and Markdown."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Analyze correlation
        correlation_data = self.analyze_kda_correlation()

        # Generate report
        report = self.generate_report()

        # Save JSON
        json_path = output_path / "kda_payload_analysis.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"\n[FINDING] JSON report saved to {json_path}")

        # Save Markdown
        findings_md = self.generate_findings_markdown(correlation_data)
        md_path = output_path / "kda_payload_findings.md"
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(findings_md)
        print(f"[FINDING] Markdown findings saved to {md_path}")


def main():
    """Main execution function."""
    if len(sys.argv) < 2:
        print("Usage: python kda_payload_analyzer.py <replay_dir> [output_dir]")
        print("\nExample:")
        print('  python kda_payload_analyzer.py "D:/Desktop/My Folder/Game/VG/vg replay/21.11.04/cache/" vg/output')
        sys.exit(1)

    replay_dir = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) >= 3 else "vg/output"

    print("[OBJECTIVE] Deep analysis of KDA payload patterns - death/kill event decoding")
    print(f"[DATA] Replay directory: {replay_dir}")
    print(f"[DATA] Output directory: {output_dir}")

    # Create analyzer
    analyzer = KDAPayloadAnalyzer(replay_dir)

    # Load frames
    analyzer.load_frames()

    # Run analyses
    analyzer.analyze_0x80_events()
    analyzer.analyze_burst_frames()
    analyzer.analyze_combat_codes()
    analyzer.build_player_profiles()

    # Save results
    analyzer.save_results(output_dir)

    print("\n[FINDING] Analysis complete - comprehensive payload analysis finished")
    print("[LIMITATION] Entity-to-hero mapping requires additional correlation with player block data")
    print("[LIMITATION] Payload field semantics are inferred; reverse engineering assumptions need validation")


if __name__ == "__main__":
    main()
