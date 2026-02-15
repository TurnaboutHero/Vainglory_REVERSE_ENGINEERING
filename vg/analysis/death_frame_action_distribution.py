#!/usr/bin/env python3
"""
Death Frame Action Code Distribution Analysis

Analyzes action code distributions across all frames to identify:
1. Rare action codes (< 1% frequency)
2. Action code transitions (sudden appearance/disappearance)
3. Death frame candidates based on distribution anomalies
"""

import json
import struct
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Tuple, Set
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.vgr_parser import VGRParser


class DeathFrameAnalyzer:
    """Analyzes action code distributions to detect death frames"""

    def __init__(self, replay_cache_dir: str):
        self.replay_cache_dir = Path(replay_cache_dir)
        self.frames_data = []  # List of {frame_num, action_counts, player_actions}
        self.global_action_counts = Counter()  # Total counts across all frames
        self.total_events = 0

    def parse_frame(self, frame_path: Path) -> Dict:
        """Parse a single frame and extract action code distribution"""
        data = frame_path.read_bytes()

        # Extract frame number
        frame_num = int(frame_path.stem.split('.')[-1])

        # Count action codes globally
        action_counts = Counter()

        # Parse events: [EntityID 2B LE][00 00][ActionCode 1B][Payload 32B] = 37 bytes
        # We'll scan for potential event patterns
        idx = 0
        events_found = 0

        while idx < len(data) - 36:  # Need at least 37 bytes for an event
            # Look for entity ID followed by 00 00 pattern
            if data[idx+2:idx+4] == b'\x00\x00':
                # Extract entity ID (2 bytes LE)
                entity_id = struct.unpack('<H', data[idx:idx+2])[0]

                # Extract action code (1 byte)
                action_code = data[idx+4]

                # Filter noise: entity IDs should be reasonable (not all zeros, not too high)
                if 0 < entity_id < 0xFFFF and action_code > 0:
                    action_counts[action_code] += 1
                    events_found += 1
                    idx += 37  # Skip to next potential event
                else:
                    idx += 1
            else:
                idx += 1

        return {
            'frame_num': frame_num,
            'action_counts': dict(action_counts),
            'total_events': events_found,
            'file_size': len(data)
        }

    def analyze_all_frames(self) -> None:
        """Parse all frames in the replay directory"""
        print("[STAGE:begin:frame_parsing]")

        # Find all frame files
        frame_files = sorted(self.replay_cache_dir.glob('*.vgr'),
                           key=lambda p: int(p.stem.split('.')[-1]))

        print(f"[DATA] Found {len(frame_files)} frames to analyze")

        for frame_path in frame_files:
            frame_data = self.parse_frame(frame_path)
            self.frames_data.append(frame_data)

            # Update global counts
            for action_code, count in frame_data['action_counts'].items():
                self.global_action_counts[action_code] += count
                self.total_events += count

        print(f"[DATA] Parsed {len(self.frames_data)} frames, {self.total_events} total events")
        print("[STAGE:status:success]")
        print("[STAGE:end:frame_parsing]")

    def identify_rare_codes(self, threshold: float = 0.01) -> List[Tuple[int, int, float]]:
        """Identify rare action codes (< threshold frequency)"""
        print("[STAGE:begin:rare_code_detection]")

        rare_codes = []
        for action_code, count in self.global_action_counts.items():
            frequency = count / self.total_events if self.total_events > 0 else 0
            if frequency < threshold:
                rare_codes.append((action_code, count, frequency))

        # Sort by frequency (rarest first)
        rare_codes.sort(key=lambda x: x[2])

        print(f"[FINDING] Identified {len(rare_codes)} rare action codes (< {threshold*100}% frequency)")
        print(f"[STAT:rare_code_count] {len(rare_codes)}")
        print(f"[STAT:total_unique_codes] {len(self.global_action_counts)}")

        print("[STAGE:status:success]")
        print("[STAGE:end:rare_code_detection]")

        return rare_codes

    def find_transition_frames(self, rare_codes: List[Tuple[int, int, float]]) -> Dict:
        """Find frames where rare codes suddenly appear or disappear"""
        print("[STAGE:begin:transition_detection]")

        rare_code_set = {code for code, _, _ in rare_codes}
        transitions = defaultdict(list)

        for i, frame_data in enumerate(self.frames_data):
            frame_num = frame_data['frame_num']
            current_codes = set(frame_data['action_counts'].keys())

            # Check which rare codes appear in this frame
            rare_in_frame = current_codes & rare_code_set

            if rare_in_frame:
                # Check previous frame
                if i > 0:
                    prev_codes = set(self.frames_data[i-1]['action_counts'].keys())
                    new_codes = rare_in_frame - prev_codes

                    if new_codes:
                        transitions[frame_num].append({
                            'type': 'appearance',
                            'codes': [f"0x{c:02X}" for c in new_codes],
                            'counts': {f"0x{c:02X}": frame_data['action_counts'][c] for c in new_codes}
                        })

                # Check next frame
                if i < len(self.frames_data) - 1:
                    next_codes = set(self.frames_data[i+1]['action_counts'].keys())
                    disappeared_codes = rare_in_frame - next_codes

                    if disappeared_codes:
                        transitions[frame_num].append({
                            'type': 'disappearance',
                            'codes': [f"0x{c:02X}" for c in disappeared_codes],
                            'counts': {f"0x{c:02X}": frame_data['action_counts'][c] for c in disappeared_codes}
                        })

        print(f"[FINDING] Detected {len(transitions)} frames with rare code transitions")
        print(f"[STAT:transition_frames] {len(transitions)}")

        print("[STAGE:status:success]")
        print("[STAGE:end:transition_detection]")

        return dict(transitions)

    def generate_heatmap_data(self) -> Dict:
        """Generate heatmap data: frame x action code matrix"""
        print("[STAGE:begin:heatmap_generation]")

        # Get all unique action codes
        all_codes = sorted(self.global_action_counts.keys())

        # Build matrix
        heatmap = []
        for frame_data in self.frames_data:
            frame_row = {
                'frame_num': frame_data['frame_num'],
                'codes': {f"0x{code:02X}": frame_data['action_counts'].get(code, 0)
                         for code in all_codes}
            }
            heatmap.append(frame_row)

        print(f"[DATA] Generated heatmap: {len(self.frames_data)} frames x {len(all_codes)} action codes")
        print(f"[STAT:heatmap_dimensions] {len(self.frames_data)}x{len(all_codes)}")

        print("[STAGE:status:success]")
        print("[STAGE:end:heatmap_generation]")

        return {
            'frames': len(self.frames_data),
            'action_codes': len(all_codes),
            'data': heatmap
        }

    def correlate_with_death_candidates(self, sudden_drops: Dict) -> Dict:
        """Cross-reference rare code appearances with sudden drop frames"""
        print("[STAGE:begin:death_correlation]")

        death_candidate_frames = set()
        for player_name, player_data in sudden_drops.items():
            for drop in player_data.get('sudden_drops', []):
                death_candidate_frames.add(drop[0])  # frame_num is first element

        print(f"[DATA] {len(death_candidate_frames)} death candidate frames from sudden drops")

        # Analyze action code distribution in death candidates vs normal frames
        death_frame_codes = Counter()
        normal_frame_codes = Counter()

        death_frame_count = 0
        normal_frame_count = 0

        for frame_data in self.frames_data:
            if frame_data['frame_num'] in death_candidate_frames:
                for code, count in frame_data['action_counts'].items():
                    death_frame_codes[code] += count
                death_frame_count += 1
            else:
                for code, count in frame_data['action_counts'].items():
                    normal_frame_codes[code] += count
                normal_frame_count += 1

        # Calculate enrichment: (death_freq / normal_freq)
        enrichment = {}
        total_death = sum(death_frame_codes.values())
        total_normal = sum(normal_frame_codes.values())

        all_codes = set(death_frame_codes.keys()) | set(normal_frame_codes.keys())

        for code in all_codes:
            death_freq = death_frame_codes[code] / total_death if total_death > 0 else 0
            normal_freq = normal_frame_codes[code] / total_normal if total_normal > 0 else 0

            if normal_freq > 0:
                enrichment_ratio = death_freq / normal_freq
            else:
                enrichment_ratio = float('inf') if death_freq > 0 else 1.0

            enrichment[code] = {
                'death_count': death_frame_codes[code],
                'normal_count': normal_frame_codes[code],
                'death_freq': death_freq,
                'normal_freq': normal_freq,
                'enrichment_ratio': enrichment_ratio
            }

        # Find top enriched codes
        enriched_codes = sorted(
            [(code, data) for code, data in enrichment.items()],
            key=lambda x: x[1]['enrichment_ratio'],
            reverse=True
        )[:20]  # Top 20

        print(f"[FINDING] Death frame analysis: {death_frame_count} death frames vs {normal_frame_count} normal frames")
        print(f"[STAT:death_frames] {death_frame_count}")
        print(f"[STAT:normal_frames] {normal_frame_count}")

        # Report top enriched codes
        for code, data in enriched_codes[:5]:
            if data['enrichment_ratio'] != float('inf') and data['enrichment_ratio'] > 1.5:
                print(f"[FINDING] Action 0x{code:02X} enriched {data['enrichment_ratio']:.2f}x in death frames")
                print(f"[STAT:enrichment_0x{code:02X}] {data['enrichment_ratio']:.2f}")

        print("[STAGE:status:success]")
        print("[STAGE:end:death_correlation]")

        return {
            'death_candidate_frames': sorted(death_candidate_frames),
            'death_frame_count': death_frame_count,
            'normal_frame_count': normal_frame_count,
            'enrichment_analysis': {f"0x{code:02X}": data for code, data in enriched_codes}
        }

    def generate_report(self, output_path: str, anomaly_data: Dict) -> None:
        """Generate comprehensive analysis report"""
        print("[STAGE:begin:report_generation]")

        # Identify rare codes
        rare_codes = self.identify_rare_codes(threshold=0.01)

        # Find transition frames
        transitions = self.find_transition_frames(rare_codes)

        # Generate heatmap
        heatmap = self.generate_heatmap_data()

        # Correlate with death candidates
        correlation = self.correlate_with_death_candidates(anomaly_data.get('player_activities', {}))

        # Build comprehensive report
        report = {
            'metadata': {
                'replay_name': self.replay_cache_dir.name,
                'total_frames': len(self.frames_data),
                'total_events': self.total_events,
                'unique_action_codes': len(self.global_action_counts)
            },
            'global_action_distribution': {
                f"0x{code:02X}": {
                    'count': count,
                    'frequency': count / self.total_events if self.total_events > 0 else 0
                }
                for code, count in self.global_action_counts.most_common()
            },
            'rare_action_codes': [
                {
                    'code': f"0x{code:02X}",
                    'count': count,
                    'frequency': freq,
                    'percentage': freq * 100
                }
                for code, count, freq in rare_codes
            ],
            'transition_frames': transitions,
            'heatmap_data': heatmap,
            'death_frame_correlation': correlation
        }

        # Save report
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        print(f"[FINDING] Report saved to {output_path}")
        print("[STAGE:status:success]")
        print("[STAGE:end:report_generation]")


def main():
    print("[OBJECTIVE] Identify rare action codes and distribution anomalies in death frames vs normal frames")

    # Paths
    replay_cache_dir = "D:/Desktop/My Folder/Game/VG/vg replay/21.11.04/cache"
    output_path = "D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/death_frame_distribution.json"
    anomaly_path = "D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/frame_anomaly_analysis.json"

    # Load anomaly data for death candidates
    with open(anomaly_path, 'r', encoding='utf-8') as f:
        anomaly_data = json.load(f)

    # Run analysis
    analyzer = DeathFrameAnalyzer(replay_cache_dir)
    analyzer.analyze_all_frames()
    analyzer.generate_report(output_path, anomaly_data)

    print("\n[FINDING] Analysis complete - check output for rare code patterns")
    print(f"[LIMITATION] Event parsing is heuristic - 37-byte alignment may miss some events")
    print(f"[LIMITATION] Entity ID filtering (0 < ID < 0xFFFF) may exclude valid events")


if __name__ == '__main__':
    main()
