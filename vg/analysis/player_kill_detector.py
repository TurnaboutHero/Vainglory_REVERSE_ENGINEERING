#!/usr/bin/env python3
"""
Player Kill Detector - Extract actual player kills from VG replay event streams

Filters the 6,008 kill candidates from entity_network_report.md to find
only real player kills by analyzing:
1. Player entity ID range (56325-58629)
2. Action code 0x44 events in late frames (51+)
3. Entity interaction patterns and lifecycle gaps
4. Target entity IDs in event payloads

Event structure: [EntityID(2B LE)][00 00][ActionCode(1B)][Payload(32B)]
"""

import struct
import sys
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Set, Optional
import json


@dataclass
class EventRecord:
    """Single event record from replay."""
    frame: int
    entity_id: int
    action_code: int
    payload: bytes
    target_entities: List[int] = field(default_factory=list)


@dataclass
class PlayerKill:
    """Confirmed player kill event."""
    killer_id: int
    killer_name: str
    victim_id: int
    victim_name: str
    frame: int
    action_code: int
    victim_last_frame: int
    victim_respawn_frame: Optional[int]
    gap_frames: int
    confidence: float
    evidence: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "killer_id": self.killer_id,
            "killer_name": self.killer_name,
            "victim_id": self.victim_id,
            "victim_name": self.victim_name,
            "frame": self.frame,
            "action_code": f"0x{self.action_code:02X}",
            "victim_last_frame": self.victim_last_frame,
            "victim_respawn_frame": self.victim_respawn_frame,
            "gap_frames": self.gap_frames,
            "confidence": round(self.confidence, 2),
            "evidence": self.evidence,
        }


class PlayerKillDetector:
    """Detects player kill events from replay data."""

    # Player entity ID range (from entity_network_report.md)
    PLAYER_ENTITY_MIN = 56325
    PLAYER_ENTITY_MAX = 58629

    # Frame gap to consider entity dead/respawned
    DEATH_GAP_THRESHOLD = 3

    # Action codes of interest (interaction/combat)
    ATTACK_ACTIONS = {0x42, 0x43, 0x44}

    def __init__(self, replay_path: str):
        """Initialize detector."""
        self.replay_path = Path(replay_path)
        self.frame_dir, self.replay_name = self._find_replay_files()

        # Data structures
        self.frames: List[Tuple[int, bytes]] = []
        self.player_entities: Dict[int, str] = {}
        self.events_by_frame: Dict[int, List[EventRecord]] = defaultdict(list)
        self.entity_frames: Dict[int, Set[int]] = defaultdict(set)
        self.player_kills: List[PlayerKill] = []

    def _find_replay_files(self) -> Tuple[Path, str]:
        """Find replay frame directory and name."""
        if self.replay_path.is_file() and str(self.replay_path).endswith('.vgr'):
            frame_dir = self.replay_path.parent
            stem = self.replay_path.stem
            replay_name = stem.rsplit('.', 1)[0] if '.' in stem else stem
            return frame_dir, replay_name

        if self.replay_path.is_dir():
            for f in self.replay_path.rglob('*.0.vgr'):
                frame_dir = f.parent
                stem = f.stem
                replay_name = stem.rsplit('.', 1)[0] if '.' in stem else stem
                return frame_dir, replay_name

        raise FileNotFoundError(f"No .vgr files found at {self.replay_path}")

    def load_frames(self):
        """Load all frame files."""
        print(f"[INFO] Loading frames from {self.frame_dir}")
        files = list(self.frame_dir.glob(f"{self.replay_name}.*.vgr"))

        for f in files:
            try:
                idx = int(f.stem.split('.')[-1])
            except ValueError:
                idx = 0
            data = f.read_bytes()
            self.frames.append((idx, data))

        self.frames.sort(key=lambda x: x[0])
        print(f"[DATA] Loaded {len(self.frames)} frames")

    def extract_player_entities(self):
        """Extract player entities from first frame."""
        if not self.frames:
            return

        PLAYER_BLOCK_MARKER = bytes([0xDA, 0x03, 0xEE])
        PLAYER_BLOCK_MARKER_ALT = bytes([0xE0, 0x03, 0xEE])
        ENTITY_ID_OFFSET = 0xA5

        first_frame_data = self.frames[0][1]
        search_start = 0
        markers = (PLAYER_BLOCK_MARKER, PLAYER_BLOCK_MARKER_ALT)

        while True:
            pos = -1
            marker = None
            for candidate in markers:
                idx = first_frame_data.find(candidate, search_start)
                if idx != -1 and (pos == -1 or idx < pos):
                    pos = idx
                    marker = candidate

            if pos == -1 or marker is None:
                break

            name_start = pos + len(marker)
            name_end = name_start
            while name_end < len(first_frame_data) and name_end < name_start + 30:
                byte = first_frame_data[name_end]
                if byte < 32 or byte > 126:
                    break
                name_end += 1

            if name_end > name_start:
                try:
                    name = first_frame_data[name_start:name_end].decode('ascii')
                except Exception:
                    name = ""

                if len(name) >= 3 and not name.startswith('GameMode'):
                    if pos + ENTITY_ID_OFFSET + 2 <= len(first_frame_data):
                        entity_id = struct.unpack('<H',
                            first_frame_data[pos + ENTITY_ID_OFFSET:pos + ENTITY_ID_OFFSET + 2])[0]
                        if entity_id not in self.player_entities:
                            self.player_entities[entity_id] = name

            search_start = pos + 1

        print(f"[DATA] Found {len(self.player_entities)} player entities: {list(self.player_entities.values())}")

    def scan_all_events(self):
        """Scan all frames for events and build interaction map."""
        print("[INFO] Scanning all events...")

        for frame_idx, data in self.frames:
            self._scan_frame_events(frame_idx, data)

        print(f"[STAT:total_frames] {len(self.frames)}")
        print(f"[STAT:events_scanned] {sum(len(events) for events in self.events_by_frame.values())}")
        print(f"[STAT:entities_tracked] {len(self.entity_frames)}")

    def _scan_frame_events(self, frame_idx: int, data: bytes):
        """Scan single frame for all events."""
        length = len(data)
        if length < 37:  # Need at least header + 32-byte payload
            return

        idx = 0
        while idx <= length - 37:
            # Look for event pattern: [EntityID(2B)][00 00][ActionCode(1B)][Payload(32B)]
            if data[idx + 2] == 0x00 and data[idx + 3] == 0x00:
                entity_id = struct.unpack('<H', data[idx:idx+2])[0]
                action_code = data[idx + 4]

                if action_code in self.ATTACK_ACTIONS:
                    # Extract 32-byte payload
                    payload_start = idx + 5
                    payload_end = min(payload_start + 32, length)
                    payload = data[payload_start:payload_end]

                    # Parse target entities from payload
                    target_entities = self._extract_target_entities(payload)

                    event = EventRecord(
                        frame=frame_idx,
                        entity_id=entity_id,
                        action_code=action_code,
                        payload=payload,
                        target_entities=target_entities,
                    )

                    self.events_by_frame[frame_idx].append(event)
                    self.entity_frames[entity_id].add(frame_idx)

                idx += 5
            else:
                idx += 1

    def _extract_target_entities(self, payload: bytes) -> List[int]:
        """Extract potential target entity IDs from payload."""
        targets = []

        # Check known entity ID offsets (2-byte aligned positions)
        # Based on payload structure analysis: offsets 0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22
        for offset in [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22]:
            if offset + 2 <= len(payload):
                value = struct.unpack('<H', payload[offset:offset+2])[0]
                # Filter to reasonable entity ID range
                if 0 < value < 65535:
                    targets.append(value)

        return targets

    def _is_player_entity(self, entity_id: int) -> bool:
        """Check if entity ID is a player."""
        return self.PLAYER_ENTITY_MIN <= entity_id <= self.PLAYER_ENTITY_MAX

    def _compute_lifecycle_gaps(self, entity_id: int) -> List[Tuple[int, int, Optional[int]]]:
        """
        Compute lifecycle gaps for an entity.

        Returns list of (last_frame_before_gap, gap_size, respawn_frame)
        """
        frames = sorted(self.entity_frames.get(entity_id, set()))
        if len(frames) < 2:
            return []

        gaps = []
        for i in range(len(frames) - 1):
            gap = frames[i + 1] - frames[i]
            if gap > self.DEATH_GAP_THRESHOLD:
                gaps.append((frames[i], gap, frames[i + 1]))

        # Check if entity never respawned (disappeared before end)
        if frames:
            last_frame = frames[-1]
            total_frames = max(self.entity_frames.keys(), default=0)
            if last_frame < total_frames - self.DEATH_GAP_THRESHOLD:
                gaps.append((last_frame, 9999, None))

        return gaps

    def detect_player_kills(self):
        """Detect player kill events from interaction patterns."""
        print("\n[INFO] Detecting player kills...")

        # Track player-to-player attacks
        player_attacks = defaultdict(list)  # (attacker, victim) -> [(frame, action_code)]

        for frame_idx, events in self.events_by_frame.items():
            for event in events:
                # Only consider events from player entities
                if not self._is_player_entity(event.entity_id):
                    continue

                # Check if any targets are player entities
                for target_id in event.target_entities:
                    if self._is_player_entity(target_id) and target_id != event.entity_id:
                        player_attacks[(event.entity_id, target_id)].append(
                            (frame_idx, event.action_code)
                        )

        print(f"[STAT:player_attack_pairs] {len(player_attacks)}")

        # Identify kills by matching attacks to victim disappearance
        for (attacker_id, victim_id), attacks in player_attacks.items():
            if not attacks:
                continue

            # Get victim lifecycle gaps (deaths)
            victim_gaps = self._compute_lifecycle_gaps(victim_id)

            if not victim_gaps:
                continue

            # For each attack, check if it coincides with a victim death
            for last_attack_frame, action_code in attacks:
                for death_frame, gap_size, respawn_frame in victim_gaps:
                    # Kill happened if attack was within 3 frames before death
                    if 0 <= death_frame - last_attack_frame <= 3:
                        # Calculate confidence
                        confidence = 0.5  # Base
                        evidence = []

                        # Boost confidence for late-game action (0x44)
                        if action_code == 0x44 and last_attack_frame >= 51:
                            confidence += 0.2
                            evidence.append("late_game_combat_0x44")

                        # Boost for multiple attacks on same victim
                        attack_count = len([f for f, _ in attacks if abs(f - last_attack_frame) <= 5])
                        if attack_count > 3:
                            confidence += 0.15
                            evidence.append(f"multiple_attacks_{attack_count}")

                        # Boost if victim had long gap (real death, not brief stun)
                        if gap_size > 10:
                            confidence += 0.1
                            evidence.append(f"long_death_gap_{gap_size}")

                        # Boost if attacker survived much longer
                        attacker_last = max(self.entity_frames.get(attacker_id, {0}))
                        if attacker_last > death_frame + 5:
                            confidence += 0.05
                            evidence.append("attacker_survived")

                        kill = PlayerKill(
                            killer_id=attacker_id,
                            killer_name=self.player_entities.get(attacker_id, f"entity_{attacker_id}"),
                            victim_id=victim_id,
                            victim_name=self.player_entities.get(victim_id, f"entity_{victim_id}"),
                            frame=last_attack_frame,
                            action_code=action_code,
                            victim_last_frame=death_frame,
                            victim_respawn_frame=respawn_frame,
                            gap_frames=gap_size,
                            confidence=min(confidence, 1.0),
                            evidence=evidence,
                        )

                        self.player_kills.append(kill)

        # Deduplicate (same kill detected from multiple attacks)
        seen = set()
        unique_kills = []
        for kill in sorted(self.player_kills, key=lambda k: -k.confidence):
            key = (kill.killer_id, kill.victim_id, kill.victim_last_frame)
            if key not in seen:
                seen.add(key)
                unique_kills.append(kill)

        self.player_kills = unique_kills

        print(f"[FINDING] Detected {len(self.player_kills)} player kill events")

        if self.player_kills:
            print("\nTop player kills:")
            for i, kill in enumerate(self.player_kills[:15], 1):
                print(f"{i}. {kill.killer_name} killed {kill.victim_name} "
                      f"at frame {kill.frame} (confidence: {kill.confidence:.2%})")
                print(f"   Evidence: {', '.join(kill.evidence)}")

    def generate_report(self, output_dir: Optional[Path] = None) -> Path:
        """Generate player kill detection report."""
        if output_dir is None:
            output_dir = self.frame_dir
        else:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

        report_data = {
            "replay_name": self.replay_name,
            "total_frames": len(self.frames),
            "player_entities": {
                str(eid): name for eid, name in self.player_entities.items()
            },
            "statistics": {
                "total_events": sum(len(events) for events in self.events_by_frame.values()),
                "entities_tracked": len(self.entity_frames),
                "player_kills_detected": len(self.player_kills),
            },
            "player_kills": [kill.to_dict() for kill in self.player_kills],
            "kill_summary": self._generate_kill_summary(),
        }

        report_path = output_dir / "player_kill_report.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        print(f"\n[OK] Report saved: {report_path}")
        return report_path

    def _generate_kill_summary(self) -> dict:
        """Generate kill/death summary for each player."""
        kills_by_player = defaultdict(int)
        deaths_by_player = defaultdict(int)

        for kill in self.player_kills:
            kills_by_player[kill.killer_id] += 1
            deaths_by_player[kill.victim_id] += 1

        summary = {}
        for player_id, player_name in self.player_entities.items():
            summary[player_name] = {
                "entity_id": player_id,
                "kills": kills_by_player[player_id],
                "deaths": deaths_by_player[player_id],
                "kd_ratio": (
                    kills_by_player[player_id] / deaths_by_player[player_id]
                    if deaths_by_player[player_id] > 0 else kills_by_player[player_id]
                ),
            }

        return summary

    def run_full_analysis(self):
        """Run complete kill detection pipeline."""
        print("\n" + "=" * 70)
        print("PLAYER KILL DETECTOR")
        print("=" * 70)
        print(f"Replay: {self.replay_name}\n")

        self.load_frames()
        self.extract_player_entities()
        self.scan_all_events()
        self.detect_player_kills()

        return self.generate_report()


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Detect player kills from VG replay events"
    )
    parser.add_argument(
        "replay_path",
        help="Path to replay folder or .vgr file"
    )
    parser.add_argument(
        "--output-dir", "-o",
        help="Output directory for report (default: replay directory)",
        default=None,
    )

    args = parser.parse_args()

    try:
        detector = PlayerKillDetector(args.replay_path)
        report_path = detector.run_full_analysis()

        print("\n" + "=" * 70)
        print("ANALYSIS COMPLETE")
        print("=" * 70)
        print(f"Report: {report_path}")

    except Exception as e:
        print(f"[ERROR] Detection failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
