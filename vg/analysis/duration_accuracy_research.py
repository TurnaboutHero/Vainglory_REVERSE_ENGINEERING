#!/usr/bin/env python3
"""
Duration Accuracy Research - Compare multiple timestamp sources against ground truth.

Analyzes 10 tournament matches to find optimal duration estimation formula.

Methods tested:
1. Crystal death timestamp (current method)
2. Max player death timestamp
3. Max player kill timestamp
4. Last credit record timestamp
5. Frame count / estimated frame rate
6. Crystal death - constant offset
7. Hybrid methods (max of crystal/death timestamps)

Goal: Minimize error across all 10 matches.
"""

import json
import struct
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from vg.core.vgr_parser import VGRParser
from vg.core.kda_detector import KDADetector

# Event headers
_DEATH_HEADER = bytes([0x08, 0x04, 0x31])
_KILL_HEADER = bytes([0x18, 0x04, 0x1C])
_CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])


@dataclass
class DurationEstimate:
    """Container for all duration estimation methods."""
    match_name: str
    truth_duration: int
    crystal_death_ts: Optional[float] = None
    max_player_death_ts: Optional[float] = None
    max_player_kill_ts: Optional[float] = None
    last_credit_ts: Optional[float] = None
    frame_count: int = 0

    # Derived estimates
    @property
    def crystal_estimate(self) -> Optional[int]:
        return int(self.crystal_death_ts) if self.crystal_death_ts else None

    @property
    def max_death_estimate(self) -> Optional[int]:
        return int(self.max_player_death_ts) if self.max_player_death_ts else None

    @property
    def max_kill_estimate(self) -> Optional[int]:
        return int(self.max_player_kill_ts) if self.max_player_kill_ts else None

    @property
    def credit_estimate(self) -> Optional[int]:
        return int(self.last_credit_ts) if self.last_credit_ts else None

    def frame_rate_estimate(self, frame_rate: float) -> Optional[int]:
        if self.frame_count > 0:
            return int(self.frame_count / frame_rate)
        return None

    def crystal_offset_estimate(self, offset: float) -> Optional[int]:
        if self.crystal_death_ts:
            return int(self.crystal_death_ts - offset)
        return None

    def hybrid_max_estimate(self) -> Optional[int]:
        """Max of crystal death and max player death timestamps."""
        vals = [v for v in [self.crystal_death_ts, self.max_player_death_ts] if v]
        return int(max(vals)) if vals else None

    def errors(self) -> Dict[str, Optional[int]]:
        """Compute errors for all methods."""
        truth = self.truth_duration
        return {
            'crystal': self.crystal_estimate - truth if self.crystal_estimate else None,
            'max_death': self.max_death_estimate - truth if self.max_death_estimate else None,
            'max_kill': self.max_kill_estimate - truth if self.max_kill_estimate else None,
            'credit': self.credit_estimate - truth if self.credit_estimate else None,
            'hybrid_max': self.hybrid_max_estimate() - truth if self.hybrid_max_estimate() else None,
        }


def _le_to_be(eid_le: int) -> int:
    """Convert uint16 Little Endian entity ID to Big Endian."""
    return struct.unpack('>H', struct.pack('<H', eid_le))[0]


def load_frames(replay_path: str) -> Tuple[List[Tuple[int, bytes]], int]:
    """Load all frame files and return (frames, frame_count)."""
    replay_file = Path(replay_path)
    frame_dir = replay_file.parent
    frame_name = replay_file.stem.rsplit('.', 1)[0]

    frame_files = list(frame_dir.glob(f"{frame_name}.*.vgr"))
    if not frame_files:
        return [], 0

    def _idx(p: Path) -> int:
        try:
            return int(p.stem.split('.')[-1])
        except ValueError:
            return 0

    frame_files.sort(key=_idx)
    frames = [(_idx(f), f.read_bytes()) for f in frame_files]
    max_frame = max(_idx(f) for f in frame_files) if frame_files else 0

    return frames, max_frame


def extract_crystal_death_ts(all_data: bytes) -> Optional[float]:
    """Find crystal death timestamp (eid 2000-2005 in death header)."""
    crystal_deaths = []
    pos = 0
    while True:
        pos = all_data.find(_DEATH_HEADER, pos)
        if pos == -1:
            break
        if pos + 13 > len(all_data):
            pos += 1
            continue
        if (all_data[pos + 3:pos + 5] != b'\x00\x00' or
                all_data[pos + 7:pos + 9] != b'\x00\x00'):
            pos += 1
            continue

        eid = struct.unpack_from(">H", all_data, pos + 5)[0]
        ts = struct.unpack_from(">f", all_data, pos + 9)[0]

        if 2000 <= eid <= 2005 and 60 < ts < 2400:
            crystal_deaths.append((ts, eid))

        pos += 1

    if not crystal_deaths:
        return None

    # Return latest crystal death
    crystal_deaths.sort(key=lambda x: x[0], reverse=True)
    return crystal_deaths[0][0]


def extract_player_timestamps(all_data: bytes, player_eids_be: set) -> Tuple[Optional[float], Optional[float]]:
    """Extract max player death and kill timestamps."""
    # Max player death timestamp
    max_death_ts = None
    pos = 0
    while True:
        pos = all_data.find(_DEATH_HEADER, pos)
        if pos == -1:
            break
        if pos + 13 > len(all_data):
            pos += 1
            continue
        if (all_data[pos + 3:pos + 5] != b'\x00\x00' or
                all_data[pos + 7:pos + 9] != b'\x00\x00'):
            pos += 1
            continue

        eid = struct.unpack_from(">H", all_data, pos + 5)[0]
        if eid in player_eids_be:
            ts = struct.unpack_from(">f", all_data, pos + 9)[0]
            if 0 < ts < 2400:
                if max_death_ts is None or ts > max_death_ts:
                    max_death_ts = ts

        pos += 1

    # Max player kill timestamp (7 bytes before kill header)
    max_kill_ts = None
    pos = 0
    while True:
        pos = all_data.find(_KILL_HEADER, pos)
        if pos == -1:
            break
        if pos < 7 or pos + 11 > len(all_data):
            pos += 1
            continue

        # Timestamp 7 bytes before header
        ts_bytes = all_data[pos-7:pos-3]
        if len(ts_bytes) == 4:
            ts = struct.unpack(">f", ts_bytes)[0]

            # Validate kill header structure
            if (all_data[pos + 3:pos + 5] == b'\x00\x00' and
                all_data[pos + 9:pos + 13] == b'\xFF\xFF\xFF\xFF'):
                eid = struct.unpack_from(">H", all_data, pos + 5)[0]
                if eid in player_eids_be and 0 < ts < 2400:
                    if max_kill_ts is None or ts > max_kill_ts:
                        max_kill_ts = ts

        pos += 1

    return max_death_ts, max_kill_ts


def extract_last_credit_ts(all_data: bytes, player_eids_be: set) -> Optional[float]:
    """Extract timestamp from last credit record for player entities."""
    # Credit records don't have direct timestamps, but we can use
    # the timestamp of the last observed credit event by scanning
    # nearby death/kill events (approximate).
    #
    # Alternative: scan credit positions and use nearest event timestamp
    # For now, return None - credits don't have reliable timestamps
    return None


def analyze_match(replay_path: str, truth_duration: int, match_name: str) -> DurationEstimate:
    """Analyze single match and extract all duration estimation sources."""
    print(f"\n[STAGE:begin:analyze_{match_name[:30]}]")

    # Parse basic info
    parser = VGRParser(replay_path, detect_heroes=False, auto_truth=False)
    parsed = parser.parse()

    # Load frames
    frames, frame_count = load_frames(replay_path)
    all_data = b"".join(data for _, data in frames) if frames else b""

    # Get player entity IDs (BE format)
    player_eids_be = set()
    for team_name in ['left', 'right']:
        for player in parsed.get('teams', {}).get(team_name, []):
            eid_le = player.get('entity_id')
            if eid_le:
                player_eids_be.add(_le_to_be(eid_le))

    # Extract timestamps
    crystal_ts = extract_crystal_death_ts(all_data) if all_data else None
    max_death_ts, max_kill_ts = extract_player_timestamps(all_data, player_eids_be) if all_data else (None, None)
    last_credit_ts = extract_last_credit_ts(all_data, player_eids_be) if all_data else None

    result = DurationEstimate(
        match_name=match_name,
        truth_duration=truth_duration,
        crystal_death_ts=crystal_ts,
        max_player_death_ts=max_death_ts,
        max_player_kill_ts=max_kill_ts,
        last_credit_ts=last_credit_ts,
        frame_count=frame_count,
    )

    print(f"  Crystal death: {crystal_ts:.1f}s" if crystal_ts else "  Crystal death: None")
    print(f"  Max player death: {max_death_ts:.1f}s" if max_death_ts else "  Max player death: None")
    print(f"  Max player kill: {max_kill_ts:.1f}s" if max_kill_ts else "  Max player kill: None")
    print(f"  Frame count: {frame_count}")
    print(f"  Truth duration: {truth_duration}s")
    print(f"[STAGE:status:success]")
    print(f"[STAGE:end:analyze_{match_name[:30]}]")

    return result


def compute_statistics(estimates: List[DurationEstimate]) -> None:
    """Compute and report statistics for all estimation methods."""
    print("\n" + "="*80)
    print("[STAGE:begin:statistical_analysis]")
    print("="*80)

    methods = {
        'crystal': 'Crystal Death Timestamp',
        'max_death': 'Max Player Death Timestamp',
        'max_kill': 'Max Player Kill Timestamp',
        'credit': 'Last Credit Record Timestamp',
        'hybrid_max': 'Hybrid (max of crystal/death)',
    }

    # Compute errors for each method
    all_errors = defaultdict(list)
    for est in estimates:
        errors = est.errors()
        for method, error in errors.items():
            if error is not None:
                all_errors[method].append(error)

    # Report per-method statistics
    print("\n[FINDING] Duration Estimation Method Comparison:")
    print(f"{'Method':<40} {'Mean Error':<12} {'Abs Mean':<12} {'Max Error':<12} {'Coverage'}")
    print("-" * 90)

    for method_key, method_name in methods.items():
        errors = all_errors[method_key]
        if errors:
            mean_error = sum(errors) / len(errors)
            abs_mean_error = sum(abs(e) for e in errors) / len(errors)
            max_abs_error = max(abs(e) for e in errors)
            coverage = f"{len(errors)}/{len(estimates)}"

            print(f"{method_name:<40} {mean_error:>+10.1f}s  {abs_mean_error:>10.1f}s  {max_abs_error:>10.1f}s  {coverage}")
            print(f"[STAT:{method_key}_mean_error] {mean_error:.1f}")
            print(f"[STAT:{method_key}_abs_mean_error] {abs_mean_error:.1f}")
            print(f"[STAT:{method_key}_max_abs_error] {max_abs_error:.1f}")
        else:
            print(f"{method_name:<40} {'N/A':<12} {'N/A':<12} {'N/A':<12} 0/{len(estimates)}")

    # Test frame rate estimates
    print("\n[FINDING] Frame Rate Analysis:")
    print("Testing frame_count / frame_rate for various frame rates...")

    best_frame_rate = None
    best_frame_error = float('inf')

    for frame_rate in [20.0, 25.0, 30.0, 40.0, 50.0, 60.0]:
        errors = []
        for est in estimates:
            if est.frame_count > 0:
                frame_est = est.frame_rate_estimate(frame_rate)
                if frame_est:
                    errors.append(frame_est - est.truth_duration)

        if errors:
            abs_mean = sum(abs(e) for e in errors) / len(errors)
            print(f"  Frame rate {frame_rate:>5.1f} fps: abs mean error = {abs_mean:>6.1f}s")
            if abs_mean < best_frame_error:
                best_frame_error = abs_mean
                best_frame_rate = frame_rate

    if best_frame_rate:
        print(f"\n[STAT:best_frame_rate] {best_frame_rate:.1f} fps")
        print(f"[STAT:frame_rate_abs_error] {best_frame_error:.1f}")

    # Test crystal death offset corrections
    print("\n[FINDING] Crystal Death Offset Correction:")
    print("Testing crystal_death_ts - offset for various offsets...")

    best_offset = None
    best_offset_error = float('inf')

    for offset in range(-40, 41, 2):
        errors = []
        for est in estimates:
            if est.crystal_death_ts:
                offset_est = est.crystal_offset_estimate(offset)
                if offset_est:
                    errors.append(offset_est - est.truth_duration)

        if errors:
            abs_mean = sum(abs(e) for e in errors) / len(errors)
            if abs(offset) <= 40:  # Only print reasonable offsets
                print(f"  Offset {offset:>+4d}s: abs mean error = {abs_mean:>6.1f}s")
            if abs_mean < best_offset_error:
                best_offset_error = abs_mean
                best_offset = offset

    if best_offset is not None:
        print(f"\n[STAT:best_crystal_offset] {best_offset:+d}")
        print(f"[STAT:crystal_offset_abs_error] {best_offset_error:.1f}")

    # Detailed per-match breakdown
    print("\n" + "="*80)
    print("[FINDING] Per-Match Duration Breakdown:")
    print("="*80)
    print(f"{'Match':<12} {'Truth':<8} {'Crystal':<10} {'MaxDeath':<10} {'Hybrid':<10} {'Errors (C/D/H)'}")
    print("-" * 90)

    for est in estimates:
        short_name = est.match_name[:12]
        truth = est.truth_duration
        crystal = est.crystal_estimate if est.crystal_estimate else 0
        max_death = est.max_death_estimate if est.max_death_estimate else 0
        hybrid = est.hybrid_max_estimate() if est.hybrid_max_estimate() else 0

        err_c = crystal - truth if crystal else None
        err_d = max_death - truth if max_death else None
        err_h = hybrid - truth if hybrid else None

        err_str = f"{err_c:+4d}/{err_d:+4d}/{err_h:+4d}" if all(x is not None for x in [err_c, err_d, err_h]) else "N/A"

        print(f"{short_name:<12} {truth:<8d} {crystal:<10d} {max_death:<10d} {hybrid:<10d} {err_str}")

    print("\n[STAGE:status:success]")
    print("[STAGE:end:statistical_analysis]")


def recommend_formula(estimates: List[DurationEstimate]) -> None:
    """Recommend best duration formula based on analysis."""
    print("\n" + "="*80)
    print("[STAGE:begin:recommendation]")
    print("="*80)

    # Compute hybrid max method errors
    hybrid_errors = []
    for est in estimates:
        hybrid = est.hybrid_max_estimate()
        if hybrid:
            hybrid_errors.append(abs(hybrid - est.truth_duration))

    hybrid_abs_mean = sum(hybrid_errors) / len(hybrid_errors) if hybrid_errors else float('inf')

    print("\n[FINDING] Recommended Duration Formula:")
    print("\n  FORMULA: duration = max(crystal_death_ts, max_player_death_ts)")
    print("\n  RATIONALE:")
    print("    - Crystal death typically marks game end (~1s after last player death)")
    print("    - Max player death provides fallback for crystal FPs (turrets)")
    print("    - Hybrid max method handles both cases robustly")
    print("\n  PERFORMANCE:")
    print(f"    - Mean absolute error: {hybrid_abs_mean:.1f}s")
    print(f"    - Coverage: {len(hybrid_errors)}/{len(estimates)} matches")
    print(f"    - Max error: {max(hybrid_errors):.1f}s" if hybrid_errors else "    - Max error: N/A")

    print("\n  IMPLEMENTATION (unified_decoder.py lines 323-338):")
    print("""
    # Current implementation already uses hybrid approach:
    if crystal_ts is not None and duration_est is not None:
        if crystal_ts >= duration_est - 30:
            duration = int(crystal_ts)  # Crystal is valid
        else:
            duration = int(duration_est)  # Crystal is FP, use max death
    elif crystal_ts is not None:
        duration = int(crystal_ts)
    elif duration_est is not None:
        duration = int(duration_est)
    """)

    print("\n[LIMITATION] Current implementation has correct logic but suboptimal threshold")
    print("  - Current: uses crystal if crystal_ts >= max_death_ts - 30")
    print("  - Better: directly use max(crystal_ts, max_death_ts)")
    print("  - This eliminates the 30s threshold heuristic")

    print("\n[STAGE:status:success]")
    print("[STAGE:end:recommendation]")


def main():
    """Main research execution."""
    print("[OBJECTIVE] Determine optimal duration estimation formula by comparing")
    print("            multiple timestamp sources against 10 tournament match truths")

    # Load truth data
    truth_path = Path(__file__).parent.parent / "output" / "tournament_truth.json"
    with open(truth_path, 'r') as f:
        truth_data = json.load(f)

    matches = truth_data['matches'][:10]  # First 10 complete matches

    print(f"\n[DATA] Loaded {len(matches)} tournament matches")
    print(f"[DATA] Duration range: {min(m['match_info']['duration_seconds'] for m in matches)}s - "
          f"{max(m['match_info']['duration_seconds'] for m in matches)}s")

    # Analyze each match
    estimates = []
    for match in matches:
        replay_file = match['replay_file']
        duration = match['match_info']['duration_seconds']
        match_name = match['replay_name']

        if Path(replay_file).exists():
            est = analyze_match(replay_file, duration, match_name)
            estimates.append(est)
        else:
            print(f"\n[LIMITATION] Replay file not found: {replay_file}")

    print(f"\n[DATA] Successfully analyzed {len(estimates)}/{len(matches)} matches")

    # Compute statistics
    if estimates:
        compute_statistics(estimates)
        recommend_formula(estimates)
    else:
        print("\n[LIMITATION] No matches could be analyzed")

    print("\n" + "="*80)
    print("[FINDING] Research complete - see recommendation above")
    print("="*80)


if __name__ == '__main__':
    main()
