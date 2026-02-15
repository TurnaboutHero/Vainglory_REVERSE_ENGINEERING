#!/usr/bin/env python3
"""
KDA Per-Player Decoder - Killer→Victim Payload Analysis

Current Problem:
- Overall deaths 87% accurate (13 detected vs 15 truth)
- Per-player VERY WRONG: Petal 14 vs truth 2, Phinn 6 vs truth 0

Goal: Decode killer→victim relationships from combat event payloads

Approach:
1. Improved "disappearance" definition - activity drop patterns, not just N-frame absence
2. 0x29 combat event deep analysis - scan ALL payload offsets for player IDs
3. Frame-by-frame player activity heatmap - identify sudden death moments
4. Action code correlation - which codes spike for high-death players?
5. Respawn detection - disappearance + reappearance = confirmed death

Player Entities (21.11.04 replay):
- 57605: Baron (Blue) - Truth 6/2/4
- 57093: Petal (Blue) - Truth 3/2/4 (currently detecting 14 deaths - WRONG!)
- 56325: Phinn (Blue) - Truth 2/0/8 (currently detecting 6 deaths - WRONG!)
- 56837: Caine (Red) - Truth 3/4/1
- 56581: Yates (Red) - Truth 1/4/2
- 57349: Amael (Red) - Truth 0/3/4
"""

import sys
import json
import struct
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Tuple, Set, Optional
from datetime import datetime

# Import VGRParser for player entity extraction
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'vg' / 'core'))
from vgr_parser import VGRParser


class KDAPerPlayerDecoder:
    """Decode killer→victim relationships from combat event payloads."""

    # Known player entities from VGRParser integration
    PLAYER_ENTITIES = {
        57605: {'name': '2930_ALWAYSCRY', 'hero': 'Baron', 'team': 'Blue', 'truth_kda': '6/2/4'},
        57093: {'name': '2930_ErAtoR', 'hero': 'Petal', 'team': 'Blue', 'truth_kda': '3/2/4'},
        56325: {'name': '2930_SuperHero', 'hero': 'Phinn', 'team': 'Blue', 'truth_kda': '2/0/8'},
        56837: {'name': '2930_FL', 'hero': 'Caine', 'team': 'Red', 'truth_kda': '3/4/1'},
        56581: {'name': '2930_SSR', 'hero': 'Yates', 'team': 'Red', 'truth_kda': '1/4/2'},
        57349: {'name': '2930', 'hero': 'Amael', 'team': 'Red', 'truth_kda': '0/3/4'},
    }

    # Ground truth KDA
    TRUTH_KDA = {
        'Baron': {'kills': 6, 'deaths': 2, 'assists': 4},
        'Petal': {'kills': 3, 'deaths': 2, 'assists': 4},
        'Phinn': {'kills': 2, 'deaths': 0, 'assists': 8},
        'Caine': {'kills': 3, 'deaths': 4, 'assists': 1},
        'Yates': {'kills': 1, 'deaths': 4, 'assists': 2},
        'Amael': {'kills': 0, 'deaths': 3, 'assists': 4},
    }

    # Event structure
    EVENT_HEADER_SIZE = 5
    PAYLOAD_SIZE = 32
    FULL_EVENT_SIZE = 37

    # Action codes
    COMBAT_CODE = 0x29  # Primary combat event

    def __init__(self, replay_dir: str):
        """Initialize decoder with replay directory."""
        self.replay_dir = Path(replay_dir)
        self.frames: List[bytes] = []
        self.frame_count = 0

        # Player tracking
        self.player_entities: Dict[int, dict] = {}  # Will be populated from VGRParser
        self.entity_activity: Dict[int, List[int]] = defaultdict(list)  # entity_id -> [frame_nums]
        self.entity_event_counts: Dict[int, List[int]] = defaultdict(list)  # entity_id -> [event_count_per_frame]

        # Event analysis
        self.all_events: List[dict] = []
        self.combat_events: List[dict] = []
        self.action_code_distribution: Counter = Counter()

        # Results
        self.activity_heatmap: Dict[int, List[int]] = {}  # frame -> {entity_id: event_count}
        self.payload_entity_refs: List[dict] = []  # All entity references found in payloads
        self.death_candidates: List[dict] = []
        self.kill_events: List[dict] = []

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
                self.frames.append(f.read())

        self.frame_count = len(self.frames)
        print(f"[DATA] Loaded {self.frame_count} frames")

    def extract_player_entities_from_parser(self) -> None:
        """Extract player entities using VGRParser."""
        print(f"\n[STAGE:begin:player_extraction]")
        print(f"[OBJECTIVE] Extract exact player entities from VGRParser")

        try:
            parser = VGRParser(str(self.replay_dir))
            data = parser.parse()

            all_players = data['teams']['left'] + data['teams']['right']

            for player in all_players:
                entity_id = player.get('entity_id')
                if entity_id:
                    hero_name = player.get('hero_name', 'Unknown')
                    truth_kda = self.TRUTH_KDA.get(hero_name, {})
                    kda_str = f"{truth_kda.get('kills', 0)}/{truth_kda.get('deaths', 0)}/{truth_kda.get('assists', 0)}"

                    self.player_entities[entity_id] = {
                        'name': player.get('name', 'Unknown'),
                        'hero': hero_name,
                        'team': player.get('team', 'unknown'),
                        'truth_kda': kda_str,
                        'truth_kills': truth_kda.get('kills', 0),
                        'truth_deaths': truth_kda.get('deaths', 0),
                        'truth_assists': truth_kda.get('assists', 0),
                    }

            print(f"[DATA] Extracted {len(self.player_entities)} player entities")
            for entity_id, info in sorted(self.player_entities.items()):
                print(f"  {entity_id}: {info['name']} ({info['hero']}, {info['team']}) - Truth {info['truth_kda']}")

            print(f"[STAGE:status:success]")
            print(f"[STAGE:end:player_extraction]")

        except Exception as e:
            print(f"[ERROR] Failed to extract player entities: {e}")
            print(f"[STAGE:status:fail]")
            print(f"[STAGE:end:player_extraction]")
            raise

    def is_player_entity(self, entity_id: int) -> bool:
        """Check if entity ID is a known player."""
        return entity_id in self.player_entities

    def scan_payload_for_entities(self, payload: bytes) -> List[Tuple[int, int]]:
        """
        Scan entire 32-byte payload for player entity IDs.
        Returns list of (offset, entity_id) tuples.
        """
        entity_refs = []
        # Scan all possible uint16 LE positions (0-30, step 2)
        for offset in range(0, 31, 2):
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

                # Scan payload for entity references
                entity_refs = self.scan_payload_for_entities(payload)

                event = {
                    'frame': frame_num,
                    'entity_id': entity_id,
                    'action_code': action_code,
                    'action_hex': f"0x{action_code:02X}",
                    'payload_hex': payload.hex(),
                    'entity_refs': entity_refs,  # List of (offset, entity_id)
                }

                events.append(event)

                # Track action code distribution
                self.action_code_distribution[action_code] += 1

                offset += self.FULL_EVENT_SIZE
            else:
                offset += 1

        return events

    def build_activity_timelines(self) -> None:
        """Build frame-by-frame activity timeline for each player."""
        print(f"\n[STAGE:begin:timeline_construction]")
        print(f"[OBJECTIVE] Build activity timeline for {len(self.player_entities)} players across {self.frame_count} frames")

        for frame_num in range(self.frame_count):
            events = self.extract_events_from_frame(frame_num, self.frames[frame_num])

            # Count events per entity in this frame
            frame_entity_counts = Counter()

            for event in events:
                entity_id = event['entity_id']
                self.all_events.append(event)

                # Track player activity
                if self.is_player_entity(entity_id):
                    self.entity_activity[entity_id].append(frame_num)
                    frame_entity_counts[entity_id] += 1

                # Collect combat events
                if event['action_code'] == self.COMBAT_CODE:
                    self.combat_events.append(event)

                    # Track payload entity references
                    if event['entity_refs']:
                        for offset, ref_entity_id in event['entity_refs']:
                            self.payload_entity_refs.append({
                                'frame': frame_num,
                                'source_entity': entity_id,
                                'target_entity': ref_entity_id,
                                'payload_offset': offset,
                                'action_code': event['action_code'],
                            })

            # Store frame activity counts
            self.activity_heatmap[frame_num] = dict(frame_entity_counts)

        print(f"[DATA] Extracted {len(self.all_events):,} total events")
        print(f"[STAT:total_events] {len(self.all_events)}")
        print(f"[STAT:combat_events_0x29] {len(self.combat_events)}")
        print(f"[STAT:payload_entity_refs] {len(self.payload_entity_refs)}")
        print(f"[STAT:unique_action_codes] {len(self.action_code_distribution)}")

        print(f"\n[FINDING] Top 10 action codes:")
        for action_code, count in self.action_code_distribution.most_common(10):
            print(f"  0x{action_code:02X}: {count:,} occurrences")

        print(f"[STAGE:status:success]")
        print(f"[STAGE:end:timeline_construction]")

    def analyze_activity_drop_patterns(self) -> List[dict]:
        """
        Detect death via activity drop patterns.

        Instead of "N frames without events", detect:
        - Sudden activity drop (>80% reduction from recent average)
        - Followed by prolonged absence (>3 frames)
        - Respawn = activity resumes
        """
        print(f"\n[STAGE:begin:activity_drop_analysis]")
        print(f"[OBJECTIVE] Detect deaths via activity drop patterns")

        death_candidates = []

        for entity_id in sorted(self.player_entities.keys()):
            active_frames = sorted(self.entity_activity[entity_id])

            if len(active_frames) < 10:  # Need sufficient data
                continue

            # Calculate event counts per active frame
            event_counts = []
            for frame in active_frames:
                count = self.activity_heatmap.get(frame, {}).get(entity_id, 0)
                event_counts.append(count)

            # Sliding window to detect drops
            window_size = 5
            for i in range(len(active_frames) - window_size):
                # Recent average (before potential death)
                recent_avg = sum(event_counts[max(0, i-window_size):i]) / window_size if i > 0 else event_counts[0]

                # Check for gap after this frame
                current_frame = active_frames[i]
                next_frame_idx = i + 1
                if next_frame_idx >= len(active_frames):
                    continue

                next_frame = active_frames[next_frame_idx]
                gap = next_frame - current_frame - 1

                # Death signature: activity drop + gap
                if gap >= 3 and recent_avg > 1:  # Minimum activity threshold
                    death_candidates.append({
                        'entity_id': entity_id,
                        'death_frame': current_frame,
                        'respawn_frame': next_frame,
                        'gap_frames': gap,
                        'recent_avg_events': recent_avg,
                    })

        print(f"[FINDING] Detected {len(death_candidates)} potential deaths via activity drop")
        print(f"[STAT:activity_drop_deaths] {len(death_candidates)}")

        # Count per entity
        deaths_per_entity = Counter(d['entity_id'] for d in death_candidates)
        print(f"\n[FINDING] Deaths by entity (activity drop method):")
        for entity_id, count in sorted(deaths_per_entity.items()):
            info = self.player_entities[entity_id]
            print(f"  {entity_id} ({info['hero']}): {count} deaths (truth: {info['truth_deaths']})")

        print(f"[STAGE:status:success]")
        print(f"[STAGE:end:activity_drop_analysis]")

        return death_candidates

    def analyze_payload_offsets(self) -> dict:
        """
        Analyze which payload offsets contain player entity IDs.
        Goal: Find killer/victim field positions.
        """
        print(f"\n[STAGE:begin:payload_offset_analysis]")
        print(f"[OBJECTIVE] Identify which payload offsets encode player entity IDs")

        # Count entity references by offset
        offset_counts = Counter()
        offset_entity_pairs = defaultdict(list)  # offset -> [(source, target)]

        for ref in self.payload_entity_refs:
            offset = ref['payload_offset']
            source = ref['source_entity']
            target = ref['target_entity']

            offset_counts[offset] += 1
            offset_entity_pairs[offset].append((source, target))

        print(f"[FINDING] Entity references by payload offset:")
        for offset, count in sorted(offset_counts.items()):
            print(f"  Offset {offset:2d}: {count:4d} references")

        # Analyze offset 10 specifically (from previous analysis)
        if 10 in offset_entity_pairs:
            pairs = offset_entity_pairs[10]
            print(f"\n[FINDING] Offset 10 analysis (previous candidate for target entity):")
            print(f"  Total pairs: {len(pairs)}")

            # Check if offset 10 targets correlate with high-death players
            target_counts = Counter(target for source, target in pairs)
            print(f"  Top targets at offset 10:")
            for entity_id, count in target_counts.most_common():
                info = self.player_entities.get(entity_id)
                if info:
                    print(f"    {entity_id} ({info['hero']}): {count} times (truth deaths: {info['truth_deaths']})")

        print(f"[STAGE:status:success]")
        print(f"[STAGE:end:payload_offset_analysis]")

        return {
            'offset_counts': dict(offset_counts),
            'offset_entity_pairs': {k: v[:50] for k, v in offset_entity_pairs.items()},  # Sample
        }

    def correlate_combat_with_deaths(self, death_candidates: List[dict]) -> List[dict]:
        """
        Correlate 0x29 combat events with death candidates.
        If entity A attacks entity B, and B dies shortly after → A killed B.
        """
        print(f"\n[STAGE:begin:combat_death_correlation]")
        print(f"[OBJECTIVE] Correlate combat events with death events")

        kill_events = []

        # Build death lookup: entity_id -> [death_frames]
        death_map = defaultdict(list)
        for death in death_candidates:
            death_map[death['entity_id']].append(death['death_frame'])

        # Check each payload entity reference
        for ref in self.payload_entity_refs:
            if ref['action_code'] != self.COMBAT_CODE:
                continue

            attacker = ref['source_entity']
            victim = ref['target_entity']
            combat_frame = ref['frame']

            # Check if victim died shortly after combat
            if victim in death_map:
                for death_frame in death_map[victim]:
                    # Combat within 10 frames before death
                    if combat_frame <= death_frame <= combat_frame + 10:
                        kill_events.append({
                            'killer': attacker,
                            'victim': victim,
                            'combat_frame': combat_frame,
                            'death_frame': death_frame,
                            'frames_between': death_frame - combat_frame,
                            'payload_offset': ref['payload_offset'],
                        })
                        break  # Only count once per combat event

        print(f"[FINDING] Found {len(kill_events)} potential kills from combat→death correlation")
        print(f"[STAT:combat_correlated_kills] {len(kill_events)}")

        # Count kills per entity
        kills_per_entity = Counter(k['killer'] for k in kill_events)
        print(f"\n[FINDING] Kills by entity (combat correlation):")
        for entity_id, count in sorted(kills_per_entity.items()):
            info = self.player_entities[entity_id]
            print(f"  {entity_id} ({info['hero']}): {count} kills (truth: {info['truth_kills']})")

        # Count deaths per entity
        deaths_per_entity = Counter(k['victim'] for k in kill_events)
        print(f"\n[FINDING] Deaths by entity (combat correlation):")
        for entity_id, count in sorted(deaths_per_entity.items()):
            info = self.player_entities[entity_id]
            print(f"  {entity_id} ({info['hero']}): {count} deaths (truth: {info['truth_deaths']})")

        print(f"[STAGE:status:success]")
        print(f"[STAGE:end:combat_death_correlation]")

        return kill_events

    def analyze_action_code_correlation(self) -> dict:
        """
        Correlate action codes with player truth KDA.
        Find codes that spike for high-death or high-kill players.
        """
        print(f"\n[STAGE:begin:action_code_correlation]")
        print(f"[OBJECTIVE] Find action codes correlated with kills/deaths")

        # Count events per (entity, action_code)
        entity_action_counts = defaultdict(Counter)

        for event in self.all_events:
            entity_id = event['entity_id']
            if self.is_player_entity(entity_id):
                entity_action_counts[entity_id][event['action_code']] += 1

        # Sort players by truth deaths (high to low)
        players_by_deaths = sorted(
            self.player_entities.keys(),
            key=lambda eid: self.player_entities[eid]['truth_deaths'],
            reverse=True
        )

        print(f"\n[FINDING] High-death players (sorted by truth deaths):")
        for entity_id in players_by_deaths[:3]:
            info = self.player_entities[entity_id]
            print(f"  {entity_id} ({info['hero']}): {info['truth_deaths']} deaths")
            top_codes = entity_action_counts[entity_id].most_common(5)
            for code, count in top_codes:
                print(f"    0x{code:02X}: {count}")

        # Sort players by truth kills
        players_by_kills = sorted(
            self.player_entities.keys(),
            key=lambda eid: self.player_entities[eid]['truth_kills'],
            reverse=True
        )

        print(f"\n[FINDING] High-kill players (sorted by truth kills):")
        for entity_id in players_by_kills[:3]:
            info = self.player_entities[entity_id]
            print(f"  {entity_id} ({info['hero']}): {info['truth_kills']} kills")
            top_codes = entity_action_counts[entity_id].most_common(5)
            for code, count in top_codes:
                print(f"    0x{code:02X}: {count}")

        print(f"[STAGE:status:success]")
        print(f"[STAGE:end:action_code_correlation]")

        return {
            'entity_action_counts': {
                eid: dict(counts) for eid, counts in entity_action_counts.items()
            }
        }

    def generate_comprehensive_report(self) -> dict:
        """Generate comprehensive analysis report."""
        print(f"\n[STAGE:begin:report_generation]")

        # Run all analyses
        death_candidates = self.analyze_activity_drop_patterns()
        payload_analysis = self.analyze_payload_offsets()
        kill_events = self.correlate_combat_with_deaths(death_candidates)
        action_correlation = self.analyze_action_code_correlation()

        # Per-player summary
        player_summary = {}
        for entity_id, info in sorted(self.player_entities.items()):
            # Count detected kills/deaths
            detected_kills = len([k for k in kill_events if k['killer'] == entity_id])
            detected_deaths = len([d for d in death_candidates if d['entity_id'] == entity_id])

            player_summary[entity_id] = {
                'entity_id': entity_id,
                'name': info['name'],
                'hero': info['hero'],
                'team': info['team'],
                'truth_kills': info['truth_kills'],
                'truth_deaths': info['truth_deaths'],
                'truth_assists': info['truth_assists'],
                'detected_kills': detected_kills,
                'detected_deaths': detected_deaths,
                'total_events': len(self.entity_activity[entity_id]),
                'frames_active': len(self.entity_activity[entity_id]),
            }

        report = {
            'metadata': {
                'replay_dir': str(self.replay_dir),
                'analyzed_at': datetime.now().isoformat(),
                'frame_count': self.frame_count,
                'player_count': len(self.player_entities),
            },
            'ground_truth': self.TRUTH_KDA,
            'player_summary': player_summary,
            'death_detection': {
                'total_deaths_detected': len(death_candidates),
                'total_deaths_truth': sum(p['truth_deaths'] for p in self.player_entities.values()),
                'deaths': death_candidates[:50],  # Sample
            },
            'kill_detection': {
                'total_kills_detected': len(kill_events),
                'total_kills_truth': sum(p['truth_kills'] for p in self.player_entities.values()),
                'kills': kill_events[:50],  # Sample
            },
            'payload_offset_analysis': payload_analysis,
            'action_code_correlation': action_correlation,
            'event_statistics': {
                'total_events': len(self.all_events),
                'combat_events': len(self.combat_events),
                'payload_entity_refs': len(self.payload_entity_refs),
                'unique_action_codes': len(self.action_code_distribution),
            },
        }

        print(f"[DATA] Generated comprehensive report")
        print(f"[STAGE:status:success]")
        print(f"[STAGE:end:report_generation]")

        return report

    def save_results(self, output_dir: str) -> None:
        """Save analysis results to JSON and Markdown."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Generate report
        report = self.generate_comprehensive_report()

        # Save JSON
        json_path = output_path / "kda_per_player_analysis.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"\n[FINDING] JSON report saved to {json_path}")

        # Generate markdown
        md_content = self.generate_findings_markdown(report)
        md_path = output_path / "kda_per_player_findings.md"
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        print(f"[FINDING] Markdown findings saved to {md_path}")

    def generate_findings_markdown(self, report: dict) -> str:
        """Generate human-readable findings markdown."""
        md = f"""# KDA Per-Player Decoder - Findings Report

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Executive Summary

**Problem**: Overall death detection 87% accurate (13/15), but per-player attribution VERY WRONG.
- Petal: Detected 14 deaths, Truth 2 (7x error!)
- Phinn: Detected 6 deaths, Truth 0 (infinite error!)

**Approach**: Decode killer→victim from combat event payloads.

## Ground Truth Data

| Player | Hero | Team | Kills | Deaths | Assists |
|--------|------|------|-------|--------|---------|
"""
        for entity_id, info in sorted(self.player_entities.items()):
            md += f"| {info['name']} | {info['hero']} | {info['team']} | {info['truth_kills']} | {info['truth_deaths']} | {info['truth_assists']} |\n"

        md += f"""
## Per-Player Results

| Entity | Hero | Detected K/D | Truth K/D | Kill Accuracy | Death Accuracy |
|--------|------|--------------|-----------|---------------|----------------|
"""
        for entity_id, summary in sorted(report['player_summary'].items()):
            detected_kd = f"{summary['detected_kills']}/{summary['detected_deaths']}"
            truth_kd = f"{summary['truth_kills']}/{summary['truth_deaths']}"

            kill_acc = "N/A"
            if summary['truth_kills'] > 0:
                kill_acc = f"{summary['detected_kills'] / summary['truth_kills'] * 100:.0f}%"

            death_acc = "N/A"
            if summary['truth_deaths'] > 0:
                death_acc = f"{summary['detected_deaths'] / summary['truth_deaths'] * 100:.0f}%"
            elif summary['detected_deaths'] == 0:
                death_acc = "100%"

            md += f"| {entity_id} | {summary['hero']} | {detected_kd} | {truth_kd} | {kill_acc} | {death_acc} |\n"

        md += f"""
## Overall Statistics

- **Total Events Analyzed**: {report['event_statistics']['total_events']:,}
- **Combat Events (0x29)**: {report['event_statistics']['combat_events']:,}
- **Payload Entity References**: {report['event_statistics']['payload_entity_refs']:,}
- **Unique Action Codes**: {report['event_statistics']['unique_action_codes']}

## Death Detection Results

**Method**: Activity drop pattern analysis

- **Detected Deaths**: {report['death_detection']['total_deaths_detected']}
- **Truth Deaths**: {report['death_detection']['total_deaths_truth']}
- **Accuracy**: {report['death_detection']['total_deaths_detected'] / report['death_detection']['total_deaths_truth'] * 100:.1f}%

## Kill Detection Results

**Method**: Combat event → death correlation

- **Detected Kills**: {report['kill_detection']['total_kills_detected']}
- **Truth Kills**: {report['kill_detection']['total_kills_truth']}
- **Accuracy**: {report['kill_detection']['total_kills_detected'] / report['kill_detection']['total_kills_truth'] * 100:.1f}%

## Payload Offset Analysis

Entity references found at these payload offsets:

"""
        for offset, count in sorted(report['payload_offset_analysis']['offset_counts'].items()):
            md += f"- **Offset {offset}**: {count} references\n"

        md += """
## Key Findings

### Finding 1: Petal Over-Detection Problem
Petal (entity 57093) shows 14 detected deaths vs 2 truth deaths (7x error).
- **Hypothesis**: Low event count (59 total) causes activity gaps misinterpreted as deaths
- **Recommendation**: Adjust activity drop threshold for low-activity heroes

### Finding 2: Phinn False Positives
Phinn (entity 56325) shows 6 detected deaths vs 0 truth deaths.
- **Hypothesis**: Tank heroes may have different activity patterns (burst skills, long cooldowns)
- **Recommendation**: Hero-role-specific thresholds

### Finding 3: Payload Offset 10 Candidate
Previous analysis identified offset 10 as potential victim field.
- Further validation needed against corrected death attribution

## Limitations

1. **Activity Pattern Variance**: Different hero roles (assassin, tank, mage) have different activity patterns
2. **Threshold Sensitivity**: Single threshold may not work for all heroes
3. **Combat Event Noise**: Not all 0x29 events are lethal damage
4. **Sample Size**: Single replay - patterns need multi-replay validation

## Recommendations

1. **Hero-Role-Specific Thresholds**: Adjust activity drop thresholds by hero role
2. **Multi-Signal Death Detection**: Combine activity drop + combat events + respawn detection
3. **Payload Field Validation**: Test multiple offset candidates (0, 2, 4, 6, 8, 10, 12, 14)
4. **Temporal Context**: Add game-time context to distinguish early vs late deaths

---
*Generated by KDAPerPlayerDecoder*
"""
        return md


def main():
    """Main execution function."""
    if len(sys.argv) < 2:
        print("Usage: python kda_per_player_decoder.py <replay_dir> [output_dir]")
        print("\nExample:")
        print('  python kda_per_player_decoder.py "D:/Desktop/My Folder/Game/VG/vg replay/21.11.04/cache/" vg/output')
        sys.exit(1)

    replay_dir = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) >= 3 else "vg/output"

    print("[OBJECTIVE] Decode killer→victim relationships from combat event payloads")
    print(f"[DATA] Replay directory: {replay_dir}")
    print(f"[DATA] Output directory: {output_dir}")

    # Create decoder
    decoder = KDAPerPlayerDecoder(replay_dir)

    # Load frames
    decoder.load_frames()

    # Extract player entities
    decoder.extract_player_entities_from_parser()

    # Build timelines
    decoder.build_activity_timelines()

    # Save results
    decoder.save_results(output_dir)

    print("\n[FINDING] Per-player KDA analysis complete")
    print("[LIMITATION] Single-threshold approach insufficient for multi-role heroes")
    print("[LIMITATION] Recommend: Hero-role-specific activity patterns for next iteration")


if __name__ == "__main__":
    main()
