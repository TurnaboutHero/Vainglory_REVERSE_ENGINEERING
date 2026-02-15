"""
KDA Detector - Kill/Death detection from Vainglory replay files.

Cross-validated accuracy (94 players across 10 complete replays):
  Kill: 97.9% (92/94) - raw detection, no filtering
  Death: 95.7% (90/94) - with post-game ceremony filter (ts <= duration + 10s)
  Combined: 96.8% (182/188)

Record structures (Big Endian protocol):
  Kill:  [18 04 1C] [00 00] [killer_eid BE] [FF FF FF FF] [3F 80 00 00] [29 00]
         Timestamp: f32 BE at 7 bytes before header
  Death: [08 04 31] [00 00] [victim_eid BE] [00 00] [timestamp f32 BE] [00 00 00]

Discovery method: Brute-force frequency matching across all (pattern, offset)
combinations, then structural validation and cross-replay verification.
"""
import struct
from collections import Counter
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Tuple

KILL_HEADER = bytes([0x18, 0x04, 0x1C])
DEATH_HEADER = bytes([0x08, 0x04, 0x31])
CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])


@dataclass
class KillEvent:
    """A detected kill event."""
    killer_eid: int
    timestamp: Optional[float] = None
    frame_idx: int = 0
    file_offset: int = 0


@dataclass
class DeathEvent:
    """A detected death event."""
    victim_eid: int
    timestamp: float = 0.0
    frame_idx: int = 0
    file_offset: int = 0


@dataclass
class KDAResult:
    """Per-player KDA counts."""
    kills: int = 0
    deaths: int = 0
    kill_events: List[KillEvent] = field(default_factory=list)
    death_events: List[DeathEvent] = field(default_factory=list)


class KDADetector:
    """
    Detects kills and deaths from VGR replay frame data.

    Usage:
        detector = KDADetector(valid_entity_ids={0x05DC, 0x05DD, ...})
        for frame_idx, frame_data in frames:
            detector.process_frame(frame_idx, frame_data)
        results = detector.get_results()  # dict of eid -> KDAResult
        # Or with post-game filter:
        results = detector.get_results(game_duration=1028)
    """

    def __init__(self, valid_entity_ids: Set[int]):
        """
        Args:
            valid_entity_ids: Set of valid player entity IDs (Big Endian).
        """
        self.valid_eids = valid_entity_ids
        self._kill_events: List[KillEvent] = []
        self._death_events: List[DeathEvent] = []

    def process_frame(self, frame_idx: int, data: bytes) -> None:
        """Process a single frame, extracting kill and death events."""
        self._scan_kills(frame_idx, data)
        self._scan_deaths(frame_idx, data)

    def _scan_kills(self, frame_idx: int, data: bytes) -> None:
        """Scan for kill records: [18 04 1C] [00 00] [eid BE] [FF FF FF FF] [3F 80 00 00] [29]"""
        pos = 0
        while True:
            pos = data.find(KILL_HEADER, pos)
            if pos == -1:
                break
            if pos + 16 > len(data):
                pos += 1
                continue

            # Structural validation
            if (data[pos+3:pos+5] != b'\x00\x00' or
                data[pos+7:pos+11] != b'\xFF\xFF\xFF\xFF' or
                data[pos+11:pos+15] != b'\x3F\x80\x00\x00' or
                data[pos+15] != 0x29):
                pos += 1
                continue

            eid = struct.unpack_from(">H", data, pos + 5)[0]
            if eid not in self.valid_eids:
                pos += 1
                continue

            # Extract timestamp from 7 bytes before header
            ts = None
            if pos >= 7:
                ts = struct.unpack_from(">f", data, pos - 7)[0]
                if not (0 < ts < 1800):
                    ts = None

            self._kill_events.append(KillEvent(
                killer_eid=eid,
                timestamp=ts,
                frame_idx=frame_idx,
                file_offset=pos,
            ))
            pos += 16  # Skip past this record

    def _scan_deaths(self, frame_idx: int, data: bytes) -> None:
        """Scan for death records: [08 04 31] [00 00] [eid BE] [00 00] [ts f32 BE]"""
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

            if eid not in self.valid_eids or not (0 < ts < 1800):
                pos += 1
                continue

            self._death_events.append(DeathEvent(
                victim_eid=eid,
                timestamp=ts,
                frame_idx=frame_idx,
                file_offset=pos,
            ))
            pos += 1

    def get_results(self, game_duration: Optional[float] = None,
                    death_buffer: float = 10.0) -> Dict[int, KDAResult]:
        """
        Get per-player KDA results.

        Args:
            game_duration: If provided, deaths with ts > duration + death_buffer
                          are filtered (post-game ceremony kills not counted in stats).
            death_buffer: Buffer seconds added to game_duration for death filtering.
                         Default 10s. Only used if game_duration is provided.

        Returns:
            Dict mapping entity ID (BE) to KDAResult.
        """
        results: Dict[int, KDAResult] = {}
        for eid in self.valid_eids:
            results[eid] = KDAResult()

        # Count kills (no timestamp filter - kill timestamps less reliable)
        for kev in self._kill_events:
            if kev.killer_eid in results:
                results[kev.killer_eid].kills += 1
                results[kev.killer_eid].kill_events.append(kev)

        # Count deaths (with optional post-game filter)
        max_death_ts = (game_duration + death_buffer) if game_duration else 9999
        for dev in self._death_events:
            if dev.victim_eid in results and dev.timestamp <= max_death_ts:
                results[dev.victim_eid].deaths += 1
                results[dev.victim_eid].death_events.append(dev)

        return results

    @property
    def kill_events(self) -> List[KillEvent]:
        return list(self._kill_events)

    @property
    def death_events(self) -> List[DeathEvent]:
        return list(self._death_events)

    def get_kill_death_pairs(self, team_map: Dict[int, str],
                             game_duration: Optional[float] = None,
                             death_buffer: float = 10.0,
                             max_dt: float = 5.0) -> List[dict]:
        """
        Match kills to deaths by timestamp (killer's team != victim's team).

        Args:
            team_map: Dict mapping entity ID (BE) -> team name ("left"/"right").
            game_duration: Optional game duration for death filtering.
            death_buffer: Buffer for death filtering.
            max_dt: Maximum time difference for kill-death matching.

        Returns:
            List of matched events with killer, victim, timestamp, etc.
        """
        max_death_ts = (game_duration + death_buffer) if game_duration else 9999

        # Filter deaths
        valid_deaths = [d for d in self._death_events if d.timestamp <= max_death_ts]
        valid_deaths.sort(key=lambda d: d.timestamp)

        # Sort kills by timestamp
        kills_with_ts = [k for k in self._kill_events if k.timestamp is not None]
        kills_with_ts.sort(key=lambda k: k.timestamp)

        # Greedy 1:1 matching
        used_deaths = set()
        pairs = []

        for kev in kills_with_ts:
            killer_team = team_map.get(kev.killer_eid)
            best_death = None
            best_dt = max_dt
            best_idx = -1

            for di, dev in enumerate(valid_deaths):
                if di in used_deaths:
                    continue
                victim_team = team_map.get(dev.victim_eid)
                if victim_team and victim_team != killer_team:
                    dt = abs(kev.timestamp - dev.timestamp)
                    if dt < best_dt:
                        best_dt = dt
                        best_death = dev
                        best_idx = di

            pairs.append({
                "killer_eid": kev.killer_eid,
                "victim_eid": best_death.victim_eid if best_death else None,
                "kill_ts": kev.timestamp,
                "death_ts": best_death.timestamp if best_death else None,
                "dt": best_dt if best_death else None,
                "frame": kev.frame_idx,
            })
            if best_idx >= 0:
                used_deaths.add(best_idx)

        return pairs
