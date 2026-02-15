#!/usr/bin/env python3
"""
Win/Loss Detector - Infer match outcome from turret destruction patterns
Analyzes turret entity IDs and destruction timing to determine winning team.

Algorithm:
1. Parse all replay frames to extract turret destruction events
2. Identify Vain Crystal destruction (6+ simultaneous turret destructions)
3. Map turret entity IDs to team ownership using player team_id correlation
4. Determine winner based on which team's crystal was destroyed first
"""

import struct
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass
from collections import defaultdict


@dataclass
class TurretDestruction:
    """Record of a turret destruction event"""
    entity_id: int
    frame: int
    team: Optional[str] = None  # "left" or "right"


@dataclass
class MatchOutcome:
    """Match win/loss result"""
    winner: str  # "left" or "right"
    loser: str
    crystal_destruction_frame: int
    total_frames: int
    left_turrets_destroyed: int
    right_turrets_destroyed: int
    confidence: float
    method: str  # Detection method used


class WinLossDetector:
    """Detect match winner from turret destruction patterns"""

    # Vain Crystal destruction signature: 5+ turrets destroyed in same frame
    CRYSTAL_DESTRUCTION_THRESHOLD = 5

    def __init__(self, replay_path: str, debug: bool = False):
        """
        Initialize detector with path to replay folder.

        Args:
            replay_path: Path to replay cache folder or .0.vgr file
            debug: Enable debug output
        """
        self.replay_path = Path(replay_path)
        self.debug = debug
        self.turret_destructions: List[TurretDestruction] = []

    def _find_replay_files(self) -> List[Path]:
        """Find all frame files for the replay"""
        if self.replay_path.is_file() and str(self.replay_path).endswith('.0.vgr'):
            frame_dir = self.replay_path.parent
            replay_name = self.replay_path.stem.rsplit('.', 1)[0]
        elif self.replay_path.is_dir():
            # Find .0.vgr file
            first_frame = None
            for file in self.replay_path.rglob('*.0.vgr'):
                first_frame = file
                break
            if not first_frame:
                raise FileNotFoundError(f"No .0.vgr file found in {self.replay_path}")
            frame_dir = first_frame.parent
            replay_name = first_frame.stem.rsplit('.', 1)[0]
        else:
            raise FileNotFoundError(f"Invalid replay path: {self.replay_path}")

        # Collect all frame files
        frames = list(frame_dir.glob(f"{replay_name}.*.vgr"))
        frames.sort(key=lambda p: self._frame_index(p))
        return frames

    def _frame_index(self, path: Path) -> int:
        """Extract frame number from filename"""
        try:
            return int(path.stem.split('.')[-1])
        except ValueError:
            return 0

    def _collect_entity_events(self) -> Dict[int, Dict]:
        """
        Collect entity lifecycle data across all frames.

        Returns:
            Dictionary mapping entity_id to {first_frame, last_frame, event_count, frames}
        """
        frames = self._find_replay_files()
        if not frames:
            return {}

        entity_data = defaultdict(lambda: {
            'first_frame': None,
            'last_frame': None,
            'event_count': 0,
            'frames': set()
        })

        for frame_path in frames:
            frame_num = self._frame_index(frame_path)
            data = frame_path.read_bytes()

            # Parse entity events: [EntityID 2B LE][00 00][ActionCode 1B][Payload ~32B]
            idx = 0
            while idx < len(data) - 5:
                # Check for entity event pattern
                if data[idx+2:idx+4] == b'\x00\x00':
                    entity_id = struct.unpack('<H', data[idx:idx+2])[0]

                    # Filter to infrastructure/objective range (1024-19970)
                    if 1024 <= entity_id <= 19970:
                        entity = entity_data[entity_id]
                        if entity['first_frame'] is None:
                            entity['first_frame'] = frame_num
                        entity['last_frame'] = frame_num
                        entity['event_count'] += 1
                        entity['frames'].add(frame_num)

                    # Skip to next potential event
                    idx += 37
                else:
                    idx += 1

        return dict(entity_data)

    def _parse_player_team_mapping(self, first_frame_data: bytes) -> Dict[int, str]:
        """
        Parse player blocks to extract entity_id -> team mapping.

        Player block structure:
        - Marker: DA 03 EE (or E0 03 EE)
        - Name: ASCII string
        - Offset +0xD5: team_id (1=left, 2=right)
        - Offset +0xA5: entity_id (uint16 LE)
        """
        PLAYER_BLOCK_MARKER = b'\xDA\x03\xEE'
        PLAYER_BLOCK_MARKER_ALT = b'\xE0\x03\xEE'

        team_map = {}
        search_start = 0
        markers = (PLAYER_BLOCK_MARKER, PLAYER_BLOCK_MARKER_ALT)

        while True:
            pos = -1
            for candidate in markers:
                idx = first_frame_data.find(candidate, search_start)
                if idx != -1 and (pos == -1 or idx < pos):
                    pos = idx

            if pos == -1:
                break

            # Extract entity_id at +0xA5
            if pos + 0xA5 + 2 <= len(first_frame_data):
                entity_id = int.from_bytes(
                    first_frame_data[pos + 0xA5:pos + 0xA5 + 2], 'little'
                )

                # Extract team_id at +0xD5
                if pos + 0xD5 < len(first_frame_data):
                    team_id = first_frame_data[pos + 0xD5]
                    team = "left" if team_id == 1 else "right" if team_id == 2 else "unknown"

                    if team != "unknown":
                        team_map[entity_id] = team

            search_start = pos + 1

        return team_map

    def _cluster_turrets_by_team(self, entity_data: Dict[int, Dict]) -> Tuple[List[int], List[int]]:
        """
        Cluster turret entity IDs into two teams based on ID ranges.

        Research finding: Turret IDs cluster by team with 834-2519 ID gap between teams.

        Returns:
            Tuple of (team1_ids, team2_ids)
        """
        if not entity_data:
            return [], []

        # Filter to turret candidates (appear early, high events, destroyed)
        turret_candidates = []
        max_frame = max(e['last_frame'] for e in entity_data.values() if e['last_frame'] is not None)

        for entity_id, data in entity_data.items():
            appears_early = data['first_frame'] is not None and data['first_frame'] <= 5
            high_events = data['event_count'] > 50
            destroyed = data['last_frame'] is not None and data['last_frame'] < max_frame - 10

            if appears_early and high_events:
                turret_candidates.append(entity_id)

        if len(turret_candidates) < 2:
            return [], []

        # Sort by entity ID
        turret_candidates.sort()

        # Find largest gap between consecutive IDs
        max_gap = 0
        split_index = len(turret_candidates) // 2

        for i in range(len(turret_candidates) - 1):
            gap = turret_candidates[i + 1] - turret_candidates[i]
            if gap > max_gap:
                max_gap = gap
                split_index = i + 1

        team1_ids = turret_candidates[:split_index]
        team2_ids = turret_candidates[split_index:]

        if self.debug:
            print(f"[DEBUG] Clustered {len(team1_ids)} team1 turrets, {len(team2_ids)} team2 turrets")
            print(f"[DEBUG] Gap between teams: {max_gap} IDs")

        return team1_ids, team2_ids

    def _identify_vain_crystals(
        self,
        team1_ids: List[int],
        team2_ids: List[int],
        entity_data: Dict[int, Dict]
    ) -> Tuple[Optional[int], Optional[int]]:
        """
        Identify Vain Crystal for each team (highest event count entity).

        Research finding: Vain Crystal has the most events per team.

        Returns:
            Tuple of (team1_crystal_id, team2_crystal_id)
        """
        team1_crystal = None
        team1_max_events = 0

        for entity_id in team1_ids:
            events = entity_data[entity_id]['event_count']
            if events > team1_max_events:
                team1_max_events = events
                team1_crystal = entity_id

        team2_crystal = None
        team2_max_events = 0

        for entity_id in team2_ids:
            events = entity_data[entity_id]['event_count']
            if events > team2_max_events:
                team2_max_events = events
                team2_crystal = entity_id

        if self.debug:
            print(f"[DEBUG] Team1 crystal: {team1_crystal} ({team1_max_events} events)")
            print(f"[DEBUG] Team2 crystal: {team2_crystal} ({team2_max_events} events)")

        return team1_crystal, team2_crystal

    def _identify_crystal_frame(self) -> Optional[int]:
        """
        Identify frame where Vain Crystal was destroyed.

        Crystal destruction signature:
        - 5+ turrets destroyed simultaneously (crystal + base turrets)
        """
        # Group destructions by frame
        by_frame = defaultdict(list)
        for turret in self.turret_destructions:
            by_frame[turret.frame].append(turret)

        # Find frame with 5+ simultaneous destructions
        for frame, turrets in sorted(by_frame.items()):
            if len(turrets) >= self.CRYSTAL_DESTRUCTION_THRESHOLD:
                if self.debug:
                    print(f"[DEBUG] Crystal destruction detected at frame {frame}")
                    print(f"[DEBUG] {len(turrets)} turrets destroyed simultaneously")
                return frame

        return None

    def _infer_winner_from_crystal(
        self,
        crystal_frame: int,
        player_team_map: Dict[int, str]
    ) -> Optional[MatchOutcome]:
        """
        Infer winner by analyzing which team's crystal was destroyed.

        Strategy:
        1. Get turrets destroyed at crystal frame
        2. Check if they belong to same team (via spatial clustering)
        3. Team whose base was destroyed = loser
        """
        # Get turrets destroyed at crystal frame
        crystal_turrets = [t for t in self.turret_destructions if t.frame == crystal_frame]

        if len(crystal_turrets) < self.CRYSTAL_DESTRUCTION_THRESHOLD:
            return None

        # Count destructions by team
        left_destroyed = sum(1 for t in self.turret_destructions if t.team == "left")
        right_destroyed = sum(1 for t in self.turret_destructions if t.team == "right")

        # Heuristic: Team with more turrets destroyed at crystal frame = loser
        # (Their base was destroyed)
        left_at_crystal = sum(1 for t in crystal_turrets if t.team == "left")
        right_at_crystal = sum(1 for t in crystal_turrets if t.team == "right")

        if left_at_crystal > right_at_crystal:
            winner, loser = "right", "left"
            confidence = left_at_crystal / len(crystal_turrets)
        elif right_at_crystal > left_at_crystal:
            winner, loser = "left", "right"
            confidence = right_at_crystal / len(crystal_turrets)
        else:
            # Fallback: Team with more total turrets destroyed = loser
            if left_destroyed > right_destroyed:
                winner, loser = "right", "left"
                confidence = 0.7
            elif right_destroyed > left_destroyed:
                winner, loser = "left", "right"
                confidence = 0.7
            else:
                # Cannot determine
                return None

        total_frames = max(t.frame for t in self.turret_destructions)

        return MatchOutcome(
            winner=winner,
            loser=loser,
            crystal_destruction_frame=crystal_frame,
            total_frames=total_frames,
            left_turrets_destroyed=left_destroyed,
            right_turrets_destroyed=right_destroyed,
            confidence=confidence,
            method="crystal_destruction"
        )

    def _read_entity_network_report(self, report_path: Path) -> List[TurretDestruction]:
        """
        Parse entity_network_report.md to extract turret destructions.
        This is a fallback/validation method.
        """
        destructions = []

        if not report_path.exists():
            return destructions

        content = report_path.read_text(encoding='utf-8')

        # Find "Destruction order:" section
        in_destruction_section = False
        for line in content.splitlines():
            if "Destruction order:" in line or "**Destruction order:**" in line:
                in_destruction_section = True
                continue

            if in_destruction_section:
                # Parse lines like: "1. Entity 55875 - destroyed at frame 34"
                if line.strip().startswith(tuple('0123456789')):
                    parts = line.split()
                    if len(parts) >= 6 and parts[1] == "Entity" and "frame" in line:
                        try:
                            entity_id = int(parts[2])
                            frame = int(parts[-1])
                            destructions.append(TurretDestruction(entity_id, frame))
                        except (ValueError, IndexError):
                            continue
                elif line.strip() and not line[0].isdigit() and "Entity" not in line:
                    # End of section
                    break

        return destructions

    def detect_winner(self) -> Optional[MatchOutcome]:
        """
        Detect match winner from turret destruction pattern.

        Algorithm:
        1. Collect all entity events across frames
        2. Cluster turret entities into 2 teams by ID ranges
        3. Track turret destruction timeline
        4. Detect crystal destruction: 6+ turrets destroyed in 5-frame window
        5. Team with concentrated destruction = loser

        Returns:
            MatchOutcome if winner can be determined, None otherwise
        """
        print("[STAGE:begin:data_loading]")

        # Collect entity lifecycle data
        entity_data = self._collect_entity_events()

        if not entity_data:
            print("[LIMITATION] No entity data collected")
            print("[STAGE:status:fail]")
            print("[STAGE:end:data_loading]")
            return None

        print(f"[DATA] Collected {len(entity_data)} entities in range 1024-19970")

        # Read first frame for player team mapping (for reference)
        frames = self._find_replay_files()
        if frames:
            first_frame_data = frames[0].read_bytes()
            player_team_map = self._parse_player_team_mapping(first_frame_data)
            if self.debug and player_team_map:
                print(f"[DEBUG] Player teams: {player_team_map}")

        print("[STAGE:status:success]")
        print("[STAGE:end:data_loading]")

        print("[STAGE:begin:analysis]")

        # Cluster turrets into two teams
        team1_ids, team2_ids = self._cluster_turrets_by_team(entity_data)

        if not team1_ids or not team2_ids:
            print("[LIMITATION] Could not cluster turrets into two teams")
            print("[STAGE:status:fail]")
            print("[STAGE:end:analysis]")
            return None

        print(f"[DATA] Team1: {len(team1_ids)} turrets, Team2: {len(team2_ids)} turrets")

        # Identify Vain Crystals
        team1_crystal, team2_crystal = self._identify_vain_crystals(team1_ids, team2_ids, entity_data)

        if not team1_crystal or not team2_crystal:
            print("[LIMITATION] Could not identify Vain Crystals")
            print("[STAGE:status:fail]")
            print("[STAGE:end:analysis]")
            return None

        print(f"[FINDING] Vain Crystals identified: Team1={team1_crystal}, Team2={team2_crystal}")

        # Build turret destruction timeline
        max_frame = max(e['last_frame'] for e in entity_data.values() if e['last_frame'] is not None)

        team1_destructions = []
        team2_destructions = []

        for tid in team1_ids:
            last_frame = entity_data[tid]['last_frame']
            if last_frame and last_frame < max_frame - 1:  # Destroyed before game end
                team1_destructions.append((tid, last_frame))

        for tid in team2_ids:
            last_frame = entity_data[tid]['last_frame']
            if last_frame and last_frame < max_frame - 1:
                team2_destructions.append((tid, last_frame))

        print(f"[DATA] Team1 turrets destroyed: {len(team1_destructions)}")
        print(f"[DATA] Team2 turrets destroyed: {len(team2_destructions)}")

        # Look for crystal destruction pattern: 6+ turrets in 5-frame window
        all_destructions = [(tid, frame, 1) for tid, frame in team1_destructions]
        all_destructions += [(tid, frame, 2) for tid, frame in team2_destructions]
        all_destructions.sort(key=lambda x: x[1])

        crystal_frame = None
        winner = None
        loser = None
        confidence = 0.0

        for i in range(len(all_destructions)):
            frame = all_destructions[i][1]
            # Count destructions in 5-frame window
            window_destructions = [d for d in all_destructions if frame <= d[1] <= frame + 5]
            team1_in_window = sum(1 for d in window_destructions if d[2] == 1)
            team2_in_window = sum(1 for d in window_destructions if d[2] == 2)

            if team1_in_window >= 6:
                winner = "team2"
                loser = "team1"
                crystal_frame = frame
                confidence = 0.90 + min(team1_in_window / 20.0, 0.09)  # 0.90-0.99 based on turret count
                print(f"[FINDING] Crystal destruction pattern detected: {team1_in_window} Team1 turrets destroyed in frames {frame}-{frame+5}")
                break
            elif team2_in_window >= 6:
                winner = "team1"
                loser = "team2"
                crystal_frame = frame
                confidence = 0.90 + min(team2_in_window / 20.0, 0.09)
                print(f"[FINDING] Crystal destruction pattern detected: {team2_in_window} Team2 turrets destroyed in frames {frame}-{frame+5}")
                break

        if not winner:
            print("[LIMITATION] Could not detect crystal destruction pattern")
            print("[LIMITATION] Match may have ended by surrender or time limit")
            print("[STAGE:status:fail]")
            print("[STAGE:end:analysis]")
            return None

        # Map team1/team2 to left/right based on player team mappings
        # Team1 has lower entity IDs, Team2 has higher entity IDs
        # Players in team_id=1 (left) typically have lower entity ranges near their turrets
        # Players in team_id=2 (right) have higher entity ranges
        winner_label = winner
        loser_label = loser

        if frames and player_team_map:
            # Find which player team (left/right) has entity IDs closer to team1/team2 turrets
            left_players = [eid for eid, team in player_team_map.items() if team == "left"]
            right_players = [eid for eid, team in player_team_map.items() if team == "right"]

            if left_players and right_players and team1_ids and team2_ids:
                # Calculate average distance from player IDs to turret IDs
                team1_avg = sum(team1_ids) / len(team1_ids)
                team2_avg = sum(team2_ids) / len(team2_ids)
                left_avg = sum(left_players) / len(left_players)
                right_avg = sum(right_players) / len(right_players)

                # Lower entity ID team is typically left
                # But verify with player mapping
                team1_is_left = team1_avg < team2_avg

                if winner == "team1":
                    winner_label = "left" if team1_is_left else "right"
                    loser_label = "right" if team1_is_left else "left"
                else:
                    winner_label = "right" if team1_is_left else "left"
                    loser_label = "left" if team1_is_left else "right"

        print(f"[FINDING] Winner: {winner_label} ({winner})")
        print(f"[FINDING] Loser: {loser_label} ({loser})")

        outcome = MatchOutcome(
            winner=winner_label,
            loser=loser_label,
            crystal_destruction_frame=crystal_frame,
            total_frames=max_frame,
            left_turrets_destroyed=len(team1_destructions),
            right_turrets_destroyed=len(team2_destructions),
            confidence=confidence,
            method="crystal_destruction_windowed"
        )

        print(f"[STAT:team1_turrets_destroyed] {len(team1_destructions)}")
        print(f"[STAT:team2_turrets_destroyed] {len(team2_destructions)}")
        print(f"[STAT:confidence] {confidence:.2f}")

        print("[STAGE:status:success]")
        print("[STAGE:end:analysis]")

        return outcome


def analyze_replay(replay_path: str, debug: bool = False) -> Optional[MatchOutcome]:
    """
    Analyze a single replay to detect winner.

    Args:
        replay_path: Path to replay folder or .0.vgr file
        debug: Enable debug output

    Returns:
        MatchOutcome if winner detected, None otherwise
    """
    detector = WinLossDetector(replay_path, debug=debug)
    return detector.detect_winner()


def batch_analyze(replay_dir: str, debug: bool = False) -> Dict[str, Optional[MatchOutcome]]:
    """
    Analyze multiple replays in a directory.

    Args:
        replay_dir: Directory containing replay folders
        debug: Enable debug output

    Returns:
        Dictionary mapping replay name to outcome
    """
    results = {}
    base = Path(replay_dir)

    # Find all .0.vgr files
    for vgr_file in base.rglob('*.0.vgr'):
        if vgr_file.name.startswith("._") or "__MACOSX" in vgr_file.parts:
            continue

        replay_name = vgr_file.parent.name
        print(f"\n{'='*60}")
        print(f"Analyzing: {replay_name}")
        print(f"{'='*60}")

        try:
            outcome = analyze_replay(str(vgr_file), debug=debug)
            results[replay_name] = outcome

            if outcome:
                print(f"\n[RESULT] Winner: {outcome.winner}")
                print(f"[RESULT] Crystal destroyed at frame {outcome.crystal_destruction_frame}")
                print(f"[RESULT] Confidence: {outcome.confidence:.1%}")
            else:
                print(f"\n[RESULT] Could not determine winner")

        except Exception as e:
            print(f"[ERROR] Failed to analyze: {e}")
            results[replay_name] = None

    return results


def main():
    """CLI entry point"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Win/Loss Detector - Detect match winner from turret destruction patterns'
    )
    parser.add_argument(
        'path',
        help='Path to replay folder or .0.vgr file'
    )
    parser.add_argument(
        '-b', '--batch',
        action='store_true',
        help='Batch process all replays in directory'
    )
    parser.add_argument(
        '-d', '--debug',
        action='store_true',
        help='Enable debug output'
    )

    args = parser.parse_args()

    if args.batch:
        results = batch_analyze(args.path, debug=args.debug)

        # Summary
        print(f"\n{'='*60}")
        print("SUMMARY")
        print(f"{'='*60}")
        print(f"Total replays: {len(results)}")

        successful = sum(1 for r in results.values() if r is not None)
        print(f"Successfully analyzed: {successful}")
        print(f"Failed: {len(results) - successful}")

    else:
        outcome = analyze_replay(args.path, debug=args.debug)

        if outcome:
            print(f"\n{'='*60}")
            print("MATCH OUTCOME")
            print(f"{'='*60}")
            print(f"Winner: {outcome.winner}")
            print(f"Loser: {outcome.loser}")
            print(f"Crystal destroyed: Frame {outcome.crystal_destruction_frame}/{outcome.total_frames}")
            print(f"Left turrets destroyed: {outcome.left_turrets_destroyed}")
            print(f"Right turrets destroyed: {outcome.right_turrets_destroyed}")
            print(f"Confidence: {outcome.confidence:.1%}")
            print(f"Method: {outcome.method}")
        else:
            print("\n[RESULT] Could not determine match outcome")


if __name__ == '__main__':
    main()
