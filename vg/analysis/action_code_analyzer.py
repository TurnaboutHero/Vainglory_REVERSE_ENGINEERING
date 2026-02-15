#!/usr/bin/env python3
"""
Action Code Analyzer - Deep analysis of VG replay action codes 0x42, 0x43, 0x44

Based on entity_network_report.md findings:
- Action code 0x42: dominant in frames 3-12
- Action code 0x43: dominant in frames 12-51
- Action code 0x44: dominant in frames 51+

This script analyzes:
1. Action code distribution and frame-based patterns
2. Payload structure differences between 0x42, 0x43, 0x44
3. Player entity events (entity IDs 56325-58629 range)
4. Kill/death pattern detection from 6,008 kill candidates

Event structure: [EntityID(2B LE)][00 00][ActionCode(1B)][Payload...]
"""

import os
import sys
import struct
from pathlib import Path
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Set
import json

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "core"))

try:
    from vgr_parser import VGRParser
except ImportError:
    VGRParser = None


@dataclass
class ActionCodeStats:
    """Statistics for a single action code."""
    action_code: int
    total_count: int = 0
    frame_distribution: Dict[int, int] = field(default_factory=dict)
    entity_distribution: Dict[int, int] = field(default_factory=dict)
    payload_samples: List[bytes] = field(default_factory=list)
    first_frame: int = 999999
    last_frame: int = 0
    unique_entities: Set[int] = field(default_factory=set)

    def add_event(self, frame: int, entity_id: int, payload: bytes):
        """Record an event occurrence."""
        self.total_count += 1
        self.frame_distribution[frame] = self.frame_distribution.get(frame, 0) + 1
        self.entity_distribution[entity_id] = self.entity_distribution.get(entity_id, 0) + 1
        self.unique_entities.add(entity_id)
        self.first_frame = min(self.first_frame, frame)
        self.last_frame = max(self.last_frame, frame)

        # Collect payload samples (max 50 to avoid memory issues)
        if len(self.payload_samples) < 50:
            self.payload_samples.append(payload)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "action_code": f"0x{self.action_code:02X}",
            "total_count": self.total_count,
            "first_frame": self.first_frame,
            "last_frame": self.last_frame,
            "unique_entities": len(self.unique_entities),
            "frame_range": f"{self.first_frame}-{self.last_frame}",
            "top_frames": sorted(
                self.frame_distribution.items(),
                key=lambda x: -x[1]
            )[:10],
            "top_entities": sorted(
                self.entity_distribution.items(),
                key=lambda x: -x[1]
            )[:10],
        }


@dataclass
class PayloadStructure:
    """Analyzed structure of payload for an action code."""
    action_code: int
    min_length: int = 999999
    max_length: int = 0
    avg_length: float = 0.0
    common_lengths: List[Tuple[int, int]] = field(default_factory=list)
    byte_patterns: Dict[int, Counter] = field(default_factory=dict)  # offset -> byte value counts
    entity_id_offsets: List[int] = field(default_factory=list)  # Offsets where entity IDs appear

    def analyze_payloads(self, payloads: List[bytes]):
        """Analyze payload structure from samples."""
        if not payloads:
            return

        lengths = [len(p) for p in payloads]
        self.min_length = min(lengths)
        self.max_length = max(lengths)
        self.avg_length = sum(lengths) / len(lengths)

        # Find common lengths
        length_counts = Counter(lengths)
        self.common_lengths = length_counts.most_common(5)

        # Analyze byte patterns at each offset (up to first 32 bytes)
        max_offset = min(32, min(len(p) for p in payloads) if payloads else 0)
        for offset in range(max_offset):
            self.byte_patterns[offset] = Counter()
            for payload in payloads:
                if offset < len(payload):
                    self.byte_patterns[offset][payload[offset]] += 1

        # Detect potential entity ID fields (uint16 LE in typical entity range)
        self.entity_id_offsets = self._find_entity_id_offsets(payloads)

    def _find_entity_id_offsets(self, payloads: List[bytes]) -> List[int]:
        """Find byte offsets that likely contain entity IDs."""
        candidates = []
        max_offset = min(30, min(len(p) for p in payloads) if payloads else 0)

        for offset in range(0, max_offset - 1, 2):  # Check 2-byte aligned positions
            entity_like_count = 0
            for payload in payloads:
                if offset + 2 <= len(payload):
                    value = struct.unpack('<H', payload[offset:offset+2])[0]
                    # Entity IDs are typically < 65535 and > 0
                    # Player entities are in 56325-58629 range
                    # Other entities seen: 0-65535
                    if 0 < value < 65535:
                        entity_like_count += 1

            # If >50% of samples have entity-like values at this offset
            if entity_like_count > len(payloads) * 0.5:
                candidates.append(offset)

        return candidates

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "action_code": f"0x{self.action_code:02X}",
            "payload_length": {
                "min": self.min_length,
                "max": self.max_length,
                "avg": round(self.avg_length, 2),
                "common_lengths": self.common_lengths,
            },
            "entity_id_offsets": self.entity_id_offsets,
            "byte_pattern_summary": self._summarize_byte_patterns(),
        }

    def _summarize_byte_patterns(self) -> Dict[int, dict]:
        """Summarize byte patterns at each offset."""
        summary = {}
        for offset, counter in sorted(self.byte_patterns.items())[:16]:  # First 16 bytes
            top_values = counter.most_common(3)
            summary[offset] = {
                "top_values": [(f"0x{val:02X}", count) for val, count in top_values],
                "entropy": self._calculate_entropy(counter),
            }
        return summary

    def _calculate_entropy(self, counter: Counter) -> str:
        """Calculate Shannon entropy of byte distribution."""
        if not counter:
            return "0.00"
        total = sum(counter.values())
        import math
        entropy = -sum((count/total) * math.log2(count/total) for count in counter.values())
        return f"{entropy:.2f}"


@dataclass
class PlayerKillCandidate:
    """Potential player kill event."""
    killer_id: int
    victim_id: int
    killer_name: Optional[str] = None
    victim_name: Optional[str] = None
    frame: int = 0
    action_code: int = 0
    confidence: float = 0.0
    evidence: List[str] = field(default_factory=list)


class ActionCodeAnalyzer:
    """Analyzer for VG replay action codes."""

    # Frame ranges for action code dominance (from entity_network_report.md)
    FRAME_RANGES = {
        0x42: (3, 12),
        0x43: (12, 51),
        0x44: (51, 9999),
    }

    # Player entity ID range (from entity_network_report.md)
    PLAYER_ENTITY_MIN = 56325
    PLAYER_ENTITY_MAX = 58629

    def __init__(self, replay_path: str):
        """Initialize analyzer with replay path."""
        self.replay_path = Path(replay_path)
        self.frame_dir, self.replay_name = self._find_replay_files()
        self.frames = []
        self.player_entities = {}

        # Statistics
        self.action_stats: Dict[int, ActionCodeStats] = {}
        self.payload_structures: Dict[int, PayloadStructure] = {}
        self.player_kill_candidates: List[PlayerKillCandidate] = []

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
        print(f"[INFO] Loaded {len(self.frames)} frames")

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

            # Extract player name
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

        print(f"[INFO] Found {len(self.player_entities)} player entities:")
        for eid, name in sorted(self.player_entities.items()):
            print(f"       {eid} -> {name}")

    def scan_action_codes(self, target_codes: List[int] = [0x42, 0x43, 0x44]):
        """Scan all frames for action code events."""
        print(f"\n[INFO] Scanning action codes: {[f'0x{c:02X}' for c in target_codes]}")

        for action_code in target_codes:
            self.action_stats[action_code] = ActionCodeStats(action_code)
            self.payload_structures[action_code] = PayloadStructure(action_code)

        for frame_idx, data in self.frames:
            self._scan_frame_for_actions(frame_idx, data, target_codes)

        # Analyze payload structures
        for action_code in target_codes:
            stats = self.action_stats[action_code]
            structure = self.payload_structures[action_code]
            structure.analyze_payloads(stats.payload_samples)

            print(f"\n[STAT:action_0x{action_code:02X}_count] {stats.total_count}")
            print(f"[STAT:action_0x{action_code:02X}_frame_range] {stats.first_frame}-{stats.last_frame}")
            print(f"[STAT:action_0x{action_code:02X}_entities] {len(stats.unique_entities)}")

    def _scan_frame_for_actions(self, frame_idx: int, data: bytes, target_codes: List[int]):
        """Scan a single frame for action code events."""
        length = len(data)
        if length < 5:
            return

        idx = 0
        while idx <= length - 5:
            # Look for event pattern: [XX XX][00 00][ActionCode]
            if data[idx + 2] == 0x00 and data[idx + 3] == 0x00:
                entity_id = struct.unpack('<H', data[idx:idx+2])[0]
                action_code = data[idx + 4]

                if action_code in target_codes:
                    # Extract payload (next 32 bytes or until end)
                    payload_start = idx + 5
                    payload_end = min(payload_start + 32, length)
                    payload = data[payload_start:payload_end]

                    stats = self.action_stats[action_code]
                    stats.add_event(frame_idx, entity_id, payload)

                idx += 5
            else:
                idx += 1

    def analyze_frame_distribution(self):
        """Analyze how action codes distribute across frame ranges."""
        print("\n[FINDING] Frame distribution analysis:")
        print("\nAction code distribution by frame range:")
        print("=" * 70)

        for action_code in [0x42, 0x43, 0x44]:
            if action_code not in self.action_stats:
                continue

            stats = self.action_stats[action_code]
            expected_range = self.FRAME_RANGES.get(action_code, (0, 9999))

            # Count events in expected range vs outside
            in_range = 0
            out_range = 0

            for frame, count in stats.frame_distribution.items():
                if expected_range[0] <= frame <= expected_range[1]:
                    in_range += count
                else:
                    out_range += count

            total = in_range + out_range
            in_pct = (in_range / total * 100) if total > 0 else 0

            print(f"\n0x{action_code:02X}: {total:,} events")
            print(f"  Expected range: frames {expected_range[0]}-{expected_range[1]}")
            print(f"  In range: {in_range:,} ({in_pct:.1f}%)")
            print(f"  Out of range: {out_range:,} ({100-in_pct:.1f}%)")

            # Show top frames
            top_frames = sorted(stats.frame_distribution.items(), key=lambda x: -x[1])[:5]
            print(f"  Top frames: {top_frames}")

    def compare_payload_structures(self):
        """Compare payload structures between action codes."""
        print("\n[FINDING] Payload structure comparison:")
        print("=" * 70)

        for action_code in [0x42, 0x43, 0x44]:
            if action_code not in self.payload_structures:
                continue

            structure = self.payload_structures[action_code]
            print(f"\n0x{action_code:02X} Payload Structure:")
            print(f"  Length: min={structure.min_length}, max={structure.max_length}, avg={structure.avg_length:.1f}")
            print(f"  Common lengths: {structure.common_lengths}")
            print(f"  Potential entity ID offsets: {structure.entity_id_offsets}")

            # Show byte patterns for potential entity ID fields
            if structure.entity_id_offsets:
                print(f"  Entity ID field analysis:")
                for offset in structure.entity_id_offsets[:3]:  # Show first 3
                    print(f"    Offset {offset}: {structure.byte_patterns.get(offset, Counter()).most_common(3)}")

    def detect_player_kills(self):
        """Detect potential player kill events from action code patterns."""
        print("\n[FINDING] Player kill detection:")
        print("=" * 70)

        # Strategy: Look for action code 0x44 events involving player entities
        # where the target player entity stops appearing soon after

        player_interactions = defaultdict(list)  # (killer_id, victim_id) -> [(frame, action)]
        player_last_seen = {}  # player_id -> last_frame

        # Track all player entity activity
        for action_code in [0x42, 0x43, 0x44]:
            if action_code not in self.action_stats:
                continue

            stats = self.action_stats[action_code]
            structure = self.payload_structures[action_code]

            # For each event involving a player entity
            for entity_id in stats.unique_entities:
                if self._is_player_entity(entity_id):
                    # Update last seen frame
                    for frame in stats.frame_distribution.keys():
                        if entity_id in [eid for eid, _ in stats.entity_distribution.items()]:
                            player_last_seen[entity_id] = max(
                                player_last_seen.get(entity_id, 0),
                                frame
                            )

                    # Check if this entity attacks other player entities
                    # Look in payload for other player entity IDs
                    if structure.entity_id_offsets:
                        for payload in stats.payload_samples[:100]:
                            for offset in structure.entity_id_offsets:
                                if offset + 2 <= len(payload):
                                    target_id = struct.unpack('<H', payload[offset:offset+2])[0]
                                    if self._is_player_entity(target_id) and target_id != entity_id:
                                        # Record interaction
                                        # (simplified - would need frame tracking)
                                        player_interactions[(entity_id, target_id)].append(
                                            (stats.last_frame, action_code)
                                        )

        print(f"[STAT:player_interactions] {len(player_interactions)}")
        print(f"[STAT:player_entities_tracked] {len(player_last_seen)}")

        # Identify kill candidates
        kill_candidates = []

        for (killer_id, victim_id), interactions in player_interactions.items():
            if not interactions:
                continue

            # Find last interaction frame
            last_interaction_frame = max(frame for frame, _ in interactions)
            victim_last_frame = player_last_seen.get(victim_id, 0)

            # If victim disappeared shortly after interaction (within 5 frames)
            if 0 <= victim_last_frame - last_interaction_frame <= 5:
                confidence = 0.7  # Base confidence
                evidence = []

                # Boost confidence if interaction was with 0x44 (late game action)
                if any(action == 0x44 for _, action in interactions):
                    confidence += 0.1
                    evidence.append("0x44_interaction")

                # Boost if multiple interactions
                if len(interactions) > 3:
                    confidence += 0.1
                    evidence.append(f"multiple_hits_{len(interactions)}")

                # Boost if victim disappeared much earlier than killer
                killer_last_frame = player_last_seen.get(killer_id, 0)
                if killer_last_frame > victim_last_frame + 3:
                    confidence += 0.1
                    evidence.append("victim_disappeared_early")

                candidate = PlayerKillCandidate(
                    killer_id=killer_id,
                    victim_id=victim_id,
                    killer_name=self.player_entities.get(killer_id),
                    victim_name=self.player_entities.get(victim_id),
                    frame=last_interaction_frame,
                    action_code=0x44,  # Simplified
                    confidence=min(confidence, 1.0),
                    evidence=evidence,
                )
                kill_candidates.append(candidate)

        # Sort by confidence
        kill_candidates.sort(key=lambda k: -k.confidence)
        self.player_kill_candidates = kill_candidates

        print(f"\n[STAT:kill_candidates_detected] {len(kill_candidates)}")

        if kill_candidates:
            print("\nTop kill candidates:")
            for i, kc in enumerate(kill_candidates[:10], 1):
                print(f"{i}. {kc.killer_name} -> {kc.victim_name} "
                      f"(frame {kc.frame}, confidence {kc.confidence:.2f})")
                print(f"   Evidence: {', '.join(kc.evidence)}")

    def _is_player_entity(self, entity_id: int) -> bool:
        """Check if entity ID is in player range."""
        return self.PLAYER_ENTITY_MIN <= entity_id <= self.PLAYER_ENTITY_MAX

    def generate_report(self, output_dir: Optional[Path] = None) -> Path:
        """Generate analysis report."""
        if output_dir is None:
            output_dir = self.frame_dir
        else:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

        # JSON output
        report_data = {
            "replay_name": self.replay_name,
            "total_frames": len(self.frames),
            "player_entities": {
                str(eid): name for eid, name in self.player_entities.items()
            },
            "action_code_stats": {
                f"0x{code:02X}": stats.to_dict()
                for code, stats in self.action_stats.items()
            },
            "payload_structures": {
                f"0x{code:02X}": structure.to_dict()
                for code, structure in self.payload_structures.items()
            },
            "player_kill_candidates": [
                {
                    "killer_id": kc.killer_id,
                    "killer_name": kc.killer_name,
                    "victim_id": kc.victim_id,
                    "victim_name": kc.victim_name,
                    "frame": kc.frame,
                    "action_code": f"0x{kc.action_code:02X}",
                    "confidence": round(kc.confidence, 2),
                    "evidence": kc.evidence,
                }
                for kc in self.player_kill_candidates
            ],
        }

        report_path = output_dir / "action_code_analysis.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        print(f"\n[OK] Report saved: {report_path}")
        return report_path

    def run_full_analysis(self):
        """Run complete analysis pipeline."""
        print("\n" + "=" * 70)
        print("ACTION CODE ANALYZER")
        print("=" * 70)
        print(f"Replay: {self.replay_name}")

        self.load_frames()
        self.extract_player_entities()
        self.scan_action_codes([0x42, 0x43, 0x44])
        self.analyze_frame_distribution()
        self.compare_payload_structures()
        self.detect_player_kills()

        return self.generate_report()


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Analyze VG replay action codes 0x42, 0x43, 0x44"
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
        analyzer = ActionCodeAnalyzer(args.replay_path)
        report_path = analyzer.run_full_analysis()

        print("\n" + "=" * 70)
        print("ANALYSIS COMPLETE")
        print("=" * 70)
        print(f"Report: {report_path}")

    except Exception as e:
        print(f"[ERROR] Analysis failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
