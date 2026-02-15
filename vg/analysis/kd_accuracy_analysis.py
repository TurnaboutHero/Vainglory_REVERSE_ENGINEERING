#!/usr/bin/env python3
"""
K/D Accuracy Gap Analysis - Deep dive into detection errors.

Analyzes each false positive and false negative to identify patterns:
- Post-game ceremony kills/deaths
- Duplicate records
- Timestamp proximity to game end
- Frame boundary issues
- Missing patterns

Goal: Move from 94.4%/92.5% accuracy closer to 100%.
"""

import json
import struct
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass
from collections import defaultdict

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from vg.core.kda_detector import KDADetector, KillEvent, DeathEvent
from vg.core.vgr_parser import VGRParser


def le_to_be(eid_le: int) -> int:
    """Convert uint16 LE to BE."""
    return struct.unpack('>H', struct.pack('<H', eid_le))[0]


@dataclass
class ErrorCase:
    """A single K/D detection error."""
    match_id: int
    replay_name: str
    player_name: str
    error_type: str  # "kill_fp", "kill_fn", "death_fp", "death_fn"
    detected: int
    truth: int
    diff: int
    game_duration: int
    events: List  # KillEvent or DeathEvent list


class KDAccuracyAnalyzer:
    """Analyzes K/D detection errors to find patterns."""

    def __init__(self, truth_path: str):
        self.truth_path = Path(truth_path)
        self.truth_data = self._load_truth()
        self.errors: List[ErrorCase] = []

    def _load_truth(self) -> Dict:
        """Load tournament truth data."""
        with open(self.truth_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def analyze_all_matches(self):
        """Analyze all matches and collect errors."""
        print("[OBJECTIVE] Analyze K/D detection accuracy gaps across tournament matches")
        print()

        for match_idx, match in enumerate(self.truth_data["matches"], start=1):
            replay_name = match["replay_name"]

            # Skip Match 9 (incomplete)
            if "Incomplete" in match.get("result_image", ""):
                print(f"Match {match_idx}: SKIP (incomplete replay)")
                continue

            print(f"Match {match_idx}: {replay_name}")
            self._analyze_match(match_idx, match)
            print()

        print(f"\n[DATA] Collected {len(self.errors)} error cases")
        print()

    def _analyze_match(self, match_idx: int, match: Dict):
        """Analyze a single match for errors."""
        replay_file = match["replay_file"]
        replay_path = Path(replay_file)

        if not replay_path.exists():
            print(f"  ERROR: Replay file not found: {replay_file}")
            return

        # Parse replay
        parser = VGRParser(str(replay_path.parent), detect_heroes=False, auto_truth=False)
        parsed = parser.parse()

        # Load frames
        frame_dir = replay_path.parent
        frame_name = replay_path.stem.rsplit('.', 1)[0]
        frames = self._load_frames(frame_dir, frame_name)

        if not frames:
            print(f"  ERROR: No frames found")
            return

        # Build entity ID mapping
        eid_map_be = {}  # BE -> player_name
        team_map = {}    # BE -> team
        name_to_eid_be = {}  # player_name -> BE eid

        for team_name, players in parsed.get("teams", {}).items():
            for p in players:
                eid_le = p.get("entity_id")
                if eid_le:
                    eid_be = le_to_be(eid_le)
                    player_name = p["name"]
                    eid_map_be[eid_be] = player_name
                    team_map[eid_be] = team_name
                    name_to_eid_be[player_name] = eid_be

        # Run KDA detector
        detector = KDADetector(set(eid_map_be.keys()))
        for frame_idx, data in frames:
            detector.process_frame(frame_idx, data)

        # Get results with post-game filter
        game_duration = match["match_info"]["duration_seconds"]
        results = detector.get_results(game_duration=game_duration, team_map=team_map)

        # Compare with truth
        truth_players = match["players"]

        for player_name, truth_stats in truth_players.items():
            eid_be = name_to_eid_be.get(player_name)
            if not eid_be:
                continue

            detected_stats = results.get(eid_be)
            if not detected_stats:
                continue

            truth_k = truth_stats["kills"]
            truth_d = truth_stats["deaths"]
            detected_k = detected_stats.kills
            detected_d = detected_stats.deaths

            # Check for errors
            if detected_k != truth_k:
                error_type = "kill_fp" if detected_k > truth_k else "kill_fn"
                self.errors.append(ErrorCase(
                    match_id=match_idx,
                    replay_name=match["replay_name"],
                    player_name=player_name,
                    error_type=error_type,
                    detected=detected_k,
                    truth=truth_k,
                    diff=detected_k - truth_k,
                    game_duration=game_duration,
                    events=detected_stats.kill_events,
                ))
                print(f"  MISS {player_name}: Kill {error_type.upper()} detected={detected_k} truth={truth_k}")

            if detected_d != truth_d:
                error_type = "death_fp" if detected_d > truth_d else "death_fn"
                self.errors.append(ErrorCase(
                    match_id=match_idx,
                    replay_name=match["replay_name"],
                    player_name=player_name,
                    error_type=error_type,
                    detected=detected_d,
                    truth=truth_d,
                    diff=detected_d - truth_d,
                    game_duration=game_duration,
                    events=detected_stats.death_events,
                ))
                print(f"  MISS {player_name}: Death {error_type.upper()} detected={detected_d} truth={truth_d}")

    def _load_frames(self, frame_dir: Path, replay_name: str) -> List[Tuple[int, bytes]]:
        """Load all frame files."""
        frame_files = list(frame_dir.glob(f"{replay_name}.*.vgr"))
        if not frame_files:
            return []

        def _idx(p: Path) -> int:
            try:
                return int(p.stem.split('.')[-1])
            except ValueError:
                return 0

        frame_files.sort(key=_idx)
        return [(_idx(f), f.read_bytes()) for f in frame_files]

    def report_findings(self):
        """Generate detailed findings report."""
        print("\n" + "="*80)
        print("[FINDING] K/D DETECTION ERROR ANALYSIS")
        print("="*80)

        if not self.errors:
            print("\n[FINDING] No errors detected - 100% accuracy!")
            return

        # Group by error type
        by_type = defaultdict(list)
        for err in self.errors:
            by_type[err.error_type].append(err)

        print(f"\n[STAT:total_errors] {len(self.errors)}")
        print(f"[STAT:kill_false_positives] {len(by_type['kill_fp'])}")
        print(f"[STAT:kill_false_negatives] {len(by_type['kill_fn'])}")
        print(f"[STAT:death_false_positives] {len(by_type['death_fp'])}")
        print(f"[STAT:death_false_negatives] {len(by_type['death_fn'])}")
        print()

        # Analyze each error type
        self._analyze_false_positives(by_type['kill_fp'], "KILL")
        self._analyze_false_positives(by_type['death_fp'], "DEATH")
        self._analyze_false_negatives(by_type['kill_fn'], "KILL")
        self._analyze_false_negatives(by_type['death_fn'], "DEATH")

        # Look for patterns
        self._find_patterns()

    def _analyze_false_positives(self, errors: List[ErrorCase], event_type: str):
        """Analyze false positives - detected but shouldn't be."""
        if not errors:
            return

        print(f"\n{'─'*80}")
        print(f"[FINDING] {event_type} FALSE POSITIVES (detected > truth)")
        print(f"{'─'*80}\n")

        for err in errors:
            print(f"Match {err.match_id}: {err.player_name}")
            print(f"  Detected: {err.detected}, Truth: {err.truth}, Extra: +{err.diff}")
            print(f"  Game duration: {err.game_duration}s")

            # List all events with timestamps
            events = err.events
            if event_type == "KILL":
                events_with_ts = [(ev.timestamp, ev.frame_idx, ev.file_offset)
                                  for ev in events if ev.timestamp]
                events_with_ts.sort()
                print(f"  All {len(events)} kill events:")
                for ts, frame, offset in events_with_ts:
                    dt = ts - err.game_duration
                    flag = "[POST-GAME]" if dt > 10 else "[OK]"
                    print(f"    ts={ts:7.1f}s (delta{dt:+6.1f}s) frame={frame:5} offset=0x{offset:06X} {flag}")
            else:  # DEATH
                events_with_ts = [(ev.timestamp, ev.frame_idx, ev.file_offset)
                                  for ev in events]
                events_with_ts.sort()
                print(f"  All {len(events)} death events:")
                for ts, frame, offset in events_with_ts:
                    dt = ts - err.game_duration
                    flag = "[POST-GAME]" if dt > 10 else "[OK]"
                    print(f"    ts={ts:7.1f}s (delta{dt:+6.1f}s) frame={frame:5} offset=0x{offset:06X} {flag}")

            # Check for duplicates
            if event_type == "DEATH":
                timestamps = [ev.timestamp for ev in events]
                if len(timestamps) != len(set(timestamps)):
                    print(f"  WARNING: DUPLICATE timestamps detected!")
                    ts_counts = defaultdict(int)
                    for ts in timestamps:
                        ts_counts[ts] += 1
                    for ts, count in ts_counts.items():
                        if count > 1:
                            print(f"    Timestamp {ts:.1f}s appears {count} times")

            print()

    def _analyze_false_negatives(self, errors: List[ErrorCase], event_type: str):
        """Analyze false negatives - should be detected but weren't."""
        if not errors:
            return

        print(f"\n{'─'*80}")
        print(f"[FINDING] {event_type} FALSE NEGATIVES (detected < truth)")
        print(f"{'─'*80}\n")

        for err in errors:
            print(f"Match {err.match_id}: {err.player_name}")
            print(f"  Detected: {err.detected}, Truth: {err.truth}, Missing: {err.diff}")
            print(f"  Game duration: {err.game_duration}s")

            # List detected events
            events = err.events
            if event_type == "KILL":
                events_with_ts = [(ev.timestamp, ev.frame_idx, ev.file_offset)
                                  for ev in events if ev.timestamp]
                events_with_ts.sort()
                print(f"  Detected {len(events)} kill events:")
                for ts, frame, offset in events_with_ts:
                    print(f"    ts={ts:7.1f}s frame={frame:5} offset=0x{offset:06X}")
            else:  # DEATH
                events_with_ts = [(ev.timestamp, ev.frame_idx, ev.file_offset)
                                  for ev in events]
                events_with_ts.sort()
                print(f"  Detected {len(events)} death events:")
                for ts, frame, offset in events_with_ts:
                    print(f"    ts={ts:7.1f}s frame={frame:5} offset=0x{offset:06X}")

            print(f"  [LIMITATION] Missing {abs(err.diff)} event(s) - pattern variation or data corruption?")
            print()

    def _find_patterns(self):
        """Look for common patterns across all errors."""
        print(f"\n{'─'*80}")
        print("[FINDING] PATTERN ANALYSIS")
        print(f"{'─'*80}\n")

        # Pattern 1: Post-game events (ts > duration + 10)
        death_fp_errors = [e for e in self.errors if e.error_type == "death_fp"]
        if death_fp_errors:
            post_game_count = 0
            for err in death_fp_errors:
                for ev in err.events:
                    if ev.timestamp > err.game_duration + 10:
                        post_game_count += 1

            if post_game_count > 0:
                print(f"[FINDING] Post-game ceremony events detected")
                print(f"  {post_game_count} death events occur >10s after game end")
                print(f"  These are likely post-game ceremony kills (not counted in stats)")
                print(f"  RECOMMENDATION: Current filter (ts <= duration + 10s) should catch these")
                print(f"  → Verify filter is being applied correctly")
                print()

        # Pattern 2: Timestamp clustering
        print("[FINDING] Timestamp distribution analysis")
        for err in self.errors:
            if err.error_type in ["death_fp", "death_fn"]:
                timestamps = [ev.timestamp for ev in err.events]
                if len(timestamps) >= 2:
                    timestamps.sort()
                    gaps = [timestamps[i+1] - timestamps[i] for i in range(len(timestamps)-1)]
                    min_gap = min(gaps) if gaps else 0
                    if min_gap < 5:
                        print(f"  Match {err.match_id} {err.player_name}: Min gap between deaths = {min_gap:.1f}s")
        print()

        # Pattern 3: Match-specific issues
        match_error_counts = defaultdict(int)
        for err in self.errors:
            match_error_counts[err.match_id] += 1

        print("[FINDING] Error distribution by match")
        for match_id, count in sorted(match_error_counts.items()):
            print(f"  Match {match_id}: {count} error(s)")
        print()

        # Pattern 4: Error magnitude
        print("[FINDING] Error magnitude analysis")
        magnitudes = [abs(err.diff) for err in self.errors]
        print(f"  All errors are magnitude ±1: {all(m == 1 for m in magnitudes)}")
        if not all(m == 1 for m in magnitudes):
            print(f"  Error magnitudes: {sorted(set(magnitudes))}")
        print()


def main():
    truth_path = Path(__file__).resolve().parent.parent / "output" / "tournament_truth.json"

    if not truth_path.exists():
        print(f"ERROR: Truth file not found: {truth_path}")
        return 1

    print("[STAGE:begin:error_collection]")
    analyzer = KDAccuracyAnalyzer(str(truth_path))
    analyzer.analyze_all_matches()
    print("[STAGE:status:success]")
    print("[STAGE:end:error_collection]")

    print("\n[STAGE:begin:pattern_analysis]")
    analyzer.report_findings()
    print("[STAGE:status:success]")
    print("[STAGE:end:pattern_analysis]")

    return 0


if __name__ == "__main__":
    sys.exit(main())
