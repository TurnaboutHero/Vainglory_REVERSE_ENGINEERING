#!/usr/bin/env python3
"""
Respawn Timer Analyzer - Death Detection via Progressive Respawn Pattern
Analyzes entity event timelines to detect deaths based on increasing respawn gaps.
"""

import sys
import json
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from vg.core.vgr_parser import VGRParser


@dataclass
class DisappearanceGap:
    """Represents a gap where entity has no events"""
    start_frame: int
    end_frame: int
    duration: int
    game_progress: float  # 0.0 to 1.0
    gap_index: int  # Which gap in sequence (0, 1, 2...)

    def to_dict(self):
        return asdict(self)


@dataclass
class EntityTimeline:
    """Timeline of entity event presence across frames"""
    entity_id: int
    player_name: str
    hero_name: str
    team: str
    truth_deaths: int
    frames_present: List[int]
    frames_absent: List[int]
    gaps: List[DisappearanceGap]
    detected_deaths: int

    def to_dict(self):
        return {
            'entity_id': self.entity_id,
            'player_name': self.player_name,
            'hero_name': self.hero_name,
            'team': self.team,
            'truth_deaths': self.truth_deaths,
            'total_frames_present': len(self.frames_present),
            'total_frames_absent': len(self.frames_absent),
            'gap_count': len(self.gaps),
            'gaps': [g.to_dict() for g in self.gaps],
            'detected_deaths': self.detected_deaths,
        }


class RespawnTimerAnalyzer:
    """Analyzes respawn timer patterns to detect player deaths"""

    # Truth data for validation
    TRUTH_DEATHS = {
        57605: 2,  # Baron (left)
        57093: 2,  # Petal (left)
        56325: 0,  # Phinn (left)
        56837: 4,  # Caine (right)
        56581: 4,  # Yates (right)
        57349: 3,  # Amael/Karas (right)
    }

    def __init__(self, replay_dir: str):
        """Initialize analyzer with replay directory"""
        self.replay_dir = Path(replay_dir)
        self.parser = VGRParser(str(self.replay_dir))
        self.total_frames = 0
        self.entity_timelines: Dict[int, EntityTimeline] = {}

    def _load_player_metadata(self) -> Dict[int, Dict]:
        """Load player entity IDs and metadata from parser"""
        data = self.parser.parse()
        self.total_frames = data['match_info']['total_frames']

        player_map = {}
        for team_name in ['left', 'right']:
            for player in data['teams'][team_name]:
                entity_id = player.get('entity_id')
                if entity_id:
                    player_map[entity_id] = {
                        'name': player['name'],
                        'hero': player.get('hero_name', 'Unknown'),
                        'team': team_name,
                        'truth_deaths': self.TRUTH_DEATHS.get(entity_id, 0)
                    }

        return player_map

    def _parse_frame_events(self, frame_path: Path) -> Dict[int, int]:
        """
        Parse a single frame and count events per entity.
        Returns: {entity_id: event_count}
        """
        data = frame_path.read_bytes()
        entity_counts = defaultdict(int)

        # Event format: [EntityID 2B LE][00 00][ActionCode 1B][Payload ~32B]
        # Scan for entity IDs at start of 37-byte patterns
        idx = 0
        while idx + 5 < len(data):
            # Read potential entity ID (2 bytes LE)
            entity_id = int.from_bytes(data[idx:idx+2], 'little')

            # Check for [00 00] marker after entity ID
            if data[idx+2:idx+4] == b'\x00\x00':
                # Valid event pattern detected
                entity_counts[entity_id] += 1
                idx += 37  # Skip to next potential event
            else:
                idx += 1

        return dict(entity_counts)

    def _build_timelines(self, player_map: Dict[int, Dict]) -> None:
        """Build event presence timelines for all players"""
        # Find all frame files
        frames = sorted(self.replay_dir.glob('*.vgr'))

        # Track which frames each entity appears in
        entity_presence = defaultdict(set)

        print(f"[STAGE:begin:frame_parsing]")
        print(f"[DATA] Parsing {len(frames)} frames...")

        for frame_idx, frame_path in enumerate(frames):
            entity_events = self._parse_frame_events(frame_path)

            for entity_id in entity_events:
                if entity_id in player_map:
                    entity_presence[entity_id].add(frame_idx)

        print(f"[STAGE:status:success]")
        print(f"[STAGE:end:frame_parsing]")

        # Build timeline objects
        for entity_id, meta in player_map.items():
            frames_present = sorted(entity_presence.get(entity_id, set()))
            all_frames = set(range(len(frames)))
            frames_absent = sorted(all_frames - set(frames_present))

            # Find disappearance gaps (consecutive absent frames)
            gaps = self._find_gaps(frames_absent, len(frames))

            timeline = EntityTimeline(
                entity_id=entity_id,
                player_name=meta['name'],
                hero_name=meta['hero'],
                team=meta['team'],
                truth_deaths=meta['truth_deaths'],
                frames_present=frames_present,
                frames_absent=frames_absent,
                gaps=gaps,
                detected_deaths=0,
            )

            self.entity_timelines[entity_id] = timeline

    def _find_gaps(self, frames_absent: List[int], total_frames: int) -> List[DisappearanceGap]:
        """Find consecutive frame gaps in absence timeline"""
        if not frames_absent:
            return []

        gaps = []
        gap_start = frames_absent[0]
        gap_index = 0

        for i in range(1, len(frames_absent)):
            # Check if consecutive
            if frames_absent[i] != frames_absent[i-1] + 1:
                # Gap ended
                gap_end = frames_absent[i-1]
                duration = gap_end - gap_start + 1

                if duration >= 2:  # Minimum 2-frame gap
                    game_progress = gap_start / total_frames
                    gaps.append(DisappearanceGap(
                        start_frame=gap_start,
                        end_frame=gap_end,
                        duration=duration,
                        game_progress=game_progress,
                        gap_index=gap_index,
                    ))
                    gap_index += 1

                # Start new gap
                gap_start = frames_absent[i]

        # Handle final gap
        gap_end = frames_absent[-1]
        duration = gap_end - gap_start + 1
        if duration >= 2:
            game_progress = gap_start / total_frames
            gaps.append(DisappearanceGap(
                start_frame=gap_start,
                end_frame=gap_end,
                duration=duration,
                game_progress=game_progress,
                gap_index=gap_index,
            ))

        return gaps

    def _progressive_threshold_filter(self, timeline: EntityTimeline) -> int:
        """
        Filter deaths using progressive respawn timer threshold.
        Early game: shorter gaps needed
        Late game: longer gaps expected
        """
        if not timeline.gaps:
            return 0

        detected = 0

        for gap in timeline.gaps:
            # Progressive threshold: min_gap_duration = base + (progress * scale)
            # Early game (0%): min 3 frames
            # Late game (100%): min 10 frames
            base_threshold = 3
            max_threshold = 10
            scale = max_threshold - base_threshold

            min_duration = base_threshold + (gap.game_progress * scale)

            if gap.duration >= min_duration:
                detected += 1

        return detected

    def _clustering_filter(self, timeline: EntityTimeline) -> int:
        """
        Filter deaths using gap duration clustering.
        Hypothesis: True deaths form a cluster of longer gaps.
        """
        if not timeline.gaps:
            return 0

        durations = [g.duration for g in timeline.gaps]

        # Simple 2-means clustering: short (noise) vs long (death)
        if len(durations) < 2:
            # Single gap - check if it's long enough
            return 1 if durations[0] >= 5 else 0

        # Sort and find natural break (largest gap between consecutive values)
        sorted_durations = sorted(durations)
        max_jump = 0
        split_idx = 0

        for i in range(1, len(sorted_durations)):
            jump = sorted_durations[i] - sorted_durations[i-1]
            if jump > max_jump:
                max_jump = jump
                split_idx = i

        # Threshold is midpoint of largest jump
        if max_jump > 0:
            threshold = (sorted_durations[split_idx-1] + sorted_durations[split_idx]) / 2
        else:
            # No clear clustering - use median
            threshold = sorted_durations[len(sorted_durations) // 2]

        # Count gaps above threshold
        return sum(1 for d in durations if d >= threshold)

    def _increasing_trend_filter(self, timeline: EntityTimeline) -> int:
        """
        Filter deaths by checking for increasing gap duration trend.
        True deaths should show generally increasing respawn times.
        """
        if not timeline.gaps:
            return 0

        # For small gap counts, use simple threshold
        if len(timeline.gaps) <= 2:
            return sum(1 for g in timeline.gaps if g.duration >= 4)

        # Check if gaps show increasing trend
        # Use linear regression slope
        n = len(timeline.gaps)
        x = list(range(n))  # Gap index
        y = [g.duration for g in timeline.gaps]

        # Calculate slope: slope = (n*Σxy - Σx*Σy) / (n*Σx² - (Σx)²)
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(xi * yi for xi, yi in zip(x, y))
        sum_x2 = sum(xi * xi for xi in x)

        denominator = n * sum_x2 - sum_x * sum_x
        if denominator == 0:
            # No trend - use median threshold
            median = sorted(y)[n // 2]
            return sum(1 for yi in y if yi >= median)

        slope = (n * sum_xy - sum_x * sum_y) / denominator

        # Positive slope suggests increasing respawn times (death pattern)
        # Negative or flat suggests noise
        if slope > 0.5:
            # Increasing trend detected - count gaps above minimum
            return sum(1 for g in timeline.gaps if g.duration >= 3)
        else:
            # No clear trend - use stricter threshold
            return sum(1 for g in timeline.gaps if g.duration >= 6)

    def analyze(self) -> Dict:
        """Run full analysis pipeline"""
        print("[OBJECTIVE] Detect player deaths using progressive respawn timer patterns")

        # Load metadata
        player_map = self._load_player_metadata()
        print(f"[DATA] Loaded {len(player_map)} players, {self.total_frames} frames")

        # Build timelines
        self._build_timelines(player_map)

        # Apply multiple detection strategies
        results = {
            'replay_dir': str(self.replay_dir),
            'total_frames': self.total_frames,
            'players': [],
            'strategy_comparison': {},
        }

        print("\n[STAGE:begin:death_detection]")

        # Strategy 1: Progressive threshold
        strategy_results = defaultdict(list)

        for entity_id, timeline in self.entity_timelines.items():
            # Apply all three strategies
            prog_deaths = self._progressive_threshold_filter(timeline)
            cluster_deaths = self._clustering_filter(timeline)
            trend_deaths = self._increasing_trend_filter(timeline)

            strategy_results['progressive'].append((entity_id, prog_deaths))
            strategy_results['clustering'].append((entity_id, cluster_deaths))
            strategy_results['trend'].append((entity_id, trend_deaths))

            # Use trend filter as primary (most sophisticated)
            timeline.detected_deaths = trend_deaths

            results['players'].append(timeline.to_dict())

        # Evaluate each strategy
        for strategy_name, detections in strategy_results.items():
            errors = []
            for entity_id, detected in detections:
                truth = self.TRUTH_DEATHS.get(entity_id, 0)
                error = abs(detected - truth)
                errors.append(error)

            total_error = sum(errors)
            mae = total_error / len(errors) if errors else 0
            perfect_matches = sum(1 for e in errors if e == 0)

            results['strategy_comparison'][strategy_name] = {
                'total_error': total_error,
                'mean_absolute_error': mae,
                'perfect_matches': perfect_matches,
                'total_players': len(errors),
            }

            print(f"[STAT:{strategy_name}_mae] {mae:.2f}")
            print(f"[STAT:{strategy_name}_perfect] {perfect_matches}/{len(errors)}")

        print("[STAGE:status:success]")
        print("[STAGE:end:death_detection]")

        # Generate findings
        self._generate_findings(results)

        return results

    def _generate_findings(self, results: Dict) -> None:
        """Generate analysis findings"""
        print("\n=== DEATH DETECTION RESULTS ===\n")

        for player in results['players']:
            entity_id = player['entity_id']
            name = player['player_name']
            hero = player['hero_name']
            truth = player['truth_deaths']
            detected = player['detected_deaths']
            gap_count = player['gap_count']

            match_symbol = "MATCH" if detected == truth else "MISS"

            print(f"[FINDING] {name} ({hero}): {detected} deaths detected vs {truth} truth [{match_symbol}]")
            print(f"  Entity {entity_id}, Team {player['team']}, {gap_count} gaps total")

            if player['gaps']:
                print(f"  Gap durations: {[g['duration'] for g in player['gaps']]}")
                progress_list = [f"{g['game_progress']:.1%}" for g in player['gaps']]
                print(f"  Gap game progress: {progress_list}")

        print("\n=== STRATEGY COMPARISON ===\n")

        best_strategy = None
        best_mae = float('inf')

        for strategy, metrics in results['strategy_comparison'].items():
            mae = metrics['mean_absolute_error']
            perfect = metrics['perfect_matches']
            total = metrics['total_players']

            print(f"[FINDING] {strategy.upper()} strategy: MAE={mae:.2f}, Perfect={perfect}/{total}")

            if mae < best_mae:
                best_mae = mae
                best_strategy = strategy

        print(f"\n[FINDING] Best strategy: {best_strategy} (MAE={best_mae:.2f})")
        print(f"[STAT:best_strategy] {best_strategy}")
        print(f"[STAT:best_mae] {best_mae:.2f}")


def main():
    """Main execution"""
    replay_dir = "D:/Desktop/My Folder/Game/VG/vg replay/21.11.04/cache/"
    output_path = Path("D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/respawn_timer_analysis.json")

    analyzer = RespawnTimerAnalyzer(replay_dir)
    results = analyzer.analyze()

    # Save results
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n[FINDING] Results saved to {output_path}")
    print(f"[STAT:output_size] {output_path.stat().st_size} bytes")


if __name__ == '__main__':
    main()
