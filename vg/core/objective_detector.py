"""
Objective Detector - Kraken and Gold Mine capture detection.

Detects objective capture events from Vainglory replay binary data.
Detection confidence: 75% for capturing team identification.

Usage:
    detector = ObjectiveDetector(valid_entity_ids={0x05DC, 0x05DD, ...})
    for frame_idx, frame_data in frames:
        detector.process_frame(frame_idx, frame_data)
    captures = detector.get_captures(team_map=team_map)

Research basis: vg/analysis/objective_event_research_report.md
"""
import struct
from collections import defaultdict
from dataclasses import dataclass
from typing import List, Dict, Set, Optional

DEATH_HEADER = bytes([0x08, 0x04, 0x31])
CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])


@dataclass
class ObjectiveCapture:
    """A detected objective capture event."""
    entity_id: int
    timestamp: float
    capturing_team: Optional[str]  # "left", "right", or None if inconclusive
    confidence: float  # 0.0 to 1.0
    objective_type: str = "unknown"  # "kraken", "gold_mine", or "unknown"
    frame_idx: int = 0
    file_offset: int = 0
    bounty_left: float = 0.0
    bounty_right: float = 0.0


@dataclass
class ObjectiveDeath:
    """Raw objective death event."""
    entity_id: int
    timestamp: float
    frame_idx: int
    file_offset: int


class ObjectiveDetector:
    """
    Detects objective capture events from replay frame data.

    Detection method:
    1. Scan death events [08 04 31] with entity ID > 65000
    2. Scan credit records [10 04 1D] within ±2000 bytes
    3. Sum action 0x06 (gold income) and 0x08 (passive gold) by team
    4. Team with >1.2x credits is capturing team (75% accuracy)

    Limitations:
    - Cannot reliably distinguish Kraken from Gold Mine
    - 75% accuracy based on 4 tournament matches
    - Some matches may have no objectives or contested captures
    """

    def __init__(self, valid_entity_ids: Set[int], objective_threshold: int = 65000):
        """
        Args:
            valid_entity_ids: Set of valid player entity IDs (Big Endian).
            objective_threshold: Minimum entity ID for objectives (default 65000).
        """
        self.valid_player_eids = valid_entity_ids
        self.objective_threshold = objective_threshold
        self._objective_deaths: List[ObjectiveDeath] = []

    def process_frame(self, frame_idx: int, data: bytes) -> None:
        """Process a single frame, extracting objective death events."""
        self._scan_objective_deaths(frame_idx, data)

    def _scan_objective_deaths(self, frame_idx: int, data: bytes) -> None:
        """Scan for objective death events (eid > threshold)."""
        pos = 0
        while True:
            pos = data.find(DEATH_HEADER, pos)
            if pos == -1:
                break
            if pos + 13 > len(data):
                pos += 1
                continue

            # Structural validation
            if data[pos+3:pos+5] != b'\x00\x00' or data[pos+7:pos+9] != b'\x00\x00':
                pos += 1
                continue

            eid = struct.unpack_from(">H", data, pos + 5)[0]
            ts = struct.unpack_from(">f", data, pos + 9)[0]

            # Filter for objective entities
            if eid > self.objective_threshold and 0 < ts < 2400:
                self._objective_deaths.append(ObjectiveDeath(
                    entity_id=eid,
                    timestamp=ts,
                    frame_idx=frame_idx,
                    file_offset=pos,
                ))

            pos += 1

    def get_captures(self,
                     team_map: Dict[int, str],
                     all_frame_data: bytes,
                     confidence_threshold: float = 0.0) -> List[ObjectiveCapture]:
        """
        Get detected objective captures with team identification.

        Args:
            team_map: Dict mapping player entity ID (BE) -> team name ("left"/"right").
            all_frame_data: Concatenated replay frame data for credit scanning.
            confidence_threshold: Minimum confidence (0.0-1.0). Default 0.0 returns all.

        Returns:
            List of ObjectiveCapture events.
        """
        captures = []

        for obj_death in self._objective_deaths:
            # Scan credits near this objective death
            credits_by_action = self._scan_credits_near(
                all_frame_data,
                obj_death.file_offset,
                scan_range=2000,
            )

            # Calculate team totals for action 0x06 and 0x08
            team_totals = {"left": 0.0, "right": 0.0}

            for action in [0x06, 0x08]:
                for credit in credits_by_action.get(action, []):
                    player_team = team_map.get(credit["eid"])
                    if player_team:
                        team_totals[player_team] += credit["value"]

            # Determine capturing team
            left_total = team_totals["left"]
            right_total = team_totals["right"]

            if left_total > right_total * 1.2:
                capturing_team = "left"
                confidence = 0.75
            elif right_total > left_total * 1.2:
                capturing_team = "right"
                confidence = 0.75
            else:
                capturing_team = None  # Inconclusive
                confidence = 0.0

            # Filter by confidence threshold
            if confidence >= confidence_threshold:
                captures.append(ObjectiveCapture(
                    entity_id=obj_death.entity_id,
                    timestamp=obj_death.timestamp,
                    capturing_team=capturing_team,
                    confidence=confidence,
                    objective_type="unknown",  # Cannot distinguish Kraken vs Gold Mine yet
                    frame_idx=obj_death.frame_idx,
                    file_offset=obj_death.file_offset,
                    bounty_left=left_total,
                    bounty_right=right_total,
                ))

        return captures

    def _scan_credits_near(self,
                          data: bytes,
                          death_offset: int,
                          scan_range: int = 2000) -> Dict[int, List[dict]]:
        """
        Scan credit records near objective death, grouped by action byte.

        Args:
            data: Full replay frame data.
            death_offset: Byte offset of objective death event.
            scan_range: Bytes to scan around death (default ±2000).

        Returns:
            Dict mapping action byte -> list of credit records.
        """
        credits_by_action = defaultdict(list)
        start = max(0, death_offset - scan_range // 2)
        end = min(death_offset + scan_range, len(data))

        pos = start
        while pos < end:
            if data[pos:pos+3] == CREDIT_HEADER and pos + 12 <= len(data):
                if data[pos+3:pos+5] == b'\x00\x00':
                    eid = struct.unpack_from(">H", data, pos + 5)[0]
                    value = struct.unpack_from(">f", data, pos + 7)[0]
                    action = data[pos + 11]

                    # Filter for valid player credits
                    if eid in self.valid_player_eids and not (value != value):  # not NaN
                        credits_by_action[action].append({
                            "eid": eid,
                            "value": round(value, 2),
                            "offset": pos,
                            "dt_bytes": pos - death_offset,
                        })
                pos += 3
            else:
                pos += 1

        return credits_by_action

    @property
    def objective_deaths(self) -> List[ObjectiveDeath]:
        """Raw objective death events (eid > threshold)."""
        return list(self._objective_deaths)

    def get_summary(self) -> dict:
        """Get detection summary statistics."""
        return {
            "objective_deaths_detected": len(self._objective_deaths),
            "entity_id_range": (
                min(d.entity_id for d in self._objective_deaths) if self._objective_deaths else 0,
                max(d.entity_id for d in self._objective_deaths) if self._objective_deaths else 0,
            ),
            "timestamp_range": (
                min(d.timestamp for d in self._objective_deaths) if self._objective_deaths else 0.0,
                max(d.timestamp for d in self._objective_deaths) if self._objective_deaths else 0.0,
            ),
        }
