#!/usr/bin/env python3
"""
Turret Team Mapper - Binary analysis to identify turret entities and map to teams

Analyzes Vainglory replay binary files to:
1. Track entity lifecycle across all frames
2. Identify turret entities by characteristics (persistent, high event count, destruction)
3. Map turrets to teams (left=1, right=2) using multiple strategies
4. Cross-validate patterns across replays

Entity event format: [EntityID 2B LE][00 00][ActionCode 1B][Payload 32B]
Player block: marker DA 03 EE, team at +0xD5, entity_id at +0xA5 (uint16 LE)
"""

import os
import sys
import json
import struct
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set, Tuple, Optional


class EntityLifecycle:
    """Track entity appearance across frames"""
    def __init__(self, entity_id: int):
        self.entity_id = entity_id
        self.first_frame = None
        self.last_frame = None
        self.frames = set()
        self.event_count = 0

    def add_event(self, frame_num: int):
        if self.first_frame is None:
            self.first_frame = frame_num
        self.last_frame = frame_num
        self.frames.add(frame_num)
        self.event_count += 1

    def is_turret_candidate(self, max_frame: int) -> bool:
        """Check if entity characteristics match turret pattern"""
        if self.first_frame is None:
            return False

        # Turrets should:
        # 1. Exist from frame 0 or very early (game start)
        # 2. Have high event count (stationary, broadcasting state)
        # 3. Stop appearing permanently (destruction)
        # 4. Be in infrastructure range 1000-20000

        appears_early = self.first_frame <= 5  # Allow some buffer
        has_high_events = self.event_count > 50  # Turrets broadcast state frequently
        destroyed_before_end = self.last_frame < max_frame - 10  # Destroyed before game end
        in_turret_range = 1000 <= self.entity_id <= 20000

        return appears_early and has_high_events and in_turret_range

    def to_dict(self):
        return {
            'entity_id': self.entity_id,
            'first_frame': self.first_frame,
            'last_frame': self.last_frame,
            'frame_count': len(self.frames),
            'event_count': self.event_count,
            'destroyed': self.last_frame is not None
        }


class TurretTeamMapper:
    """Analyze replay binary to map turret entities to teams"""

    PLAYER_MARKER = b'\xDA\x03\xEE'
    TEAM_OFFSET = 0xD5
    ENTITY_ID_OFFSET = 0xA5

    def __init__(self, cache_dir: str):
        self.cache_dir = Path(cache_dir)
        self.entity_lifecycles: Dict[int, EntityLifecycle] = {}
        self.max_frame = 0
        self.player_teams: Dict[int, int] = {}  # entity_id -> team (1=left, 2=right)

    def parse_all_frames(self) -> None:
        """Parse all .vgr frames to build entity lifecycle data"""
        print(f"[STAGE:begin:parse_frames]")

        vgr_files = sorted(self.cache_dir.glob("*.vgr"), key=lambda p: self._get_frame_num(p))

        if not vgr_files:
            print(f"[LIMITATION] No .vgr files found in {self.cache_dir}")
            return

        print(f"[DATA] Found {len(vgr_files)} frame files")

        for frame_path in vgr_files:
            frame_num = self._get_frame_num(frame_path)
            self.max_frame = max(self.max_frame, frame_num)

            with open(frame_path, 'rb') as f:
                data = f.read()

            # Parse entity events: [EntityID 2B LE][00 00][ActionCode 1B][Payload 32B]
            # Pattern: 2 bytes entity ID, 2 bytes 00 00, 1 byte action code
            i = 0
            while i < len(data) - 5:
                # Check for entity event pattern
                if data[i+2:i+4] == b'\x00\x00':
                    entity_id = struct.unpack('<H', data[i:i+2])[0]

                    # Track entity lifecycle
                    if entity_id not in self.entity_lifecycles:
                        self.entity_lifecycles[entity_id] = EntityLifecycle(entity_id)
                    self.entity_lifecycles[entity_id].add_event(frame_num)

                    # Skip to next potential event (37 bytes total: 2+2+1+32)
                    i += 37
                else:
                    i += 1

            # Parse player blocks in frame 0 for team mapping
            if frame_num == 0:
                self._parse_player_blocks(data)

        print(f"[DATA] Parsed {self.max_frame + 1} frames, tracked {len(self.entity_lifecycles)} unique entities")
        print(f"[STAT:total_entities] {len(self.entity_lifecycles)}")
        print(f"[STAT:total_frames] {self.max_frame + 1}")
        print(f"[STAGE:status:success]")
        print(f"[STAGE:end:parse_frames]")

    def _get_frame_num(self, path: Path) -> int:
        """Extract frame number from filename"""
        stem = path.stem  # e.g., "replay-uuid.123"
        return int(stem.split('.')[-1])

    def _parse_player_blocks(self, data: bytes) -> None:
        """Parse player blocks from frame 0 to extract team assignments"""
        print(f"[STAGE:begin:parse_players]")

        # Find player markers (DA 03 EE)
        pos = 0
        player_count = 0

        while True:
            pos = data.find(self.PLAYER_MARKER, pos)
            if pos == -1:
                break

            # Check if we have enough data for offsets
            if pos + self.TEAM_OFFSET + 1 < len(data) and pos + self.ENTITY_ID_OFFSET + 2 < len(data):
                team = data[pos + self.TEAM_OFFSET]
                entity_id = struct.unpack('<H', data[pos + self.ENTITY_ID_OFFSET:pos + self.ENTITY_ID_OFFSET + 2])[0]

                if team in [1, 2] and 50000 <= entity_id <= 60000:
                    self.player_teams[entity_id] = team
                    player_count += 1

            pos += 1

        print(f"[DATA] Found {player_count} players in frame 0")
        team1_count = sum(1 for t in self.player_teams.values() if t == 1)
        team2_count = sum(1 for t in self.player_teams.values() if t == 2)
        print(f"[STAT:team1_players] {team1_count}")
        print(f"[STAT:team2_players] {team2_count}")
        print(f"[STAGE:status:success]")
        print(f"[STAGE:end:parse_players]")

    def identify_turrets(self) -> List[EntityLifecycle]:
        """Identify turret entities by characteristics"""
        print(f"[STAGE:begin:identify_turrets]")

        turret_candidates = []

        for entity_id, lifecycle in self.entity_lifecycles.items():
            if lifecycle.is_turret_candidate(self.max_frame):
                turret_candidates.append(lifecycle)

        # Sort by entity ID
        turret_candidates.sort(key=lambda e: e.entity_id)

        print(f"[FINDING] Identified {len(turret_candidates)} turret candidates")
        print(f"[STAT:turret_count] {len(turret_candidates)}")

        # Analyze characteristics
        if turret_candidates:
            avg_events = sum(t.event_count for t in turret_candidates) / len(turret_candidates)
            print(f"[STAT:avg_turret_events] {avg_events:.1f}")

            # Show turret ID ranges
            min_id = min(t.entity_id for t in turret_candidates)
            max_id = max(t.entity_id for t in turret_candidates)
            print(f"[STAT:turret_id_range] {min_id}-{max_id}")

        print(f"[STAGE:status:success]")
        print(f"[STAGE:end:identify_turrets]")

        return turret_candidates

    def map_turrets_to_teams(self, turrets: List[EntityLifecycle]) -> Dict[int, int]:
        """Map turret entity IDs to teams using multiple strategies"""
        print(f"[STAGE:begin:map_teams]")

        team_mapping = {}

        # Strategy 1: Cluster by entity ID ranges
        # Assumption: each team's turrets are in consecutive ID ranges
        if len(turrets) >= 6:  # Minimum for 3v3 mode (3 turrets per team)
            turret_ids = sorted([t.entity_id for t in turrets])

            # Look for gap in entity IDs
            max_gap = 0
            gap_index = len(turret_ids) // 2  # Default to middle

            for i in range(len(turret_ids) - 1):
                gap = turret_ids[i + 1] - turret_ids[i]
                if gap > max_gap:
                    max_gap = gap
                    gap_index = i + 1

            # Split by gap
            team1_ids = turret_ids[:gap_index]
            team2_ids = turret_ids[gap_index:]

            print(f"[FINDING] ID clustering strategy: split at index {gap_index} (gap={max_gap})")
            print(f"[STAT:cluster_team1_count] {len(team1_ids)}")
            print(f"[STAT:cluster_team2_count] {len(team2_ids)}")

            for tid in team1_ids:
                team_mapping[tid] = 1
            for tid in team2_ids:
                team_mapping[tid] = 2

        # Strategy 2: Destruction timing analysis
        # Turrets destroyed near crystal frame likely belong to losing team
        turret_destruction_frames = [(t.entity_id, t.last_frame) for t in turrets if t.last_frame]
        turret_destruction_frames.sort(key=lambda x: x[1])

        if turret_destruction_frames:
            # Find the last destroyed turret (likely crystal or final objective)
            crystal_frame = max(f for _, f in turret_destruction_frames)
            print(f"[STAT:crystal_frame] {crystal_frame}")

            # Turrets destroyed within 50 frames of crystal likely same team
            late_destruction = [(tid, f) for tid, f in turret_destruction_frames if f > crystal_frame - 50]
            print(f"[FINDING] {len(late_destruction)} turrets destroyed near crystal frame")

        print(f"[STAGE:status:success]")
        print(f"[STAGE:end:map_teams]")

        return team_mapping

    def analyze_replay(self) -> Dict:
        """Full analysis pipeline"""
        print(f"[OBJECTIVE] Analyze turret entities and map to teams for replay in {self.cache_dir}")

        self.parse_all_frames()
        turrets = self.identify_turrets()
        team_mapping = self.map_turrets_to_teams(turrets)

        # Build results
        results = {
            'replay_path': str(self.cache_dir),
            'total_frames': self.max_frame + 1,
            'total_entities': len(self.entity_lifecycles),
            'turret_count': len(turrets),
            'players': {
                'team1': sum(1 for t in self.player_teams.values() if t == 1),
                'team2': sum(1 for t in self.player_teams.values() if t == 2)
            },
            'turrets': [t.to_dict() for t in turrets],
            'team_mapping': team_mapping,
            'entity_ranges': self._analyze_entity_ranges()
        }

        return results

    def _analyze_entity_ranges(self) -> Dict:
        """Analyze entity ID distributions by range"""
        ranges = {
            'system': [],           # 0
            'infrastructure': [],   # 1-1000
            'objectives': [],       # 1000-20000
            'unknown1': [],         # 20000-50000
            'players': [],          # 50000-60000
            'unknown2': []          # 60000+
        }

        for entity_id in self.entity_lifecycles.keys():
            if entity_id == 0:
                ranges['system'].append(entity_id)
            elif 1 <= entity_id <= 1000:
                ranges['infrastructure'].append(entity_id)
            elif 1001 <= entity_id <= 20000:
                ranges['objectives'].append(entity_id)
            elif 20001 <= entity_id <= 50000:
                ranges['unknown1'].append(entity_id)
            elif 50001 <= entity_id <= 60000:
                ranges['players'].append(entity_id)
            else:
                ranges['unknown2'].append(entity_id)

        return {k: len(v) for k, v in ranges.items()}


def main():
    if len(sys.argv) < 2:
        print("Usage: python turret_team_mapper.py <cache_directory>")
        print("Example: python turret_team_mapper.py 'D:/Desktop/My Folder/Game/VG/vg replay/21.11.04/cache/'")
        sys.exit(1)

    cache_dir = sys.argv[1]

    if not os.path.isdir(cache_dir):
        print(f"[LIMITATION] Cache directory not found: {cache_dir}")
        sys.exit(1)

    # Run analysis
    mapper = TurretTeamMapper(cache_dir)
    results = mapper.analyze_replay()

    # Save results
    output_path = Path("D:/Documents/GitHub/VG_REVERSE_ENGINEERING/vg/output/turret_team_analysis.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\n[FINDING] Analysis complete - results saved to {output_path}")

    # Print summary
    print("\n" + "="*60)
    print("TURRET ANALYSIS SUMMARY")
    print("="*60)
    print(f"Total frames analyzed: {results['total_frames']}")
    print(f"Total entities tracked: {results['total_entities']}")
    print(f"Turret candidates identified: {results['turret_count']}")
    print(f"\nPlayers detected:")
    print(f"  Team 1 (left): {results['players']['team1']}")
    print(f"  Team 2 (right): {results['players']['team2']}")
    print(f"\nEntity distribution:")
    for range_name, count in results['entity_ranges'].items():
        if count > 0:
            print(f"  {range_name}: {count}")

    if results['turrets']:
        print(f"\nTurret details:")
        for turret in results['turrets'][:10]:  # Show first 10
            team = results['team_mapping'].get(turret['entity_id'], '?')
            print(f"  Entity {turret['entity_id']}: frames {turret['first_frame']}-{turret['last_frame']}, "
                  f"events={turret['event_count']}, team={team}")
        if len(results['turrets']) > 10:
            print(f"  ... and {len(results['turrets']) - 10} more")

    print("\n[LIMITATION] Team mapping requires validation across multiple replays")
    print("[LIMITATION] Binary event pattern may need refinement based on actual data structure")


if __name__ == '__main__':
    main()
