#!/usr/bin/env python3
"""
Gold Kill Correlator - Reverse engineer Gold field encoding in KillActor events

Strategy:
1. Parse all frames from 21.11.04 replay
2. Extract all player events (entity_id based)
3. Scan each 32-byte payload for uint16 LE values in 150-500 range (hero kill gold)
4. Map offset positions where these values appear
5. Correlate with truth data kill timestamps
6. Distinguish kill gold (150-500) from minion gold (35-80) and turret gold (300)
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
        56325: {"name": "Phinn", "kills": 2, "deaths": 0},
        56581: {"name": "Yates", "kills": 1, "deaths": 4},
        56837: {"name": "Caine", "kills": 3, "deaths": 4},
        57093: {"name": "Petal", "kills": 3, "deaths": 2},
        57349: {"name": "Karas", "kills": 0, "deaths": 3},
        57605: {"name": "Baron", "kills": 6, "deaths": 2},
    }
}

# Gold ranges
HERO_KILL_GOLD_RANGE = (150, 500)
MINION_GOLD_RANGE = (35, 80)
JUNGLE_GOLD_RANGE = (45, 120)
TURRET_GOLD = 300


class GoldKillCorrelator:
    """Correlate gold values in binary payloads with kill events"""

    def __init__(self, replay_cache_path: str):
        self.replay_path = Path(replay_cache_path)
        self.frames_data = b""
        self.event_candidates = []
        self.offset_frequency = defaultdict(Counter)

    def load_all_frames(self) -> None:
        """Load all .vgr frames in sequential order"""
        print(f"[STAGE:begin:data_loading]")
        start_time = datetime.now()

        # Find all .vgr files
        vgr_files = sorted(self.replay_path.glob("*.vgr"))

        # Sort by frame index (extract number before .vgr)
        def get_frame_index(path: Path) -> int:
            parts = path.stem.split('.')
            try:
                return int(parts[-1])
            except (ValueError, IndexError):
                return 0

        vgr_files.sort(key=get_frame_index)

        print(f"[DATA] Found {len(vgr_files)} frame files")

        # Concatenate all frames
        frame_data_list = []
        for frame_file in vgr_files:
            frame_data_list.append(frame_file.read_bytes())

        self.frames_data = b"".join(frame_data_list)

        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"[DATA] Loaded {len(self.frames_data):,} bytes from {len(vgr_files)} frames")
        print(f"[STAGE:status:success]")
        print(f"[STAGE:time:{elapsed:.2f}]")
        print(f"[STAGE:end:data_loading]")

    def scan_for_gold_values(self, min_gold: int = 150, max_gold: int = 500) -> None:
        """
        Scan all 32-byte windows for uint16 LE values in gold range.
        Map which byte offsets (0-30) contain gold-like values.
        """
        print(f"\n[STAGE:begin:gold_scanning]")
        start_time = datetime.now()

        print(f"[OBJECTIVE] Scan for uint16 values in range [{min_gold}, {max_gold}]")

        # Scan every 32-byte window in the data
        # Assuming events are aligned on some boundary, but we'll scan densely
        window_size = 32
        gold_hits = []

        total_windows = len(self.frames_data) - window_size
        print(f"[DATA] Scanning {total_windows:,} possible 32-byte windows")

        for window_start in range(0, len(self.frames_data) - window_size, 1):
            window = self.frames_data[window_start:window_start + window_size]

            # Check all 2-byte positions (0-30) for uint16 LE
            for offset in range(0, window_size - 1):
                value = struct.unpack_from('<H', window, offset)[0]

                if min_gold <= value <= max_gold:
                    # Record this hit
                    gold_hits.append({
                        'window_start': window_start,
                        'offset_in_window': offset,
                        'absolute_position': window_start + offset,
                        'value': value,
                        'window_hex': window.hex()
                    })

                    # Track frequency of this offset position
                    self.offset_frequency[offset][value] += 1

        self.event_candidates = gold_hits

        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"[FINDING] Found {len(gold_hits):,} uint16 values in range [{min_gold}, {max_gold}]")
        print(f"[STAT:total_gold_hits] {len(gold_hits)}")
        print(f"[STAT:scan_time_seconds] {elapsed:.2f}")
        print(f"[STAGE:status:success]")
        print(f"[STAGE:time:{elapsed:.2f}]")
        print(f"[STAGE:end:gold_scanning]")

    def analyze_offset_patterns(self) -> Dict[int, Dict]:
        """Analyze which offsets have the most gold-range hits"""
        print(f"\n[STAGE:begin:offset_analysis]")
        start_time = datetime.now()

        offset_stats = {}

        for offset in range(32):
            if offset in self.offset_frequency:
                values = self.offset_frequency[offset]
                total_hits = sum(values.values())
                unique_values = len(values)
                most_common = values.most_common(5)

                offset_stats[offset] = {
                    'total_hits': total_hits,
                    'unique_values': unique_values,
                    'most_common': most_common,
                    'all_values': dict(values)
                }

        # Sort by total hits
        sorted_offsets = sorted(
            offset_stats.items(),
            key=lambda x: x[1]['total_hits'],
            reverse=True
        )

        print(f"[FINDING] Offset position frequency analysis:")
        for offset, stats in sorted_offsets[:10]:
            print(f"  Offset {offset:2d}: {stats['total_hits']:5d} hits, "
                  f"{stats['unique_values']:3d} unique values")
            top_3 = stats['most_common'][:3]
            for value, count in top_3:
                print(f"    Value {value:3d}: {count:4d} times")

        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"[STAT:offsets_with_hits] {len(offset_stats)}")
        print(f"[STAGE:status:success]")
        print(f"[STAGE:time:{elapsed:.2f}]")
        print(f"[STAGE:end:offset_analysis]")

        return offset_stats

    def filter_by_kill_count(self, offset_stats: Dict) -> List[Tuple[int, Dict]]:
        """
        Filter offsets where total hits roughly match expected kill count.

        Truth data: 15 total kills
        Expected: offset with ~15-30 hits (accounting for both killer and victim events)
        """
        print(f"\n[STAGE:begin:kill_count_filtering]")
        start_time = datetime.now()

        expected_min = 10
        expected_max = 50

        print(f"[OBJECTIVE] Filter offsets with hit count near expected kill count")
        print(f"[DATA] Truth data: {TRUTH_DATA['total_kills']} kills, {TRUTH_DATA['total_deaths']} deaths")
        print(f"[DATA] Expected hit range: {expected_min}-{expected_max} (accounting for killer/victim events)")

        candidates = []
        for offset, stats in offset_stats.items():
            if expected_min <= stats['total_hits'] <= expected_max:
                candidates.append((offset, stats))

        candidates.sort(key=lambda x: x[1]['total_hits'])

        print(f"[FINDING] {len(candidates)} offset positions match kill count range:")
        for offset, stats in candidates:
            print(f"  Offset {offset:2d}: {stats['total_hits']:3d} hits")

        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"[STAT:candidate_offsets] {len(candidates)}")
        print(f"[STAGE:status:success]")
        print(f"[STAGE:time:{elapsed:.2f}]")
        print(f"[STAGE:end:kill_count_filtering]")

        return candidates

    def extract_event_payloads_at_offset(self, offset: int) -> List[Dict]:
        """
        Extract all 32-byte payloads where gold value appears at specified offset.
        """
        print(f"\n[STAGE:begin:payload_extraction]")
        start_time = datetime.now()

        print(f"[OBJECTIVE] Extract full 32-byte payloads for offset {offset}")

        payloads = []
        for hit in self.event_candidates:
            if hit['offset_in_window'] == offset:
                window_start = hit['window_start']
                payload = self.frames_data[window_start:window_start + 32]

                payloads.append({
                    'absolute_position': window_start,
                    'gold_value': hit['value'],
                    'payload_hex': payload.hex(),
                    'payload_bytes': list(payload),
                })

        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"[FINDING] Extracted {len(payloads)} payloads with gold at offset {offset}")
        print(f"[STAT:payloads_extracted] {len(payloads)}")
        print(f"[STAGE:status:success]")
        print(f"[STAGE:time:{elapsed:.2f}]")
        print(f"[STAGE:end:payload_extraction]")

        return payloads

    def analyze_payload_patterns(self, payloads: List[Dict]) -> Dict:
        """Analyze common patterns in extracted payloads"""
        print(f"\n[STAGE:begin:pattern_analysis]")
        start_time = datetime.now()

        # Analyze each byte position
        byte_patterns = defaultdict(Counter)

        for payload_info in payloads:
            payload_bytes = payload_info['payload_bytes']
            for pos, byte_val in enumerate(payload_bytes):
                byte_patterns[pos][byte_val] += 1

        # Find positions with low entropy (fixed values)
        fixed_positions = {}
        for pos in range(32):
            if pos in byte_patterns:
                most_common = byte_patterns[pos].most_common(1)[0]
                value, count = most_common
                if count / len(payloads) > 0.8:  # 80% same value
                    fixed_positions[pos] = {
                        'value': value,
                        'frequency': count / len(payloads)
                    }

        print(f"[FINDING] Found {len(fixed_positions)} byte positions with consistent values:")
        for pos, info in sorted(fixed_positions.items()):
            print(f"  Byte {pos:2d}: 0x{info['value']:02X} ({info['frequency']:.1%} consistent)")

        elapsed = (datetime.now() - start_time).total_seconds()
        print(f"[STAGE:status:success]")
        print(f"[STAGE:time:{elapsed:.2f}]")
        print(f"[STAGE:end:pattern_analysis]")

        return {
            'byte_patterns': {k: dict(v) for k, v in byte_patterns.items()},
            'fixed_positions': fixed_positions
        }

    def save_results(self, output_path: str, offset_stats: Dict,
                     candidate_offsets: List, payloads: List[Dict],
                     pattern_analysis: Dict) -> None:
        """Save analysis results to JSON"""
        print(f"\n[STAGE:begin:save_results]")
        start_time = datetime.now()

        output = {
            'metadata': {
                'replay_path': str(self.replay_path),
                'total_bytes': len(self.frames_data),
                'analysis_timestamp': datetime.now().isoformat(),
                'truth_data': TRUTH_DATA,
            },
            'gold_scan_summary': {
                'total_hits': len(self.event_candidates),
                'gold_range': HERO_KILL_GOLD_RANGE,
                'offsets_analyzed': len(offset_stats),
            },
            'offset_frequency': {
                str(k): v for k, v in offset_stats.items()
            },
            'candidate_offsets': [
                {
                    'offset': offset,
                    'total_hits': stats['total_hits'],
                    'unique_values': stats['unique_values'],
                    'most_common': stats['most_common']
                }
                for offset, stats in candidate_offsets
            ],
            'sample_payloads': payloads[:100],  # Limit to first 100
            'pattern_analysis': pattern_analysis,
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
    """Execute gold kill correlation analysis"""
    print("[OBJECTIVE] Identify Gold field encoding in KillActor event payloads")
    print(f"[DATA] Analyzing replay: 21.11.04")
    print(f"[DATA] Truth data: {TRUTH_DATA['total_kills']} kills across 6 players\n")

    replay_cache = "D:/Desktop/My Folder/Game/VG/vg replay/21.11.04/cache/"
    output_path = "D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/gold_kill_correlation.json"

    correlator = GoldKillCorrelator(replay_cache)

    # Phase 1: Load all frames
    correlator.load_all_frames()

    # Phase 2: Scan for gold values
    correlator.scan_for_gold_values(
        min_gold=HERO_KILL_GOLD_RANGE[0],
        max_gold=HERO_KILL_GOLD_RANGE[1]
    )

    # Phase 3: Analyze offset patterns
    offset_stats = correlator.analyze_offset_patterns()

    # Phase 4: Filter by expected kill count
    candidate_offsets = correlator.filter_by_kill_count(offset_stats)

    # Phase 5: Deep dive into most promising offset
    if candidate_offsets:
        best_offset, best_stats = candidate_offsets[0]
        print(f"\n[FINDING] Best candidate offset: {best_offset} ({best_stats['total_hits']} hits)")

        payloads = correlator.extract_event_payloads_at_offset(best_offset)
        pattern_analysis = correlator.analyze_payload_patterns(payloads)
    else:
        print(f"\n[LIMITATION] No offsets matched expected kill count")
        payloads = []
        pattern_analysis = {}

    # Phase 6: Save results
    correlator.save_results(output_path, offset_stats, candidate_offsets,
                            payloads, pattern_analysis)

    print(f"\n[FINDING] Analysis complete - results saved to vg/output/gold_kill_correlation.json")
    print(f"[LIMITATION] This analysis assumes gold values are encoded as uint16 LE")
    print(f"[LIMITATION] May need to check uint32, float32, or BCD encoding if no clear pattern found")


if __name__ == '__main__':
    main()
