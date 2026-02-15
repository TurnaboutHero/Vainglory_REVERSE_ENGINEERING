#!/usr/bin/env python3
"""
Frame Anomaly Detector - Statistical Kill/Death Event Detection
Analyzes frame-level statistical properties to detect anomalous events (kills/deaths)
without relying on specific action codes.
"""

import sys
import json
import struct
from pathlib import Path
from collections import Counter, defaultdict
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass, asdict
import statistics

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from vg.core.vgr_parser import VGRParser


@dataclass
class FrameMetrics:
    """Statistical metrics for a single frame"""
    frame_num: int
    file_size: int
    total_events: int
    unique_entities: int
    player_events: int  # Events from player entities (50000-60000)
    infrastructure_events: int  # Events from infrastructure (1000-20000)
    system_events: int  # Events from system (0-100)
    action_codes: Dict[int, int]  # Action code distribution
    top_entities: List[Tuple[int, int]]  # Top 10 most active entities


@dataclass
class PlayerActivity:
    """Player entity activity over time"""
    entity_id: int
    player_name: str
    frame_events: List[int]  # Events per frame (index = frame number)
    total_events: int
    avg_events_per_frame: float
    max_events_frame: int
    min_events_frame: int
    sudden_drops: List[Tuple[int, int, int]]  # (frame, before_avg, after_count)


@dataclass
class AnomalousFrame:
    """A frame flagged as anomalous"""
    frame_num: int
    anomaly_score: float
    reasons: List[str]
    metrics: FrameMetrics


class FrameAnomalyDetector:
    """Detect kill/death events through statistical anomaly detection"""

    EVENT_SIZE = 37  # [EntityID 2B LE][00 00][ActionCode 1B][Payload ~32B]

    def __init__(self, replay_path: str):
        """Initialize detector with replay path"""
        self.replay_path = Path(replay_path)
        self.frames: List[FrameMetrics] = []
        self.player_activities: Dict[int, PlayerActivity] = {}
        self.anomalous_frames: List[AnomalousFrame] = []

        # Parse metadata from first frame
        self.parser = VGRParser(str(replay_path), detect_heroes=False, auto_truth=True)
        self.metadata = self.parser.parse()

        # Extract player entity IDs
        self.player_entities: Dict[int, str] = {}
        for team in ['left', 'right']:
            for player in self.metadata['teams'][team]:
                if player.get('entity_id'):
                    self.player_entities[player['entity_id']] = player['name']

    def _load_frame(self, frame_num: int) -> Optional[bytes]:
        """Load a specific frame file"""
        # Find the replay name from first frame
        first_frame = list(self.replay_path.glob('*.0.vgr'))
        if not first_frame:
            return None

        replay_name = first_frame[0].stem.rsplit('.', 1)[0]
        frame_path = self.replay_path / f"{replay_name}.{frame_num}.vgr"

        if not frame_path.exists():
            return None

        return frame_path.read_bytes()

    def _parse_frame_events(self, data: bytes) -> List[Tuple[int, int]]:
        """
        Parse events from frame data.
        Returns: List of (entity_id, action_code) tuples
        """
        events = []

        # Scan for event patterns: [EntityID 2B LE][00 00][ActionCode 1B]
        # We look for the [00 00] marker and extract entity_id before and action_code after
        for i in range(len(data) - 5):
            # Check for [00 00] pattern
            if data[i:i+2] == b'\x00\x00':
                # Entity ID is 2 bytes before [00 00]
                if i >= 2:
                    entity_id = struct.unpack('<H', data[i-2:i])[0]
                    action_code = data[i+2]

                    # Only count if entity_id is reasonable (not 0x0000)
                    if entity_id > 0:
                        events.append((entity_id, action_code))

        return events

    def _compute_frame_metrics(self, frame_num: int, data: bytes) -> FrameMetrics:
        """Compute statistical metrics for a frame"""
        events = self._parse_frame_events(data)

        entity_counts = Counter(e[0] for e in events)
        action_counts = Counter(e[1] for e in events)

        # Categorize events by entity range
        player_events = sum(1 for e, _ in events if 50000 <= e <= 60000)
        infrastructure_events = sum(1 for e, _ in events if 1000 <= e <= 20000)
        system_events = sum(1 for e, _ in events if 0 <= e <= 100)

        # Top 10 most active entities
        top_entities = entity_counts.most_common(10)

        return FrameMetrics(
            frame_num=frame_num,
            file_size=len(data),
            total_events=len(events),
            unique_entities=len(entity_counts),
            player_events=player_events,
            infrastructure_events=infrastructure_events,
            system_events=system_events,
            action_codes=dict(action_counts),
            top_entities=top_entities
        )

    def analyze_all_frames(self) -> None:
        """Analyze all frames and build statistical profile"""
        print("[STAGE:begin:frame_analysis]")
        print("[OBJECTIVE] Analyzing 103 frames for statistical anomalies")

        total_frames = self.metadata['match_info']['total_frames']

        # Analyze each frame
        for frame_num in range(total_frames):
            data = self._load_frame(frame_num)
            if data is None:
                continue

            metrics = self._compute_frame_metrics(frame_num, data)
            self.frames.append(metrics)

            if (frame_num + 1) % 20 == 0:
                print(f"[DATA] Processed {frame_num + 1}/{total_frames} frames")

        print(f"[DATA] Completed analysis of {len(self.frames)} frames")
        print("[STAGE:status:success]")
        print("[STAGE:end:frame_analysis]")

    def build_player_activity_timeseries(self) -> None:
        """Build per-player event count time series"""
        print("[STAGE:begin:player_activity]")

        # Initialize activity trackers
        for entity_id, name in self.player_entities.items():
            self.player_activities[entity_id] = PlayerActivity(
                entity_id=entity_id,
                player_name=name,
                frame_events=[],
                total_events=0,
                avg_events_per_frame=0.0,
                max_events_frame=0,
                min_events_frame=0,
                sudden_drops=[]
            )

        # Count events per player per frame
        for frame in self.frames:
            frame_num = frame.frame_num

            # Load frame data again to count player-specific events
            data = self._load_frame(frame_num)
            if data is None:
                continue

            events = self._parse_frame_events(data)
            player_event_counts = Counter(e for e, _ in events if e in self.player_entities)

            # Record counts for each player
            for entity_id in self.player_entities:
                count = player_event_counts.get(entity_id, 0)
                self.player_activities[entity_id].frame_events.append(count)

        # Compute statistics
        for entity_id, activity in self.player_activities.items():
            if activity.frame_events:
                activity.total_events = sum(activity.frame_events)
                activity.avg_events_per_frame = statistics.mean(activity.frame_events)
                activity.max_events_frame = max(activity.frame_events)
                activity.min_events_frame = min(activity.frame_events)

                # Detect sudden drops (potential deaths)
                activity.sudden_drops = self._detect_sudden_drops(activity.frame_events)

        print("[STAGE:status:success]")
        print("[STAGE:end:player_activity]")

    def _detect_sudden_drops(self, frame_events: List[int], window: int = 5) -> List[Tuple[int, int, int]]:
        """
        Detect sudden drops in activity (potential death events).
        Returns: List of (frame, before_avg, after_count)
        """
        drops = []

        for i in range(window, len(frame_events) - 1):
            # Calculate average of previous window
            before_avg = statistics.mean(frame_events[i-window:i])
            after_count = frame_events[i]

            # Flag if drop is significant (>50% decrease and before_avg > 10)
            if before_avg > 10 and after_count < before_avg * 0.5:
                drops.append((i, int(before_avg), after_count))

        return drops

    def build_normal_profile(self) -> Dict[str, Any]:
        """Build baseline 'normal frame' statistical profile"""
        print("[STAGE:begin:baseline_profile]")

        if not self.frames:
            return {}

        # Aggregate statistics
        file_sizes = [f.file_size for f in self.frames]
        total_events = [f.total_events for f in self.frames]
        unique_entities = [f.unique_entities for f in self.frames]
        player_events = [f.player_events for f in self.frames]

        profile = {
            'file_size_mean': statistics.mean(file_sizes),
            'file_size_median': statistics.median(file_sizes),
            'file_size_stdev': statistics.stdev(file_sizes) if len(file_sizes) > 1 else 0,
            'total_events_mean': statistics.mean(total_events),
            'total_events_median': statistics.median(total_events),
            'total_events_stdev': statistics.stdev(total_events) if len(total_events) > 1 else 0,
            'unique_entities_mean': statistics.mean(unique_entities),
            'unique_entities_median': statistics.median(unique_entities),
            'player_events_mean': statistics.mean(player_events),
            'player_events_median': statistics.median(player_events),
            'player_events_stdev': statistics.stdev(player_events) if len(player_events) > 1 else 0,
        }

        print(f"[STAT:baseline_total_events_mean] {profile['total_events_mean']:.1f}")
        print(f"[STAT:baseline_player_events_mean] {profile['player_events_mean']:.1f}")
        print(f"[STAT:baseline_file_size_mean] {profile['file_size_mean']:.0f} bytes")

        print("[STAGE:status:success]")
        print("[STAGE:end:baseline_profile]")

        return profile

    def detect_anomalous_frames(self, profile: Dict[str, Any]) -> None:
        """Detect frames that deviate significantly from baseline"""
        print("[STAGE:begin:anomaly_detection]")

        for frame in self.frames:
            anomaly_score = 0.0
            reasons = []

            # Check total events deviation
            if profile['total_events_stdev'] > 0:
                z_score = abs(frame.total_events - profile['total_events_mean']) / profile['total_events_stdev']
                if z_score > 2.0:
                    anomaly_score += z_score
                    reasons.append(f"Total events: {frame.total_events} (z={z_score:.2f})")

            # Check player events deviation
            if profile['player_events_stdev'] > 0:
                z_score = abs(frame.player_events - profile['player_events_mean']) / profile['player_events_stdev']
                if z_score > 2.0:
                    anomaly_score += z_score
                    reasons.append(f"Player events: {frame.player_events} (z={z_score:.2f})")

            # Check file size deviation
            if profile['file_size_stdev'] > 0:
                z_score = abs(frame.file_size - profile['file_size_mean']) / profile['file_size_stdev']
                if z_score > 2.5:
                    anomaly_score += z_score * 0.5  # Lower weight
                    reasons.append(f"File size: {frame.file_size} bytes (z={z_score:.2f})")

            # Check for unusual action codes
            all_action_codes = set()
            for f in self.frames:
                all_action_codes.update(f.action_codes.keys())

            rare_codes = set(frame.action_codes.keys()) - all_action_codes
            if rare_codes:
                anomaly_score += len(rare_codes) * 0.5
                reasons.append(f"Rare action codes: {rare_codes}")

            # Flag if anomaly score is significant
            if anomaly_score > 2.0:
                self.anomalous_frames.append(AnomalousFrame(
                    frame_num=frame.frame_num,
                    anomaly_score=anomaly_score,
                    reasons=reasons,
                    metrics=frame
                ))

        # Sort by anomaly score
        self.anomalous_frames.sort(key=lambda x: x.anomaly_score, reverse=True)

        print(f"[FINDING] Detected {len(self.anomalous_frames)} anomalous frames")
        print(f"[STAT:anomalous_frame_count] {len(self.anomalous_frames)}")

        print("[STAGE:status:success]")
        print("[STAGE:end:anomaly_detection]")

    def identify_team_fight_frames(self) -> List[Tuple[int, List[int]]]:
        """
        Identify frames where multiple players have unusual activity simultaneously.
        Returns: List of (frame_num, [entity_ids with unusual activity])
        """
        print("[STAGE:begin:team_fight_detection]")

        team_fights = []

        for frame_num in range(len(self.frames)):
            unusual_players = []

            for entity_id, activity in self.player_activities.items():
                if frame_num >= len(activity.frame_events):
                    continue

                # Check if this frame has unusual activity for this player
                frame_count = activity.frame_events[frame_num]

                # Unusual = significantly above average
                if activity.avg_events_per_frame > 0:
                    ratio = frame_count / activity.avg_events_per_frame
                    if ratio > 2.0 or ratio < 0.3:  # 2x spike or 70% drop
                        unusual_players.append(entity_id)

            # Team fight = 3+ players with unusual activity
            if len(unusual_players) >= 3:
                team_fights.append((frame_num, unusual_players))

        print(f"[FINDING] Identified {len(team_fights)} potential team fight frames")
        print(f"[STAT:team_fight_frame_count] {len(team_fights)}")

        print("[STAGE:status:success]")
        print("[STAGE:end:team_fight_detection]")

        return team_fights

    def generate_text_plot(self, entity_id: int, width: int = 80, height: int = 10) -> List[str]:
        """Generate ASCII plot of player activity over time"""
        activity = self.player_activities[entity_id]
        events = activity.frame_events

        if not events or max(events) == 0:
            return [f"No activity data for entity {entity_id}"]

        # Normalize to height
        max_val = max(events)
        normalized = [int((e / max_val) * (height - 1)) for e in events]

        # Build plot
        plot = []
        plot.append(f"Player: {activity.player_name} (Entity {entity_id})")
        plot.append(f"Range: 0 to {max_val} events/frame")
        plot.append("─" * width)

        # Create grid
        for row in range(height - 1, -1, -1):
            line = []
            for frame_idx, val in enumerate(normalized):
                if frame_idx >= width:
                    break
                if val >= row:
                    line.append("█")
                else:
                    line.append(" ")
            plot.append("".join(line))

        plot.append("─" * width)
        plot.append(f"Frames: 0 → {min(len(events), width)}")

        return plot

    def save_results(self, output_path: str) -> None:
        """Save analysis results to JSON file"""
        print("[STAGE:begin:save_results]")

        # Build truth data comparison
        truth_players = {}
        for team in ['left', 'right']:
            for player in self.metadata['teams'][team]:
                truth_players[player['name']] = {
                    'entity_id': player.get('entity_id'),
                    'expected_kills': player.get('kills', 0),
                    'expected_deaths': player.get('deaths', 0),
                }

        # Build results
        results = {
            'replay_name': self.metadata['replay_name'],
            'total_frames': len(self.frames),
            'total_expected_deaths': sum(p.get('expected_deaths', 0) for p in truth_players.values()),
            'baseline_profile': self.build_normal_profile(),
            'anomalous_frames': [
                {
                    'frame_num': af.frame_num,
                    'anomaly_score': af.anomaly_score,
                    'reasons': af.reasons,
                    'metrics': {
                        'total_events': af.metrics.total_events,
                        'player_events': af.metrics.player_events,
                        'file_size': af.metrics.file_size,
                        'unique_entities': af.metrics.unique_entities,
                    }
                }
                for af in self.anomalous_frames[:20]  # Top 20
            ],
            'player_activities': {
                name: {
                    'entity_id': activity.entity_id,
                    'total_events': activity.total_events,
                    'avg_events_per_frame': activity.avg_events_per_frame,
                    'sudden_drops': activity.sudden_drops,
                    'expected_deaths': truth_players.get(name, {}).get('expected_deaths', 0),
                }
                for entity_id, activity in self.player_activities.items()
                for name in [activity.player_name]
            },
            'team_fights': [
                {
                    'frame_num': frame_num,
                    'players_involved': [self.player_entities.get(e, f"Entity_{e}") for e in entities]
                }
                for frame_num, entities in self.identify_team_fight_frames()
            ],
            'truth_comparison': truth_players,
        }

        # Save to file
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        print(f"[FINDING] Results saved to {output_path}")
        print("[STAGE:status:success]")
        print("[STAGE:end:save_results]")

    def print_summary(self) -> None:
        """Print analysis summary to console"""
        print("\n" + "="*80)
        print("FRAME ANOMALY DETECTION SUMMARY")
        print("="*80)

        # Top anomalous frames
        print("\n[FINDING] Top 10 Anomalous Frames:")
        for i, af in enumerate(self.anomalous_frames[:10], 1):
            print(f"  {i}. Frame {af.frame_num}: Score={af.anomaly_score:.2f}")
            for reason in af.reasons:
                print(f"     - {reason}")

        # Player activity sudden drops
        print("\n[FINDING] Player Activity Sudden Drops (Potential Deaths):")
        for entity_id, activity in self.player_activities.items():
            if activity.sudden_drops:
                print(f"  {activity.player_name} (Entity {entity_id}):")
                for frame, before, after in activity.sudden_drops[:5]:  # Top 5 drops
                    print(f"    Frame {frame}: {before} -> {after} events ({(after-before)/before*100:.0f}% change)")

        # Text plots - skip on Windows console due to Unicode issues
        try:
            print("\n[FINDING] Player Activity Trajectories (First 80 frames):")
            for entity_id in sorted(self.player_activities.keys()):
                plot_lines = self.generate_text_plot(entity_id, width=80, height=8)
                for line in plot_lines:
                    print(f"  {line}")
                print()
        except UnicodeEncodeError:
            print("\n[LIMITATION] Text plots skipped due to console encoding limitations")
            print("[LIMITATION] Full activity data available in JSON output file")


def main():
    """Main execution"""
    replay_path = "D:/Desktop/My Folder/Game/VG/vg replay/21.11.04/cache/"
    output_path = "vg/output/frame_anomaly_analysis.json"

    print("[OBJECTIVE] Detect kill/death events through frame-level statistical anomaly detection")
    print(f"[DATA] Replay path: {replay_path}")
    print(f"[DATA] Output path: {output_path}")

    detector = FrameAnomalyDetector(replay_path)
    detector.analyze_all_frames()
    detector.build_player_activity_timeseries()

    profile = detector.build_normal_profile()
    detector.detect_anomalous_frames(profile)

    detector.print_summary()
    detector.save_results(output_path)

    print("\n[LIMITATION] Statistical anomaly detection captures unusual frames but cannot definitively identify death events without action code mapping")
    print("[LIMITATION] Sudden drops in player activity may indicate deaths, respawns, or temporary disengagement")
    print("[LIMITATION] Team fight detection based on simultaneous unusual activity may include non-combat events")


if __name__ == '__main__':
    main()
