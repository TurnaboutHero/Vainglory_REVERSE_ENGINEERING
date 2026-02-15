#!/usr/bin/env python3
"""
Cross-Validation Analysis: Death-Exclusive Action Codes
Validates whether action codes 0x61, 0x81, 0x82, 0x85 appear exclusively in death contexts across multiple replays.
"""

import os
import sys
import json
import struct
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Set

# Add project root to path
sys.path.insert(0, 'D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg')

from core.vgr_parser import VGRParser

# Death-exclusive codes from baseline analysis
DEATH_CODES = {0x61, 0x81, 0x82, 0x85}

class DeathCodeValidator:
    def __init__(self, replay_dir: str, replay_name: str):
        self.replay_dir = replay_dir
        self.replay_name = replay_name
        self.results = {
            'replay_name': replay_name,
            'total_frames': 0,
            'frames_with_death_codes': 0,
            'death_candidate_frames': 0,
            'overlap_frames': 0,
            'precision': 0.0,
            'recall': 0.0,
            'death_code_occurrences': {hex(code): 0 for code in DEATH_CODES},
            'non_death_occurrences': [],
            'death_code_details': []
        }

    def get_frame_files(self) -> List[Tuple[int, str]]:
        """Get all VGR frame files sorted by frame number."""
        frames = []

        # Check if this is tournament replay (VGR files in root) or regular (cache/ subdirectory)
        cache_dir = os.path.join(self.replay_dir, 'cache')
        if os.path.exists(cache_dir):
            search_dir = cache_dir
        else:
            search_dir = self.replay_dir

        for file in os.listdir(search_dir):
            if file.endswith('.vgr'):
                parts = file.split('.')
                if len(parts) >= 2:
                    try:
                        frame_num = int(parts[-2])
                        frames.append((frame_num, os.path.join(search_dir, file)))
                    except ValueError:
                        continue

        frames.sort(key=lambda x: x[0])
        print(f"[DATA] Found {len(frames)} VGR frames in {search_dir}")
        return frames

    def get_player_entity_ids(self) -> Set[int]:
        """Extract player entity IDs from replay metadata."""
        try:
            parser = VGRParser(self.replay_dir, detect_heroes=False)
            data = parser.parse()

            entity_ids = set()
            for player in data.get('players', []):
                if player.get('entity_id'):
                    entity_ids.add(player['entity_id'])

            print(f"[DATA] Found {len(entity_ids)} player entity IDs: {sorted(entity_ids)}")
            return entity_ids
        except Exception as e:
            print(f"[LIMITATION] Could not parse player entity IDs: {e}")
            # Fallback: assume player entities are in 50000-60000 range
            return set(range(50000, 60000))

    def extract_player_events(self, frame_data: bytes, player_ids: Set[int]) -> Dict[int, List[int]]:
        """
        Extract player events from frame data.
        Pattern: [entity_id_2bytes_LE][00 00][action_code]
        Returns: {entity_id: [action_codes]}
        """
        events = defaultdict(list)

        i = 0
        while i < len(frame_data) - 4:
            # Read entity ID (2 bytes, little-endian)
            entity_id = struct.unpack_from('<H', frame_data, i)[0]

            # Check if this looks like player event pattern
            if i + 4 < len(frame_data):
                next_bytes = frame_data[i+2:i+4]
                if next_bytes == b'\x00\x00' and entity_id in player_ids:
                    # Read action code
                    if i + 4 < len(frame_data):
                        action_code = frame_data[i+4]
                        events[entity_id].append(action_code)
                        i += 5
                        continue
            i += 1

        return events

    def detect_death_candidate_frames(self, frame_files: List[Tuple[int, str]], player_ids: Set[int]) -> Set[int]:
        """
        Detect frames that are likely death events using sudden drop heuristic.
        Death frames show >50% drop in event count.
        """
        death_candidates = set()
        prev_event_count = 0

        for frame_num, frame_path in frame_files:
            try:
                with open(frame_path, 'rb') as f:
                    data = f.read()

                events = self.extract_player_events(data, player_ids)
                total_events = sum(len(codes) for codes in events.values())

                # Check for sudden drop
                if prev_event_count > 0:
                    drop_ratio = (prev_event_count - total_events) / prev_event_count
                    if drop_ratio > 0.5 and total_events < prev_event_count:
                        death_candidates.add(frame_num)

                prev_event_count = total_events

            except Exception as e:
                print(f"[LIMITATION] Error processing frame {frame_num}: {e}")
                continue

        print(f"[FINDING] Detected {len(death_candidates)} death candidate frames using drop heuristic")
        return death_candidates

    def analyze_replay(self):
        """Main analysis routine."""
        print(f"\n[OBJECTIVE] Cross-validate death-exclusive codes for replay: {self.replay_name}")

        # Get frame files
        frame_files = self.get_frame_files()
        if not frame_files:
            print(f"[LIMITATION] No VGR frames found in {self.replay_dir}")
            return self.results

        self.results['total_frames'] = len(frame_files)

        # Get player entity IDs
        player_ids = self.get_player_entity_ids()

        # Detect death candidate frames
        death_candidates = self.detect_death_candidate_frames(frame_files, player_ids)
        self.results['death_candidate_frames'] = len(death_candidates)

        # Scan all frames for death codes
        frames_with_codes = set()

        for frame_num, frame_path in frame_files:
            try:
                with open(frame_path, 'rb') as f:
                    data = f.read()

                events = self.extract_player_events(data, player_ids)

                # Check for death codes
                frame_has_death_code = False
                for entity_id, codes in events.items():
                    for code in codes:
                        if code in DEATH_CODES:
                            frame_has_death_code = True
                            self.results['death_code_occurrences'][hex(code)] += 1

                            # Record details
                            detail = {
                                'frame': frame_num,
                                'entity_id': entity_id,
                                'code': hex(code),
                                'is_death_candidate': frame_num in death_candidates
                            }
                            self.results['death_code_details'].append(detail)

                            # Check if this is in NON-death frame
                            if frame_num not in death_candidates:
                                self.results['non_death_occurrences'].append(detail)

                if frame_has_death_code:
                    frames_with_codes.add(frame_num)

            except Exception as e:
                print(f"[LIMITATION] Error scanning frame {frame_num}: {e}")
                continue

        self.results['frames_with_death_codes'] = len(frames_with_codes)

        # Calculate overlap
        overlap = frames_with_codes & death_candidates
        self.results['overlap_frames'] = len(overlap)

        # Calculate precision and recall
        if len(frames_with_codes) > 0:
            self.results['precision'] = len(overlap) / len(frames_with_codes)

        if len(death_candidates) > 0:
            self.results['recall'] = len(overlap) / len(death_candidates)

        # Report findings
        print(f"[FINDING] Frames with death codes: {len(frames_with_codes)}")
        print(f"[FINDING] Death candidate frames: {len(death_candidates)}")
        print(f"[FINDING] Overlap (codes in death frames): {len(overlap)}")
        print(f"[STAT:precision] {self.results['precision']:.2%}")
        print(f"[STAT:recall] {self.results['recall']:.2%}")

        # Report code distribution
        for code_hex, count in self.results['death_code_occurrences'].items():
            if count > 0:
                print(f"[STAT:{code_hex}_count] {count}")

        # Report non-death occurrences
        if self.results['non_death_occurrences']:
            print(f"[FINDING] Found {len(self.results['non_death_occurrences'])} death code occurrences in NON-death frames!")
            for occ in self.results['non_death_occurrences'][:5]:  # Show first 5
                print(f"  Frame {occ['frame']}: entity {occ['entity_id']} code {occ['code']}")
        else:
            print(f"[FINDING] All death codes appeared ONLY in death candidate frames (100% exclusivity)")

        return self.results


def main():
    print("[STAGE:begin:cross_validation]")
    import time
    start_time = time.time()

    # Define replays to analyze
    regular_replays = [
        ("21.11.04", "D:/Desktop/My Folder/Game/VG/vg replay/21.11.04"),
        ("21.11.17", "D:/Desktop/My Folder/Game/VG/vg replay/21.11.17"),
        ("21.11.21", "D:/Desktop/My Folder/Game/VG/vg replay/21.11.21"),
        ("21.11.22", "D:/Desktop/My Folder/Game/VG/vg replay/21.11.22"),
        ("21.12.02", "D:/Desktop/My Folder/Game/VG/vg replay/21.12.02"),
    ]

    # Tournament replays (pick 3-4)
    tournament_base = "D:/Desktop/My Folder/Game/VG/vg replay/Tournament_Replays"
    tournament_replays = []

    if os.path.exists(tournament_base):
        subdirs = [d for d in os.listdir(tournament_base)
                   if os.path.isdir(os.path.join(tournament_base, d))]
        # Take first 4 tournament replays
        for subdir in subdirs[:4]:
            game1_path = os.path.join(tournament_base, subdir, "1")
            if os.path.exists(game1_path):
                tournament_replays.append((f"Tournament_{subdir}_G1", game1_path))

    all_replays = regular_replays + tournament_replays

    print(f"[DATA] Analyzing {len(all_replays)} replays total")
    print(f"[DATA] Regular replays: {len(regular_replays)}")
    print(f"[DATA] Tournament replays: {len(tournament_replays)}")

    # Analyze each replay
    all_results = []

    for name, path in all_replays:
        if not os.path.exists(path):
            print(f"[LIMITATION] Replay not found: {path}")
            continue

        validator = DeathCodeValidator(path, name)
        result = validator.analyze_replay()
        all_results.append(result)

    # Aggregate findings
    print(f"\n{'='*80}")
    print("[STAGE:end:cross_validation]")
    print("[STAGE:begin:synthesis]")

    total_frames = sum(r['total_frames'] for r in all_results)
    total_code_frames = sum(r['frames_with_death_codes'] for r in all_results)
    total_death_candidates = sum(r['death_candidate_frames'] for r in all_results)
    total_overlaps = sum(r['overlap_frames'] for r in all_results)
    total_non_death = sum(len(r['non_death_occurrences']) for r in all_results)

    print(f"\n[FINDING] AGGREGATE CROSS-VALIDATION RESULTS")
    print(f"[STAT:total_replays] {len(all_results)}")
    print(f"[STAT:total_frames] {total_frames}")
    print(f"[STAT:frames_with_death_codes] {total_code_frames}")
    print(f"[STAT:death_candidate_frames] {total_death_candidates}")
    print(f"[STAT:overlap_frames] {total_overlaps}")

    # Overall precision/recall
    overall_precision = total_overlaps / total_code_frames if total_code_frames > 0 else 0
    overall_recall = total_overlaps / total_death_candidates if total_death_candidates > 0 else 0

    print(f"[STAT:overall_precision] {overall_precision:.2%}")
    print(f"[STAT:overall_recall] {overall_recall:.2%}")
    print(f"[STAT:non_death_occurrences] {total_non_death}")

    if total_non_death == 0:
        print(f"\n[FINDING] ✓ VALIDATION SUCCESS: Death codes appear EXCLUSIVELY in death contexts across ALL {len(all_results)} replays")
        print(f"[FINDING] ✓ 100% precision maintained across {total_code_frames} death code occurrences")
    else:
        print(f"\n[FINDING] ✗ VALIDATION FAILED: Found {total_non_death} death code occurrences in non-death frames")
        print(f"[LIMITATION] Death codes are NOT 100% exclusive to death contexts")

    # Code-specific statistics
    code_totals = defaultdict(int)
    for result in all_results:
        for code_hex, count in result['death_code_occurrences'].items():
            code_totals[code_hex] += count

    print(f"\n[FINDING] Code distribution across all replays:")
    for code_hex in sorted(code_totals.keys()):
        print(f"  {code_hex}: {code_totals[code_hex]} occurrences")

    # Save results
    output_path = "D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/cross_validation_death_codes.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    summary = {
        'analysis_timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'total_replays': len(all_results),
        'aggregate_stats': {
            'total_frames': total_frames,
            'frames_with_death_codes': total_code_frames,
            'death_candidate_frames': total_death_candidates,
            'overlap_frames': total_overlaps,
            'overall_precision': overall_precision,
            'overall_recall': overall_recall,
            'non_death_occurrences': total_non_death,
            'code_distribution': dict(code_totals)
        },
        'per_replay_results': all_results
    }

    with open(output_path, 'w') as f:
        json.dump(summary, f, indent=2)

    print(f"\n[FINDING] Results saved to {output_path}")

    elapsed = time.time() - start_time
    print(f"[STAGE:status:success]")
    print(f"[STAGE:time:{elapsed:.2f}]")
    print("[STAGE:end:synthesis]")

    return summary


if __name__ == '__main__':
    main()
