#!/usr/bin/env python3
"""
0x18 Death Marker Validation + 0x29 Kill Signature Multi-Replay Verification

Task 1: Validate 0x18 as death marker in 21.11.04 replay
Task 2: Verify 0x29 kill signature across multiple replays
Task 3: Integrated kill+death analysis

Background:
- 0x29 from player entities = Kill events (Baron 6/6 = 100% match!)
- 0x18: 39.2% player reference rate → most likely death marker candidate
- Currently validated on single replay (21.11.04) only
"""

import sys
import json
import struct
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Tuple, Set, Optional
from datetime import datetime

# Add VGRParser to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'core'))
from vgr_parser import VGRParser


class DeathKillValidator:
    """Validate 0x18 death marker and 0x29 kill signature across replays."""

    # Event structure
    EVENT_HEADER_SIZE = 5
    PAYLOAD_SIZE = 32
    FULL_EVENT_SIZE = 37

    # Action codes
    CODE_0x18 = 0x18  # Death marker candidate
    CODE_0x29 = 0x29  # Kill signature (validated)

    # Truth data for 21.11.04 replay
    TRUTH_2111 = {
        'Baron': {'kills': 6, 'deaths': 2, 'assists': 4},
        'Petal': {'kills': 3, 'deaths': 2, 'assists': 4},
        'Phinn': {'kills': 2, 'deaths': 0, 'assists': 8},
        'Caine': {'kills': 3, 'deaths': 4, 'assists': 1},
        'Yates': {'kills': 1, 'deaths': 4, 'assists': 2},
        'Amael': {'kills': 0, 'deaths': 3, 'assists': 4},
    }

    def __init__(self, replay_dir: str, replay_name: str = None):
        """Initialize validator with replay directory."""
        self.replay_dir = Path(replay_dir)
        self.replay_name = replay_name or self.replay_dir.parent.name
        self.frames: List[bytes] = []
        self.frame_count = 0

        # Player tracking
        self.player_entities: Dict[int, dict] = {}

        # Event tracking
        self.events_0x18: List[dict] = []
        self.events_0x29: List[dict] = []

        # Results
        self.player_0x18_counts: Counter = Counter()  # entity_id -> count (as source)
        self.player_0x29_counts: Counter = Counter()  # entity_id -> count (as source)
        self.player_in_0x18_payload: Counter = Counter()  # entity_id -> count (in payload)

    def load_frames(self) -> None:
        """Load all replay frames."""
        vgr_files = list(self.replay_dir.glob("*.vgr"))
        if not vgr_files:
            raise FileNotFoundError(f"No .vgr files found in {self.replay_dir}")

        vgr_files.sort(key=lambda p: int(p.stem.split('.')[-1]))

        print(f"[DATA] Loading {len(vgr_files)} frames from {self.replay_name}")
        for vgr_file in vgr_files:
            with open(vgr_file, 'rb') as f:
                self.frames.append(f.read())

        self.frame_count = len(self.frames)
        print(f"[DATA] Loaded {self.frame_count} frames")

    def extract_player_entities(self) -> None:
        """Extract player entities using VGRParser."""
        print(f"[STAGE:begin:player_extraction]")

        try:
            parser = VGRParser(str(self.replay_dir))
            data = parser.parse()

            all_players = data['teams']['left'] + data['teams']['right']

            for player in all_players:
                entity_id = player.get('entity_id')
                if entity_id:
                    hero_name = player.get('hero_name', 'Unknown')

                    # Get truth KDA if available (21.11.04 replay)
                    truth_kda = self.TRUTH_2111.get(hero_name, {})

                    self.player_entities[entity_id] = {
                        'name': player.get('name', 'Unknown'),
                        'hero': hero_name,
                        'team': player.get('team', 'unknown'),
                        'truth_kills': truth_kda.get('kills', None),
                        'truth_deaths': truth_kda.get('deaths', None),
                        'truth_assists': truth_kda.get('assists', None),
                    }

            print(f"[DATA] Extracted {len(self.player_entities)} player entities")
            for entity_id, info in sorted(self.player_entities.items()):
                truth_str = f"{info['truth_kills']}/{info['truth_deaths']}/{info['truth_assists']}" if info['truth_kills'] is not None else "N/A"
                print(f"  {entity_id}: {info['hero']} ({info['team']}) - Truth {truth_str}")

            print(f"[STAGE:status:success]")
            print(f"[STAGE:end:player_extraction]")

        except Exception as e:
            print(f"[ERROR] Failed to extract player entities: {e}")
            print(f"[STAGE:status:fail]")
            print(f"[STAGE:end:player_extraction]")
            raise

    def is_player_entity(self, entity_id: int) -> bool:
        """Check if entity ID is a player."""
        return entity_id in self.player_entities

    def scan_payload_for_players(self, payload: bytes) -> List[Tuple[int, int]]:
        """Scan 32-byte payload for player entity IDs (uint16 LE)."""
        player_refs = []
        for offset in range(0, 31, 2):
            if offset + 2 <= len(payload):
                value = struct.unpack('<H', payload[offset:offset+2])[0]
                if self.is_player_entity(value):
                    player_refs.append((offset, value))
        return player_refs

    def analyze_0x18_events(self) -> None:
        """Extract and analyze all 0x18 events."""
        print(f"\n[STAGE:begin:0x18_analysis]")
        print(f"[OBJECTIVE] Analyze 0x18 events for death marker signature")

        for frame_num, frame_data in enumerate(self.frames):
            offset = 0

            while offset + self.FULL_EVENT_SIZE <= len(frame_data):
                entity_id = struct.unpack('<H', frame_data[offset:offset+2])[0]
                marker = frame_data[offset+2:offset+4]

                if marker == b'\x00\x00':
                    action_code = frame_data[offset+4]
                    payload = frame_data[offset+5:offset+37]

                    if action_code == self.CODE_0x18:
                        player_refs = self.scan_payload_for_players(payload)

                        event = {
                            'frame': frame_num,
                            'source_entity': entity_id,
                            'is_player_source': self.is_player_entity(entity_id),
                            'payload_hex': payload.hex(),
                            'player_refs': player_refs,
                        }

                        self.events_0x18.append(event)

                        # Count player as source
                        if self.is_player_entity(entity_id):
                            self.player_0x18_counts[entity_id] += 1

                        # Count players in payload
                        for offset_val, player_id in player_refs:
                            self.player_in_0x18_payload[player_id] += 1

                    offset += self.FULL_EVENT_SIZE
                else:
                    offset += 1

        print(f"[DATA] Found {len(self.events_0x18)} total 0x18 events")
        print(f"[STAT:total_0x18_events] {len(self.events_0x18)}")

        player_source_count = sum(1 for e in self.events_0x18 if e['is_player_source'])
        print(f"[STAT:0x18_player_source] {player_source_count}")

        # Analyze player as source vs truth deaths
        print(f"\n[FINDING] 0x18 events with PLAYER as source:")
        print(f"{'Entity':>6s} {'Hero':>8s} {'0x18 Count':>11s} {'Truth Deaths':>13s} {'Match':>6s}")

        for entity_id in sorted(self.player_entities.keys()):
            count = self.player_0x18_counts[entity_id]
            info = self.player_entities[entity_id]
            truth_deaths = info['truth_deaths']

            if truth_deaths is not None:
                match = "OK" if count == truth_deaths else f"{count - truth_deaths:+d}"
            else:
                match = "N/A"

            truth_str = str(truth_deaths) if truth_deaths is not None else "N/A"
            print(f"{entity_id:6d} {info['hero']:>8s} {count:11d} {truth_str:>13s} {match:>6s}")

        # Analyze player in payload vs truth deaths
        print(f"\n[FINDING] Players appearing in 0x18 payloads:")
        print(f"{'Entity':>6s} {'Hero':>8s} {'Payload Count':>13s} {'Truth Deaths':>13s} {'Match':>6s}")

        for entity_id in sorted(self.player_entities.keys()):
            count = self.player_in_0x18_payload[entity_id]
            info = self.player_entities[entity_id]
            truth_deaths = info['truth_deaths']

            if truth_deaths is not None:
                match = "OK" if count == truth_deaths else f"{count - truth_deaths:+d}"
            else:
                match = "N/A"

            truth_str = str(truth_deaths) if truth_deaths is not None else "N/A"
            print(f"{entity_id:6d} {info['hero']:>8s} {count:13d} {truth_str:>13s} {match:>6s}")

        print(f"[STAGE:status:success]")
        print(f"[STAGE:end:0x18_analysis]")

    def analyze_0x29_events(self) -> None:
        """Extract and analyze all 0x29 events (kill signature)."""
        print(f"\n[STAGE:begin:0x29_analysis]")
        print(f"[OBJECTIVE] Analyze 0x29 events for kill signature validation")

        for frame_num, frame_data in enumerate(self.frames):
            offset = 0

            while offset + self.FULL_EVENT_SIZE <= len(frame_data):
                entity_id = struct.unpack('<H', frame_data[offset:offset+2])[0]
                marker = frame_data[offset+2:offset+4]

                if marker == b'\x00\x00':
                    action_code = frame_data[offset+4]
                    payload = frame_data[offset+5:offset+37]

                    if action_code == self.CODE_0x29:
                        player_refs = self.scan_payload_for_players(payload)

                        event = {
                            'frame': frame_num,
                            'source_entity': entity_id,
                            'is_player_source': self.is_player_entity(entity_id),
                            'payload_hex': payload.hex(),
                            'player_refs': player_refs,
                        }

                        self.events_0x29.append(event)

                        # Count player as source (kills)
                        if self.is_player_entity(entity_id):
                            self.player_0x29_counts[entity_id] += 1

                    offset += self.FULL_EVENT_SIZE
                else:
                    offset += 1

        print(f"[DATA] Found {len(self.events_0x29)} total 0x29 events")
        print(f"[STAT:total_0x29_events] {len(self.events_0x29)}")

        player_source_count = sum(1 for e in self.events_0x29 if e['is_player_source'])
        print(f"[STAT:0x29_player_source] {player_source_count}")

        # Analyze player source vs truth kills
        print(f"\n[FINDING] 0x29 events with PLAYER as source (Kill Signature):")
        print(f"{'Entity':>6s} {'Hero':>8s} {'0x29 Count':>11s} {'Truth Kills':>12s} {'Match':>6s}")

        for entity_id in sorted(self.player_entities.keys()):
            count = self.player_0x29_counts[entity_id]
            info = self.player_entities[entity_id]
            truth_kills = info['truth_kills']

            if truth_kills is not None:
                match = "EXACT" if count == truth_kills else f"{count - truth_kills:+d}"
            else:
                match = "N/A"

            truth_str = str(truth_kills) if truth_kills is not None else "N/A"
            print(f"{entity_id:6d} {info['hero']:>8s} {count:11d} {truth_str:>12s} {match:>6s}")

        print(f"[STAGE:status:success]")
        print(f"[STAGE:end:0x29_analysis]")

    def generate_summary(self) -> dict:
        """Generate summary statistics for this replay."""
        total_detected_kills = sum(self.player_0x29_counts.values())
        total_detected_deaths_source = sum(self.player_0x18_counts.values())
        total_detected_deaths_payload = sum(self.player_in_0x18_payload.values())

        total_truth_kills = sum(p['truth_kills'] for p in self.player_entities.values() if p['truth_kills'] is not None)
        total_truth_deaths = sum(p['truth_deaths'] for p in self.player_entities.values() if p['truth_deaths'] is not None)

        per_player = {}
        for entity_id, info in self.player_entities.items():
            per_player[entity_id] = {
                'hero': info['hero'],
                'team': info['team'],
                'truth_kills': info['truth_kills'],
                'truth_deaths': info['truth_deaths'],
                'detected_kills_0x29': self.player_0x29_counts[entity_id],
                'detected_deaths_0x18_source': self.player_0x18_counts[entity_id],
                'detected_deaths_0x18_payload': self.player_in_0x18_payload[entity_id],
            }

        return {
            'replay_name': self.replay_name,
            'frame_count': self.frame_count,
            'player_count': len(self.player_entities),
            'total_0x18_events': len(self.events_0x18),
            'total_0x29_events': len(self.events_0x29),
            'totals': {
                'truth_kills': total_truth_kills,
                'truth_deaths': total_truth_deaths,
                'detected_kills_0x29': total_detected_kills,
                'detected_deaths_0x18_source': total_detected_deaths_source,
                'detected_deaths_0x18_payload': total_detected_deaths_payload,
            },
            'per_player': per_player,
        }


def find_replay_directories(base_dir: str) -> List[Path]:
    """Find all cache directories with .vgr files."""
    base_path = Path(base_dir)
    replay_dirs = []

    # Search for cache directories
    for path in base_path.rglob('cache'):
        if path.is_dir():
            vgr_files = list(path.glob('*.vgr'))
            if vgr_files:
                replay_dirs.append(path)

    return replay_dirs


def main():
    """Main execution."""
    print("[OBJECTIVE] Validate 0x18 death marker and 0x29 kill signature across multiple replays")

    # Find replay directories
    base_replay_dir = "D:/Desktop/My Folder/Game/VG/vg replay"

    print(f"\n[STAGE:begin:directory_discovery]")
    print(f"[DATA] Searching for replays in {base_replay_dir}")

    replay_dirs = find_replay_directories(base_replay_dir)

    print(f"[DATA] Found {len(replay_dirs)} replay directories with .vgr files:")
    for i, replay_dir in enumerate(replay_dirs, 1):
        print(f"  {i}. {replay_dir}")

    if not replay_dirs:
        print("[ERROR] No replay directories found!")
        print("[LIMITATION] Cannot proceed without replay data")
        return

    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:directory_discovery]")

    # Analyze each replay
    all_summaries = []

    for i, replay_dir in enumerate(replay_dirs[:4], 1):  # Limit to 4 replays
        print(f"\n{'='*80}")
        print(f"REPLAY {i}/{min(len(replay_dirs), 4)}: {replay_dir.parent.name}")
        print(f"{'='*80}")

        try:
            validator = DeathKillValidator(str(replay_dir), replay_dir.parent.name)
            validator.load_frames()
            validator.extract_player_entities()
            validator.analyze_0x18_events()
            validator.analyze_0x29_events()

            summary = validator.generate_summary()
            all_summaries.append(summary)

        except Exception as e:
            print(f"[ERROR] Failed to analyze {replay_dir}: {e}")
            continue

    # Generate comprehensive report
    print(f"\n{'='*80}")
    print("COMPREHENSIVE ANALYSIS ACROSS ALL REPLAYS")
    print(f"{'='*80}")

    output_dir = Path("vg/output")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save JSON
    report = {
        'metadata': {
            'analyzed_at': datetime.now().isoformat(),
            'total_replays': len(all_summaries),
            'base_directory': base_replay_dir,
        },
        'replays': all_summaries,
        'cross_replay_analysis': analyze_cross_replay(all_summaries),
    }

    json_path = output_dir / 'death_marker_validation.json'
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n[FINDING] Comprehensive report saved to {json_path}")

    # Generate markdown
    md_content = generate_markdown_report(report)
    md_path = output_dir / 'death_marker_findings.md'
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_content)
    print(f"[FINDING] Markdown findings saved to {md_path}")

    print("\n[FINDING] Multi-replay validation complete!")


def analyze_cross_replay(summaries: List[dict]) -> dict:
    """Analyze patterns across all replays."""

    # Aggregate totals
    total_kills_truth = 0
    total_kills_detected = 0
    total_deaths_truth = 0
    total_deaths_0x18_source = 0
    total_deaths_0x18_payload = 0

    kill_accuracies = []
    death_source_accuracies = []
    death_payload_accuracies = []

    for summary in summaries:
        totals = summary['totals']

        if totals['truth_kills'] > 0:
            total_kills_truth += totals['truth_kills']
            total_kills_detected += totals['detected_kills_0x29']
            kill_acc = totals['detected_kills_0x29'] / totals['truth_kills']
            kill_accuracies.append(kill_acc)

        if totals['truth_deaths'] > 0:
            total_deaths_truth += totals['truth_deaths']
            total_deaths_0x18_source += totals['detected_deaths_0x18_source']
            total_deaths_0x18_payload += totals['detected_deaths_0x18_payload']

            death_src_acc = totals['detected_deaths_0x18_source'] / totals['truth_deaths']
            death_pld_acc = totals['detected_deaths_0x18_payload'] / totals['truth_deaths']

            death_source_accuracies.append(death_src_acc)
            death_payload_accuracies.append(death_pld_acc)

    return {
        'aggregated_totals': {
            'total_truth_kills': total_kills_truth,
            'total_detected_kills_0x29': total_kills_detected,
            'total_truth_deaths': total_deaths_truth,
            'total_detected_deaths_0x18_source': total_deaths_0x18_source,
            'total_detected_deaths_0x18_payload': total_deaths_0x18_payload,
        },
        'overall_accuracy': {
            'kill_0x29_accuracy': total_kills_detected / total_kills_truth if total_kills_truth > 0 else None,
            'death_0x18_source_accuracy': total_deaths_0x18_source / total_deaths_truth if total_deaths_truth > 0 else None,
            'death_0x18_payload_accuracy': total_deaths_0x18_payload / total_deaths_truth if total_deaths_truth > 0 else None,
        },
        'per_replay_accuracies': {
            'kill_0x29': kill_accuracies,
            'death_0x18_source': death_source_accuracies,
            'death_0x18_payload': death_payload_accuracies,
        },
    }


def generate_markdown_report(report: dict) -> str:
    """Generate markdown findings report."""

    md = f"""# 0x18 Death Marker + 0x29 Kill Signature Validation

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Executive Summary

**Objective**: Validate 0x18 as death marker and verify 0x29 kill signature across multiple replays

**Replays Analyzed**: {report['metadata']['total_replays']}

## Cross-Replay Analysis

"""

    cross = report['cross_replay_analysis']
    agg = cross['aggregated_totals']
    acc = cross['overall_accuracy']

    md += f"""### Aggregated Totals

| Metric | Truth | Detected (0x29) | Detected (0x18 Source) | Detected (0x18 Payload) |
|--------|-------|-----------------|------------------------|-------------------------|
| **Kills** | {agg['total_truth_kills']} | {agg['total_detected_kills_0x29']} | - | - |
| **Deaths** | {agg['total_truth_deaths']} | - | {agg['total_detected_deaths_0x18_source']} | {agg['total_detected_deaths_0x18_payload']} |

### Overall Accuracy

| Signature | Accuracy | Status |
|-----------|----------|--------|
| **0x29 = Kills** | {acc['kill_0x29_accuracy']*100:.1f}% | {"[OK] VALIDATED" if acc['kill_0x29_accuracy'] and acc['kill_0x29_accuracy'] >= 0.95 else "[!] NEEDS REVIEW"} |
| **0x18 Source = Deaths** | {acc['death_0x18_source_accuracy']*100:.1f}% if acc['death_0x18_source_accuracy'] else "N/A" | {"[OK] VALIDATED" if acc['death_0x18_source_accuracy'] and acc['death_0x18_source_accuracy'] >= 0.95 else "[!] NEEDS REVIEW"} |
| **0x18 Payload = Deaths** | {acc['death_0x18_payload_accuracy']*100:.1f}% if acc['death_0x18_payload_accuracy'] else "N/A" | {"[OK] VALIDATED" if acc['death_0x18_payload_accuracy'] and acc['death_0x18_payload_accuracy'] >= 0.95 else "[!] NEEDS REVIEW"} |

"""

    # Per-replay details
    md += "\n## Per-Replay Details\n\n"

    for i, replay_summary in enumerate(report['replays'], 1):
        md += f"""### Replay {i}: {replay_summary['replay_name']}

**Frame Count**: {replay_summary['frame_count']:,}
**Players**: {replay_summary['player_count']}
**Total 0x18 Events**: {replay_summary['total_0x18_events']:,}
**Total 0x29 Events**: {replay_summary['total_0x29_events']:,}

#### Kill Detection (0x29)

| Entity | Hero | Truth Kills | Detected 0x29 | Match |
|--------|------|-------------|---------------|-------|
"""

        for entity_id, player in sorted(replay_summary['per_player'].items()):
            truth_k = player['truth_kills'] if player['truth_kills'] is not None else "N/A"
            detected_k = player['detected_kills_0x29']

            if player['truth_kills'] is not None:
                match = "[OK]" if detected_k == player['truth_kills'] else f"{detected_k - player['truth_kills']:+d}"
            else:
                match = "N/A"

            md += f"| {entity_id} | {player['hero']} | {truth_k} | {detected_k} | {match} |\n"

        md += f"""
#### Death Detection (0x18)

| Entity | Hero | Truth Deaths | 0x18 Source | 0x18 Payload | Best Match |
|--------|------|--------------|-------------|--------------|------------|
"""

        for entity_id, player in sorted(replay_summary['per_player'].items()):
            truth_d = player['truth_deaths'] if player['truth_deaths'] is not None else "N/A"
            detected_src = player['detected_deaths_0x18_source']
            detected_pld = player['detected_deaths_0x18_payload']

            if player['truth_deaths'] is not None:
                src_match = detected_src == player['truth_deaths']
                pld_match = detected_pld == player['truth_deaths']

                if src_match and pld_match:
                    best = "Both [OK]"
                elif src_match:
                    best = "Source [OK]"
                elif pld_match:
                    best = "Payload [OK]"
                else:
                    best = f"Src:{detected_src - player['truth_deaths']:+d} Pld:{detected_pld - player['truth_deaths']:+d}"
            else:
                best = "N/A"

            md += f"| {entity_id} | {player['hero']} | {truth_d} | {detected_src} | {detected_pld} | {best} |\n"

        md += "\n"

    # Key findings
    md += """## Key Findings

### Finding 1: 0x29 Kill Signature Validation

"""

    if acc['kill_0x29_accuracy'] and acc['kill_0x29_accuracy'] >= 0.95:
        md += f"""**STATUS**: [OK] VALIDATED ({acc['kill_0x29_accuracy']*100:.1f}% accuracy)

- Player-sourced 0x29 events consistently match kill counts across replays
- Recommendation: **Use 0x29 for kill detection in production**
"""
    else:
        acc_str = f"{acc['kill_0x29_accuracy']*100:.1f}%" if acc['kill_0x29_accuracy'] else "N/A"
        md += f"""**STATUS**: [!] NEEDS REVIEW ({acc_str} accuracy)

- Inconsistent match between 0x29 events and truth kills
- Further investigation required
"""

    md += """
### Finding 2: 0x18 Death Marker Analysis

"""

    src_acc = acc['death_0x18_source_accuracy']
    pld_acc = acc['death_0x18_payload_accuracy']

    if src_acc and src_acc >= 0.95:
        md += f"""**0x18 Source = Death**: [OK] VALIDATED ({src_acc*100:.1f}% accuracy)
"""
    elif pld_acc and pld_acc >= 0.95:
        md += f"""**0x18 Payload = Death**: [OK] VALIDATED ({pld_acc*100:.1f}% accuracy)
"""
    else:
        src_acc_str = f"{src_acc*100:.1f}%" if src_acc else "N/A"
        pld_acc_str = f"{pld_acc*100:.1f}%" if pld_acc else "N/A"
        md += f"""**0x18 as Death Marker**: [!] INCONCLUSIVE
- Source accuracy: {src_acc_str}
- Payload accuracy: {pld_acc_str}
- Recommendation: Investigate alternative action codes for death detection
"""

    md += """
### Finding 3: Kill/Death Balance

In MOBA games: Total Kills = Total Deaths (across all players)

"""

    if agg['total_truth_kills'] == agg['total_truth_deaths']:
        md += f"""[OK] Truth data balanced: {agg['total_truth_kills']} kills = {agg['total_truth_deaths']} deaths
"""

    if agg['total_detected_kills_0x29'] > 0 and agg['total_detected_deaths_0x18_source'] > 0:
        if agg['total_detected_kills_0x29'] == agg['total_detected_deaths_0x18_source']:
            md += f"""[OK] Detected data balanced (Source): {agg['total_detected_kills_0x29']} kills = {agg['total_detected_deaths_0x18_source']} deaths
"""
        else:
            md += f"""[!] Imbalance (Source): {agg['total_detected_kills_0x29']} kills != {agg['total_detected_deaths_0x18_source']} deaths
"""

    if agg['total_detected_kills_0x29'] > 0 and agg['total_detected_deaths_0x18_payload'] > 0:
        if agg['total_detected_kills_0x29'] == agg['total_detected_deaths_0x18_payload']:
            md += f"""[OK] Detected data balanced (Payload): {agg['total_detected_kills_0x29']} kills = {agg['total_detected_deaths_0x18_payload']} deaths
"""
        else:
            md += f"""[!] Imbalance (Payload): {agg['total_detected_kills_0x29']} kills != {agg['total_detected_deaths_0x18_payload']} deaths
"""

    md += """
## Limitations

1. **Sample Size**: Analysis limited to available replays with truth data
2. **Truth Data Availability**: Only 21.11.04 replay has verified KDA
3. **Payload Offset**: Not all payload offsets analyzed for player references
4. **Temporal Correlation**: Kill/death timing not verified (should occur in same/adjacent frames)

## Recommendations

1. **Production Kill Detection**: Use 0x29 player-sourced events
2. **Death Detection**:
   - If 0x18 source >=95% accurate → use source entity
   - If 0x18 payload >=95% accurate → use payload entity reference
   - Otherwise → investigate alternative codes (0x10, 0xD5, etc.)
3. **Temporal Validation**: Check if kills and deaths occur in temporally correlated frames
4. **Expand Truth Data**: Manually verify KDA for additional replays to improve validation

---
*Generated by DeathKillValidator*
"""

    return md


if __name__ == "__main__":
    main()
