#!/usr/bin/env python3
"""
Deep Event Mapper - Comprehensive VGR Event Code Analysis

Maps all 256 possible event codes with their payload structures by analyzing
Vainglory replay binary files. Performs entity classification, event sequence
analysis, cross-frame temporal analysis, and generates detailed reports.

Event structure: [EntityID(2B LE)][00 00][ActionCode(1B)][Payload...]
Player blocks start with DA 03 EE marker.
Entity IDs at offset +0xA5, team IDs at offset +0xD5 from player block.
"""

import argparse
import json
import math
import struct
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import (
    Any,
    Dict,
    FrozenSet,
    List,
    Optional,
    Set,
    Tuple,
)

# ---------------------------------------------------------------------------
# Imports from project core
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent.parent / "core"))

try:
    from vgr_parser import VGRParser
except ImportError:
    from vg.core.vgr_parser import VGRParser

try:
    from vgr_mapping import HERO_ID_MAP, ITEM_ID_MAP, ASSET_HERO_ID_INT_MAP
except ImportError:
    try:
        from vg.core.vgr_mapping import HERO_ID_MAP, ITEM_ID_MAP, ASSET_HERO_ID_INT_MAP
    except ImportError:
        HERO_ID_MAP = {}
        ITEM_ID_MAP = {}
        ASSET_HERO_ID_INT_MAP = {}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class EventRecord:
    """A single event extracted from replay binary data."""
    frame: int
    offset: int
    entity_id: int
    action: int
    payload: bytes
    payload_len: int = 0

    def __post_init__(self) -> None:
        self.payload_len = len(self.payload)

    @property
    def action_hex(self) -> str:
        return f"0x{self.action:02X}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frame": self.frame,
            "offset": self.offset,
            "entity_id": self.entity_id,
            "action": self.action,
            "action_hex": self.action_hex,
            "payload_hex": self.payload.hex(),
            "payload_len": self.payload_len,
        }


@dataclass
class PayloadFieldInfo:
    """Statistical description of a single byte offset within a payload."""
    offset: int
    min_val: int = 255
    max_val: int = 0
    mean_val: float = 0.0
    mode_val: int = 0
    unique_count: int = 0
    is_fixed: bool = False
    fixed_value: Optional[int] = None
    is_potential_float_part: bool = False
    is_potential_entity_ref: bool = False
    is_potential_counter: bool = False
    value_distribution: Dict[int, int] = field(default_factory=dict)


@dataclass
class ActionCodeProfile:
    """Complete profile for a single action code."""
    action: int
    action_hex: str
    total_occurrences: int = 0
    distinct_entities: int = 0
    player_entity_count: int = 0
    non_player_entity_count: int = 0
    payload_lengths: Dict[int, int] = field(default_factory=dict)
    dominant_payload_length: int = 0
    fields: List[Dict[str, Any]] = field(default_factory=list)
    frame_distribution: Dict[int, int] = field(default_factory=dict)
    first_seen_frame: int = -1
    last_seen_frame: int = -1
    entity_id_refs_in_payload: int = 0
    potential_float_fields: List[int] = field(default_factory=list)
    potential_counter_fields: List[int] = field(default_factory=list)
    confidence: float = 0.0
    hypothesis: str = ""
    sample_payloads: List[str] = field(default_factory=list)


@dataclass
class EntityProfile:
    """Profile for a tracked entity."""
    entity_id: int
    is_player: bool = False
    player_name: Optional[str] = None
    team: Optional[str] = None
    team_id: Optional[int] = None
    first_seen_frame: int = -1
    last_seen_frame: int = -1
    total_events: int = 0
    action_distribution: Dict[int, int] = field(default_factory=dict)
    interacts_with: Set[int] = field(default_factory=set)
    behavior_cluster: str = "unknown"

    def lifespan_frames(self) -> int:
        if self.first_seen_frame < 0 or self.last_seen_frame < 0:
            return 0
        return self.last_seen_frame - self.first_seen_frame + 1


@dataclass
class TransitionEdge:
    """A directed edge in the event state-machine graph."""
    from_action: int
    to_action: int
    count: int = 0
    probability: float = 0.0


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PAYLOAD_CAPTURE_LEN = 32  # bytes to capture after action code
MAX_SAMPLE_PAYLOADS = 5
FLOAT_RANGE_MIN = -5000.0
FLOAT_RANGE_MAX = 5000.0
KNOWN_EVENTS: Dict[int, str] = {
    0xBC: "item_purchase",
    0x3E: "skill_levelup",
    0x08: "movement_related",
    0x44: "common_action_44",
    0x43: "common_action_43",
    0x0E: "ranged_attack",
    0x65: "common_action_65",
    0x13: "mobility_related",
    0x76: "common_action_76",
}


# ---------------------------------------------------------------------------
# Frame I/O helpers
# ---------------------------------------------------------------------------
def find_replay_info(replay_path: Path) -> Tuple[Path, str]:
    """Return (frame_directory, replay_base_name) from a replay path."""
    if replay_path.is_file() and str(replay_path).endswith(".0.vgr"):
        frame_dir = replay_path.parent
        replay_name = replay_path.stem.rsplit(".", 1)[0]
        return frame_dir, replay_name

    if replay_path.is_dir():
        for f in replay_path.rglob("*.0.vgr"):
            frame_dir = f.parent
            replay_name = f.stem.rsplit(".", 1)[0]
            return frame_dir, replay_name

    raise FileNotFoundError(f"No .0.vgr file found in {replay_path}")


def iter_frames(frame_dir: Path, replay_name: str):
    """Yield (frame_number, frame_bytes) in frame order."""
    frame_files = list(frame_dir.glob(f"{replay_name}.*.vgr"))

    def _key(p: Path) -> int:
        try:
            return int(p.stem.split(".")[-1])
        except ValueError:
            return 0

    frame_files.sort(key=_key)
    for fp in frame_files:
        frame_num = _key(fp)
        yield frame_num, fp.read_bytes()


def read_all_frames(frame_dir: Path, replay_name: str) -> bytes:
    """Concatenate all frame data in order."""
    return b"".join(data for _, data in iter_frames(frame_dir, replay_name))


# ---------------------------------------------------------------------------
# Player / entity extraction helpers
# ---------------------------------------------------------------------------
def extract_player_entities(first_frame_path: Path) -> List[Dict[str, Any]]:
    """Parse the first frame to extract player entity information."""
    parser = VGRParser(str(first_frame_path), auto_truth=False)
    parsed = parser.parse()

    players: List[Dict[str, Any]] = []
    for team_label in ("left", "right"):
        for p in parsed["teams"].get(team_label, []):
            eid = p.get("entity_id")
            if eid is not None:
                players.append({
                    "entity_id": eid,
                    "name": p.get("name", ""),
                    "team": team_label,
                    "team_id": p.get("team_id"),
                })
    return players


# ---------------------------------------------------------------------------
# Core event extraction
# ---------------------------------------------------------------------------
def extract_events_from_data(
    data: bytes,
    frame_num: int,
    entity_ids: Optional[Set[int]] = None,
    scan_all: bool = False,
) -> List[EventRecord]:
    """
    Extract events from binary data.

    If entity_ids is given, only extract events for those entities.
    If scan_all is True, scan for ALL possible 2-byte entity patterns
    followed by 00 00 and a 1-byte action.
    """
    events: List[EventRecord] = []

    if scan_all:
        # Scan every position for the [XX XX][00 00][action] pattern
        idx = 0
        data_len = len(data)
        while idx + 5 <= data_len:
            # Check for the 00 00 separator at idx+2
            if data[idx + 2] == 0x00 and data[idx + 3] == 0x00:
                entity_id = int.from_bytes(data[idx:idx + 2], "little")
                # Filter out entity_id == 0 as noise
                if entity_id != 0:
                    action = data[idx + 4]
                    payload_end = min(idx + 5 + PAYLOAD_CAPTURE_LEN, data_len)
                    payload = data[idx + 5:payload_end]
                    events.append(EventRecord(
                        frame=frame_num,
                        offset=idx,
                        entity_id=entity_id,
                        action=action,
                        payload=payload,
                    ))
            idx += 1
    else:
        targets = entity_ids if entity_ids else set()
        for entity_id in targets:
            base = entity_id.to_bytes(2, "little") + b"\x00\x00"
            idx = 0
            while True:
                idx = data.find(base, idx)
                if idx == -1:
                    break
                if idx + 5 <= len(data):
                    action = data[idx + 4]
                    payload_end = min(idx + 5 + PAYLOAD_CAPTURE_LEN, len(data))
                    payload = data[idx + 5:payload_end]
                    events.append(EventRecord(
                        frame=frame_num,
                        offset=idx,
                        entity_id=entity_id,
                        action=action,
                        payload=payload,
                    ))
                idx += 1

    return events


def discover_entity_ids(data: bytes, min_occurrences: int = 5) -> Set[int]:
    """
    Scan data for recurring [XX XX][00 00] patterns to discover entity IDs.
    Returns entity IDs that appear at least min_occurrences times.
    """
    candidates: Counter = Counter()
    idx = 0
    data_len = len(data)
    while idx + 4 <= data_len:
        if data[idx + 2] == 0x00 and data[idx + 3] == 0x00:
            entity_id = int.from_bytes(data[idx:idx + 2], "little")
            if entity_id != 0:
                candidates[entity_id] += 1
        idx += 1
    return {eid for eid, cnt in candidates.items() if cnt >= min_occurrences}


# ---------------------------------------------------------------------------
# 1. Event Payload Structure Analysis
# ---------------------------------------------------------------------------
def analyze_payload_structure(
    events_by_action: Dict[int, List[EventRecord]],
    player_entity_ids: Set[int],
    all_entity_ids: Set[int],
) -> Dict[int, ActionCodeProfile]:
    """
    For each action code, analyze payload bytes to determine:
    - Common payload lengths
    - Fixed vs variable bytes
    - Potential IEEE 754 floats (coordinates)
    - Entity ID references in payloads
    - Potential timestamps / frame counters
    """
    profiles: Dict[int, ActionCodeProfile] = {}

    for action, events in events_by_action.items():
        profile = ActionCodeProfile(
            action=action,
            action_hex=f"0x{action:02X}",
            total_occurrences=len(events),
        )

        entity_set: Set[int] = set()
        payload_len_counter: Counter = Counter()
        frame_counter: Counter = Counter()

        # Collect payloads and metadata
        payloads: List[bytes] = []
        for ev in events:
            entity_set.add(ev.entity_id)
            payload_len_counter[ev.payload_len] += 1
            frame_counter[ev.frame] += 1
            payloads.append(ev.payload)

        profile.distinct_entities = len(entity_set)
        profile.player_entity_count = len(entity_set & player_entity_ids)
        profile.non_player_entity_count = len(entity_set - player_entity_ids)
        profile.payload_lengths = dict(payload_len_counter)
        profile.frame_distribution = dict(frame_counter)

        frames_seen = [ev.frame for ev in events]
        if frames_seen:
            profile.first_seen_frame = min(frames_seen)
            profile.last_seen_frame = max(frames_seen)

        # Dominant payload length
        if payload_len_counter:
            profile.dominant_payload_length = payload_len_counter.most_common(1)[0][0]

        # Sample payloads
        for ev in events[:MAX_SAMPLE_PAYLOADS]:
            profile.sample_payloads.append(ev.payload.hex())

        # Analyze each byte position in the dominant-length payloads
        dom_len = profile.dominant_payload_length
        if dom_len > 0 and payloads:
            dom_payloads = [p for p in payloads if len(p) >= dom_len]
            if dom_payloads:
                field_infos = _analyze_payload_fields(
                    dom_payloads, dom_len, player_entity_ids, all_entity_ids,
                )
                profile.fields = [_field_info_to_dict(fi) for fi in field_infos]

                # Aggregate field-level flags
                profile.potential_float_fields = [
                    fi.offset for fi in field_infos if fi.is_potential_float_part
                ]
                profile.potential_counter_fields = [
                    fi.offset for fi in field_infos if fi.is_potential_counter
                ]
                profile.entity_id_refs_in_payload = sum(
                    1 for fi in field_infos if fi.is_potential_entity_ref
                )

        # Assign known hypothesis
        if action in KNOWN_EVENTS:
            profile.hypothesis = KNOWN_EVENTS[action]

        # Confidence score: higher for more occurrences and more player entities
        profile.confidence = _compute_action_confidence(profile)

        profiles[action] = profile

    return profiles


def _analyze_payload_fields(
    payloads: List[bytes],
    length: int,
    player_eids: Set[int],
    all_eids: Set[int],
) -> List[PayloadFieldInfo]:
    """Analyze each byte offset in a collection of same-length payloads."""
    fields: List[PayloadFieldInfo] = []
    n = len(payloads)

    for off in range(length):
        fi = PayloadFieldInfo(offset=off)
        vals = [p[off] for p in payloads if len(p) > off]

        if not vals:
            fields.append(fi)
            continue

        counter = Counter(vals)
        fi.min_val = min(vals)
        fi.max_val = max(vals)
        fi.mean_val = round(sum(vals) / len(vals), 2)
        fi.mode_val = counter.most_common(1)[0][0]
        fi.unique_count = len(counter)
        fi.value_distribution = dict(counter.most_common(10))

        # Fixed byte detection
        if fi.unique_count == 1:
            fi.is_fixed = True
            fi.fixed_value = fi.mode_val

        # Potential entity ID reference: check pairs (off, off+1) as uint16 LE
        if off + 1 < length:
            entity_ref_hits = 0
            for p in payloads:
                if len(p) > off + 1:
                    ref_id = p[off] | (p[off + 1] << 8)
                    if ref_id in all_eids and ref_id != 0:
                        entity_ref_hits += 1
            if entity_ref_hits > n * 0.05 and entity_ref_hits >= 2:
                fi.is_potential_entity_ref = True

        # Potential float component: check groups of 4 bytes as IEEE 754
        if off + 3 < length and off % 4 == 0:
            float_hits = 0
            for p in payloads:
                if len(p) > off + 3:
                    try:
                        val = struct.unpack_from("<f", p, off)[0]
                        if (
                            math.isfinite(val)
                            and FLOAT_RANGE_MIN <= val <= FLOAT_RANGE_MAX
                            and val != 0.0
                        ):
                            float_hits += 1
                    except struct.error:
                        pass
            if float_hits > n * 0.5:
                fi.is_potential_float_part = True

        # Potential counter: monotonically non-decreasing across events
        if n >= 5:
            sorted_vals_by_frame = [
                p[off] for p in payloads if len(p) > off
            ]
            # Check if values trend upward (allowing some noise)
            increases = sum(
                1 for i in range(1, len(sorted_vals_by_frame))
                if sorted_vals_by_frame[i] >= sorted_vals_by_frame[i - 1]
            )
            if increases > len(sorted_vals_by_frame) * 0.8 and fi.unique_count > 3:
                fi.is_potential_counter = True

        fields.append(fi)

    return fields


def _field_info_to_dict(fi: PayloadFieldInfo) -> Dict[str, Any]:
    """Convert PayloadFieldInfo to a serialisable dict."""
    d: Dict[str, Any] = {
        "offset": fi.offset,
        "min": fi.min_val,
        "max": fi.max_val,
        "mean": fi.mean_val,
        "mode": fi.mode_val,
        "unique_values": fi.unique_count,
        "is_fixed": fi.is_fixed,
    }
    if fi.is_fixed:
        d["fixed_value"] = fi.fixed_value
    if fi.is_potential_float_part:
        d["potential_float"] = True
    if fi.is_potential_entity_ref:
        d["potential_entity_ref"] = True
    if fi.is_potential_counter:
        d["potential_counter"] = True
    # Top value distribution (capped for readability)
    d["top_values"] = {str(k): v for k, v in list(fi.value_distribution.items())[:8]}
    return d


def _compute_action_confidence(profile: ActionCodeProfile) -> float:
    """Heuristic confidence score for an action code profile (0..1)."""
    score = 0.0
    if profile.total_occurrences >= 100:
        score += 0.2
    elif profile.total_occurrences >= 10:
        score += 0.1
    if profile.player_entity_count > 0:
        score += 0.2
    if profile.dominant_payload_length > 0:
        # Consistent payload length is a good sign
        dom_count = profile.payload_lengths.get(profile.dominant_payload_length, 0)
        consistency = dom_count / max(profile.total_occurrences, 1)
        score += 0.3 * consistency
    if profile.entity_id_refs_in_payload > 0:
        score += 0.15
    if profile.potential_float_fields:
        score += 0.15
    return round(min(score, 1.0), 3)


# ---------------------------------------------------------------------------
# 2. Entity Classification
# ---------------------------------------------------------------------------
def classify_entities(
    all_events: List[EventRecord],
    player_entity_ids: Set[int],
    total_frames: int,
) -> Dict[int, EntityProfile]:
    """
    Classify entities:
    - Player vs non-player
    - Group non-players by behaviour (action distribution similarity)
    - Track lifecycle (first/last frame)
    - Map interactions
    """
    profiles: Dict[int, EntityProfile] = {}
    player_lookup = player_entity_ids

    for ev in all_events:
        eid = ev.entity_id
        if eid not in profiles:
            profiles[eid] = EntityProfile(
                entity_id=eid,
                is_player=(eid in player_lookup),
            )
        ep = profiles[eid]
        ep.total_events += 1
        ep.action_distribution[ev.action] = ep.action_distribution.get(ev.action, 0) + 1

        if ep.first_seen_frame < 0 or ev.frame < ep.first_seen_frame:
            ep.first_seen_frame = ev.frame
        if ev.frame > ep.last_seen_frame:
            ep.last_seen_frame = ev.frame

        # Look for entity references in payload
        _find_entity_refs_in_payload(ev.payload, profiles.keys(), eid, ep)

    # Cluster non-player entities by action distribution similarity
    _cluster_non_player_entities(profiles, player_entity_ids, total_frames)

    return profiles


def _find_entity_refs_in_payload(
    payload: bytes,
    known_eids,
    source_eid: int,
    entity_profile: EntityProfile,
) -> None:
    """Check payload for references to other known entity IDs."""
    if len(payload) < 2:
        return
    for off in range(0, len(payload) - 1):
        ref = int.from_bytes(payload[off:off + 2], "little")
        if ref != 0 and ref != source_eid and ref in known_eids:
            entity_profile.interacts_with.add(ref)


def _cluster_non_player_entities(
    profiles: Dict[int, EntityProfile],
    player_eids: Set[int],
    total_frames: int,
) -> None:
    """
    Assign behaviour cluster labels to non-player entities based on:
    - Lifespan (short-lived = minion, long-lived = turret/objective)
    - Action diversity
    - Event density
    """
    for eid, ep in profiles.items():
        if ep.is_player:
            ep.behavior_cluster = "player"
            continue

        lifespan = ep.lifespan_frames()
        action_diversity = len(ep.action_distribution)
        density = ep.total_events / max(lifespan, 1)

        # Heuristic clustering
        if lifespan <= 0:
            ep.behavior_cluster = "ephemeral"
        elif lifespan >= total_frames * 0.8:
            if action_diversity <= 3:
                ep.behavior_cluster = "structure"  # turret, crystal, vain
            else:
                ep.behavior_cluster = "persistent_npc"  # jungle boss?
        elif lifespan < total_frames * 0.1:
            if density > 5:
                ep.behavior_cluster = "projectile_or_effect"
            else:
                ep.behavior_cluster = "minion"
        elif lifespan < total_frames * 0.4:
            ep.behavior_cluster = "jungle_creep"
        else:
            ep.behavior_cluster = "objective_or_boss"


# ---------------------------------------------------------------------------
# 3. Event Sequence Analysis
# ---------------------------------------------------------------------------
def analyze_event_sequences(
    all_events: List[EventRecord],
    player_entity_ids: Set[int],
) -> Dict[str, Any]:
    """
    Find common event sequences:
    - Bigram transitions (A -> B)
    - Repeating patterns / cooldown cycles
    - Events that always follow other events
    - State machine model of transitions
    """
    # Sort events by (entity_id, frame, offset) to get per-entity ordering
    sorted_events = sorted(all_events, key=lambda e: (e.entity_id, e.frame, e.offset))

    # Per-entity action sequences
    entity_sequences: Dict[int, List[int]] = defaultdict(list)
    for ev in sorted_events:
        entity_sequences[ev.entity_id].append(ev.action)

    # ---- Bigram analysis (global) ----
    bigram_counter: Counter = Counter()
    for eid, seq in entity_sequences.items():
        for i in range(len(seq) - 1):
            bigram_counter[(seq[i], seq[i + 1])] += 1

    total_bigrams = sum(bigram_counter.values())

    # ---- Transition probabilities per action ----
    outgoing: Dict[int, Counter] = defaultdict(Counter)
    for (a, b), cnt in bigram_counter.items():
        outgoing[a][b] += cnt

    transitions: List[Dict[str, Any]] = []
    for from_a, targets in outgoing.items():
        total_from = sum(targets.values())
        for to_b, cnt in targets.most_common(5):
            transitions.append({
                "from": f"0x{from_a:02X}",
                "to": f"0x{to_b:02X}",
                "count": cnt,
                "probability": round(cnt / total_from, 4),
            })

    transitions.sort(key=lambda t: t["count"], reverse=True)

    # ---- "Always follows" detection ----
    # For each action B, check if there is a single action A that always precedes it
    preceding: Dict[int, Counter] = defaultdict(Counter)
    for (a, b), cnt in bigram_counter.items():
        preceding[b][a] += cnt

    always_follows: List[Dict[str, Any]] = []
    for action_b, pred_counter in preceding.items():
        total_b = sum(pred_counter.values())
        if total_b < 5:
            continue
        top_a, top_cnt = pred_counter.most_common(1)[0]
        ratio = top_cnt / total_b
        if ratio >= 0.8:
            always_follows.append({
                "action": f"0x{action_b:02X}",
                "preceded_by": f"0x{top_a:02X}",
                "ratio": round(ratio, 4),
                "occurrences": total_b,
            })

    always_follows.sort(key=lambda x: x["ratio"], reverse=True)

    # ---- Trigram patterns (top common 3-event sequences) ----
    trigram_counter: Counter = Counter()
    for eid, seq in entity_sequences.items():
        for i in range(len(seq) - 2):
            trigram_counter[(seq[i], seq[i + 1], seq[i + 2])] += 1

    common_trigrams = [
        {
            "sequence": [f"0x{a:02X}" for a in tri],
            "count": cnt,
        }
        for tri, cnt in trigram_counter.most_common(30)
    ]

    # ---- Repeating pattern detection (cooldown cycles) ----
    repeating_patterns: List[Dict[str, Any]] = []
    for eid in player_entity_ids:
        seq = entity_sequences.get(eid, [])
        if len(seq) < 10:
            continue
        patterns = _find_repeating_subsequences(seq, min_len=2, max_len=5, min_reps=3)
        for pat, reps in patterns[:5]:
            repeating_patterns.append({
                "entity_id": eid,
                "pattern": [f"0x{a:02X}" for a in pat],
                "repetitions": reps,
            })

    return {
        "total_bigrams": total_bigrams,
        "top_transitions": transitions[:50],
        "always_follows": always_follows[:20],
        "common_trigrams": common_trigrams,
        "repeating_patterns": repeating_patterns[:30],
    }


def _find_repeating_subsequences(
    seq: List[int],
    min_len: int = 2,
    max_len: int = 5,
    min_reps: int = 3,
) -> List[Tuple[Tuple[int, ...], int]]:
    """Find subsequences that repeat consecutively at least min_reps times."""
    results: List[Tuple[Tuple[int, ...], int]] = []
    seen: Set[Tuple[int, ...]] = set()

    for pat_len in range(min_len, max_len + 1):
        for start in range(len(seq) - pat_len * min_reps + 1):
            pattern = tuple(seq[start:start + pat_len])
            if pattern in seen:
                continue

            # Count consecutive repetitions starting at this position
            reps = 1
            pos = start + pat_len
            while pos + pat_len <= len(seq):
                if tuple(seq[pos:pos + pat_len]) == pattern:
                    reps += 1
                    pos += pat_len
                else:
                    break

            if reps >= min_reps:
                seen.add(pattern)
                results.append((pattern, reps))

    results.sort(key=lambda x: x[1], reverse=True)
    return results


# ---------------------------------------------------------------------------
# 4. Cross-Frame Analysis
# ---------------------------------------------------------------------------
def analyze_cross_frame(
    all_events: List[EventRecord],
    total_frames: int,
    player_entity_ids: Set[int],
) -> Dict[str, Any]:
    """
    Compare event distributions across frames:
    - Events unique to early / late frames
    - Entity count changes (spawns / deaths)
    - Game phase markers
    """
    events_per_frame: Dict[int, List[EventRecord]] = defaultdict(list)
    for ev in all_events:
        events_per_frame[ev.frame].append(ev)

    sorted_frames = sorted(events_per_frame.keys())
    if not sorted_frames:
        return {"error": "no frames found"}

    # ---- Per-frame statistics ----
    frame_stats: List[Dict[str, Any]] = []
    for fn in sorted_frames:
        frame_evs = events_per_frame[fn]
        action_counts = Counter(e.action for e in frame_evs)
        entity_counts = Counter(e.entity_id for e in frame_evs)
        frame_stats.append({
            "frame": fn,
            "event_count": len(frame_evs),
            "unique_entities": len(entity_counts),
            "unique_actions": len(action_counts),
            "top_actions": {
                f"0x{a:02X}": c for a, c in action_counts.most_common(5)
            },
        })

    # ---- Early / Late frame analysis ----
    if len(sorted_frames) >= 4:
        quarter = max(len(sorted_frames) // 4, 1)
        early_frames = set(sorted_frames[:quarter])
        late_frames = set(sorted_frames[-quarter:])
        mid_frames = set(sorted_frames[quarter:-quarter])

        early_actions: Counter = Counter()
        late_actions: Counter = Counter()
        mid_actions: Counter = Counter()

        for ev in all_events:
            if ev.frame in early_frames:
                early_actions[ev.action] += 1
            elif ev.frame in late_frames:
                late_actions[ev.action] += 1
            elif ev.frame in mid_frames:
                mid_actions[ev.action] += 1

        # Actions that appear only in early frames
        early_only = {
            f"0x{a:02X}": c
            for a, c in early_actions.items()
            if a not in late_actions and a not in mid_actions and c >= 3
        }
        # Actions that appear only in late frames
        late_only = {
            f"0x{a:02X}": c
            for a, c in late_actions.items()
            if a not in early_actions and a not in mid_actions and c >= 3
        }
    else:
        early_only = {}
        late_only = {}

    # ---- Entity count per frame (spawn/death tracking) ----
    entity_timeline: Dict[int, Dict[str, int]] = {}
    prev_entities: Set[int] = set()
    for fn in sorted_frames:
        cur_entities = {e.entity_id for e in events_per_frame[fn]}
        spawned = cur_entities - prev_entities
        died = prev_entities - cur_entities
        entity_timeline[fn] = {
            "active": len(cur_entities),
            "spawned": len(spawned),
            "died": len(died),
        }
        prev_entities = cur_entities

    # ---- Game phase detection heuristics ----
    phases = _detect_game_phases(frame_stats, sorted_frames, entity_timeline)

    return {
        "total_frames_analyzed": len(sorted_frames),
        "frame_stats": frame_stats,
        "early_only_actions": early_only,
        "late_only_actions": late_only,
        "entity_timeline": {
            str(k): v for k, v in entity_timeline.items()
        },
        "detected_phases": phases,
    }


def _detect_game_phases(
    frame_stats: List[Dict[str, Any]],
    sorted_frames: List[int],
    entity_timeline: Dict[int, Dict[str, int]],
) -> List[Dict[str, Any]]:
    """
    Heuristic game phase detection:
    - Laning: low entity interaction, steady event rate
    - Teamfight: spike in event count and entity interactions
    - Objective: specific entity patterns
    """
    if len(frame_stats) < 4:
        return []

    event_counts = [fs["event_count"] for fs in frame_stats]
    mean_events = sum(event_counts) / len(event_counts)
    std_events = math.sqrt(
        sum((c - mean_events) ** 2 for c in event_counts) / len(event_counts)
    ) if len(event_counts) > 1 else 0.0

    threshold_high = mean_events + 1.5 * std_events if std_events > 0 else mean_events * 1.5

    phases: List[Dict[str, Any]] = []

    for fs in frame_stats:
        fn = fs["frame"]
        et = entity_timeline.get(fn, {})
        event_count = fs["event_count"]

        if event_count > threshold_high:
            phase_label = "teamfight_spike"
            confidence = min((event_count - mean_events) / (std_events + 1e-9) * 0.2, 1.0)
        elif et.get("spawned", 0) > 5:
            phase_label = "spawn_wave"
            confidence = 0.5
        elif et.get("died", 0) > 3:
            phase_label = "death_spike"
            confidence = 0.5
        else:
            continue

        phases.append({
            "frame": fn,
            "phase": phase_label,
            "event_count": event_count,
            "entities_spawned": et.get("spawned", 0),
            "entities_died": et.get("died", 0),
            "confidence": round(confidence, 3),
        })

    return phases


# ---------------------------------------------------------------------------
# 5. Report generation
# ---------------------------------------------------------------------------
def build_json_report(
    replay_name: str,
    total_frames: int,
    player_info: List[Dict[str, Any]],
    action_profiles: Dict[int, ActionCodeProfile],
    entity_profiles: Dict[int, EntityProfile],
    sequence_analysis: Dict[str, Any],
    cross_frame: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the comprehensive JSON report."""
    # Serialise action profiles
    action_profiles_ser: Dict[str, Any] = {}
    for action in sorted(action_profiles.keys()):
        ap = action_profiles[action]
        action_profiles_ser[ap.action_hex] = {
            "total_occurrences": ap.total_occurrences,
            "distinct_entities": ap.distinct_entities,
            "player_entity_count": ap.player_entity_count,
            "non_player_entity_count": ap.non_player_entity_count,
            "dominant_payload_length": ap.dominant_payload_length,
            "payload_lengths": {str(k): v for k, v in ap.payload_lengths.items()},
            "first_seen_frame": ap.first_seen_frame,
            "last_seen_frame": ap.last_seen_frame,
            "entity_id_refs_in_payload": ap.entity_id_refs_in_payload,
            "potential_float_fields": ap.potential_float_fields,
            "potential_counter_fields": ap.potential_counter_fields,
            "confidence": ap.confidence,
            "hypothesis": ap.hypothesis,
            "sample_payloads": ap.sample_payloads,
            "fields": ap.fields,
        }

    # Serialise entity profiles
    entity_profiles_ser: Dict[str, Any] = {}
    for eid in sorted(entity_profiles.keys()):
        ep = entity_profiles[eid]
        entity_profiles_ser[str(eid)] = {
            "entity_id": ep.entity_id,
            "is_player": ep.is_player,
            "player_name": ep.player_name,
            "team": ep.team,
            "behavior_cluster": ep.behavior_cluster,
            "first_seen_frame": ep.first_seen_frame,
            "last_seen_frame": ep.last_seen_frame,
            "lifespan_frames": ep.lifespan_frames(),
            "total_events": ep.total_events,
            "action_distribution": {
                f"0x{a:02X}": c
                for a, c in sorted(ep.action_distribution.items(), key=lambda x: -x[1])
            },
            "interacts_with": sorted(ep.interacts_with),
        }

    # Cluster summary for entities
    cluster_summary: Dict[str, int] = Counter()
    for ep in entity_profiles.values():
        cluster_summary[ep.behavior_cluster] += 1

    # Action code summary
    codes_by_frequency = sorted(
        action_profiles.values(),
        key=lambda p: p.total_occurrences,
        reverse=True,
    )

    return {
        "meta": {
            "replay_name": replay_name,
            "total_frames": total_frames,
            "total_action_codes_found": len(action_profiles),
            "total_entities_found": len(entity_profiles),
            "player_entities": len([e for e in entity_profiles.values() if e.is_player]),
            "non_player_entities": len([e for e in entity_profiles.values() if not e.is_player]),
        },
        "players": player_info,
        "action_code_summary": [
            {
                "action": p.action_hex,
                "occurrences": p.total_occurrences,
                "player_entities": p.player_entity_count,
                "hypothesis": p.hypothesis,
                "confidence": p.confidence,
            }
            for p in codes_by_frequency
        ],
        "action_code_profiles": action_profiles_ser,
        "entity_classification": {
            "cluster_summary": dict(cluster_summary),
            "entities": entity_profiles_ser,
        },
        "event_sequences": sequence_analysis,
        "cross_frame_analysis": cross_frame,
    }


def generate_markdown_summary(report: Dict[str, Any]) -> str:
    """Generate a human-readable markdown summary."""
    lines: List[str] = []
    meta = report["meta"]

    lines.append("# Deep Event Mapper Report")
    lines.append("")
    lines.append(f"**Replay:** {meta['replay_name']}")
    lines.append(f"**Frames:** {meta['total_frames']}")
    lines.append(f"**Action Codes Found:** {meta['total_action_codes_found']}")
    lines.append(f"**Entities Tracked:** {meta['total_entities_found']} "
                 f"({meta['player_entities']} players, {meta['non_player_entities']} NPCs)")
    lines.append("")

    # Players
    lines.append("## Players")
    lines.append("")
    lines.append("| Entity ID | Name | Team |")
    lines.append("|-----------|------|------|")
    for p in report.get("players", []):
        lines.append(f"| {p['entity_id']} | {p['name']} | {p['team']} |")
    lines.append("")

    # Top action codes
    lines.append("## Top Action Codes (by frequency)")
    lines.append("")
    lines.append("| Code | Occurrences | Player Entities | Hypothesis | Confidence |")
    lines.append("|------|-------------|-----------------|------------|------------|")
    for item in report.get("action_code_summary", [])[:40]:
        hyp = item.get("hypothesis") or "-"
        conf = f"{item['confidence']:.2f}"
        lines.append(
            f"| {item['action']} | {item['occurrences']} | "
            f"{item['player_entities']} | {hyp} | {conf} |"
        )
    lines.append("")

    # Payload structure highlights
    lines.append("## Payload Structure Highlights")
    lines.append("")
    profiles = report.get("action_code_profiles", {})
    highlighted = sorted(
        profiles.items(),
        key=lambda kv: kv[1].get("confidence", 0),
        reverse=True,
    )[:15]

    for action_hex, prof in highlighted:
        lines.append(f"### {action_hex}")
        lines.append(f"- Occurrences: {prof['total_occurrences']}")
        lines.append(f"- Dominant payload length: {prof['dominant_payload_length']} bytes")
        lines.append(f"- Entity ID refs in payload: {prof['entity_id_refs_in_payload']}")
        if prof.get("potential_float_fields"):
            lines.append(f"- Potential float offsets: {prof['potential_float_fields']}")
        if prof.get("potential_counter_fields"):
            lines.append(f"- Potential counter offsets: {prof['potential_counter_fields']}")
        if prof.get("hypothesis"):
            lines.append(f"- **Hypothesis: {prof['hypothesis']}**")

        # Fixed fields
        fixed_fields = [f for f in prof.get("fields", []) if f.get("is_fixed")]
        if fixed_fields:
            fixed_str = ", ".join(
                f"offset {f['offset']}=0x{f['fixed_value']:02X}" for f in fixed_fields
            )
            lines.append(f"- Fixed bytes: {fixed_str}")

        if prof.get("sample_payloads"):
            lines.append(f"- Sample: `{prof['sample_payloads'][0]}`")
        lines.append("")

    # Entity classification
    lines.append("## Entity Classification")
    lines.append("")
    cluster_summary = report.get("entity_classification", {}).get("cluster_summary", {})
    lines.append("| Cluster | Count |")
    lines.append("|---------|-------|")
    for cluster, count in sorted(cluster_summary.items(), key=lambda x: -x[1]):
        lines.append(f"| {cluster} | {count} |")
    lines.append("")

    # Event sequences
    seq = report.get("event_sequences", {})
    lines.append("## Event Sequence Analysis")
    lines.append("")
    lines.append(f"Total bigrams analyzed: {seq.get('total_bigrams', 0)}")
    lines.append("")

    # Top transitions
    lines.append("### Top Transitions (A -> B)")
    lines.append("")
    lines.append("| From | To | Count | Probability |")
    lines.append("|------|----|-------|-------------|")
    for tr in seq.get("top_transitions", [])[:20]:
        lines.append(
            f"| {tr['from']} | {tr['to']} | {tr['count']} | {tr['probability']:.3f} |"
        )
    lines.append("")

    # Always follows
    af = seq.get("always_follows", [])
    if af:
        lines.append("### Events That Almost Always Follow Another")
        lines.append("")
        lines.append("| Action | Preceded By | Ratio | Occurrences |")
        lines.append("|--------|-------------|-------|-------------|")
        for item in af[:15]:
            lines.append(
                f"| {item['action']} | {item['preceded_by']} | "
                f"{item['ratio']:.3f} | {item['occurrences']} |"
            )
        lines.append("")

    # Common trigrams
    tg = seq.get("common_trigrams", [])
    if tg:
        lines.append("### Common 3-Event Sequences")
        lines.append("")
        lines.append("| Sequence | Count |")
        lines.append("|----------|-------|")
        for item in tg[:15]:
            seq_str = " -> ".join(item["sequence"])
            lines.append(f"| {seq_str} | {item['count']} |")
        lines.append("")

    # Repeating patterns
    rp = seq.get("repeating_patterns", [])
    if rp:
        lines.append("### Repeating Patterns (Cooldown Cycles)")
        lines.append("")
        for item in rp[:10]:
            pat_str = " -> ".join(item["pattern"])
            lines.append(f"- Entity {item['entity_id']}: `{pat_str}` x{item['repetitions']}")
        lines.append("")

    # Cross-frame analysis
    cf = report.get("cross_frame_analysis", {})
    lines.append("## Cross-Frame Analysis")
    lines.append("")
    lines.append(f"Frames analyzed: {cf.get('total_frames_analyzed', 0)}")
    lines.append("")

    early = cf.get("early_only_actions", {})
    if early:
        lines.append("### Early-Only Actions (first quarter)")
        lines.append("")
        for code, cnt in sorted(early.items(), key=lambda x: -x[1]):
            lines.append(f"- {code}: {cnt} occurrences")
        lines.append("")

    late = cf.get("late_only_actions", {})
    if late:
        lines.append("### Late-Only Actions (last quarter)")
        lines.append("")
        for code, cnt in sorted(late.items(), key=lambda x: -x[1]):
            lines.append(f"- {code}: {cnt} occurrences")
        lines.append("")

    phases = cf.get("detected_phases", [])
    if phases:
        lines.append("### Detected Game Phases")
        lines.append("")
        lines.append("| Frame | Phase | Event Count | Spawned | Died | Confidence |")
        lines.append("|-------|-------|-------------|---------|------|------------|")
        for ph in phases[:30]:
            lines.append(
                f"| {ph['frame']} | {ph['phase']} | {ph['event_count']} | "
                f"{ph['entities_spawned']} | {ph['entities_died']} | {ph['confidence']:.2f} |"
            )
        lines.append("")

    lines.append("---")
    lines.append("*Generated by deep_event_mapper.py*")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------
def run_analysis(
    replay_path: Path,
    output_dir: Optional[Path] = None,
    truth_path: Optional[Path] = None,
    max_frames: Optional[int] = None,
    scan_all_entities: bool = False,
) -> Dict[str, Any]:
    """
    Run the full deep event mapping analysis pipeline.

    Args:
        replay_path: Path to replay folder or .0.vgr file.
        output_dir: Directory for output files. Defaults to replay folder.
        truth_path: Optional path to truth data JSON.
        max_frames: Limit number of frames to process (for speed).
        scan_all_entities: If True, discover entities from data instead of
                          only using player entity IDs.

    Returns:
        The complete analysis report as a dict.
    """
    frame_dir, replay_name = find_replay_info(replay_path)
    first_frame_path = frame_dir / f"{replay_name}.0.vgr"

    print(f"[deep_event_mapper] Replay: {replay_name}")
    print(f"[deep_event_mapper] Frame dir: {frame_dir}")

    # --- Extract player entities ---
    player_info = extract_player_entities(first_frame_path)
    player_entity_ids: Set[int] = {p["entity_id"] for p in player_info}
    print(f"[deep_event_mapper] Player entities: {sorted(player_entity_ids)}")

    # --- Read frames and extract events ---
    all_events: List[EventRecord] = []
    total_frames = 0

    print("[deep_event_mapper] Reading frames and extracting events...")
    for frame_num, frame_data in iter_frames(frame_dir, replay_name):
        if max_frames is not None and frame_num >= max_frames:
            break
        total_frames += 1

        if scan_all_entities:
            # Discover entity IDs from data on first frame, then reuse
            if frame_num == 0:
                discovered_eids = discover_entity_ids(frame_data, min_occurrences=3)
                discovered_eids |= player_entity_ids
                target_eids = discovered_eids
                print(f"[deep_event_mapper] Discovered {len(target_eids)} entities "
                      f"(including {len(player_entity_ids)} players)")
            events = extract_events_from_data(
                frame_data, frame_num, entity_ids=target_eids,
            )
        else:
            # Discover all entities from combined data approach:
            # Use a moderate threshold to find active entities
            discovered_eids = discover_entity_ids(frame_data, min_occurrences=3)
            combined_eids = player_entity_ids | discovered_eids
            events = extract_events_from_data(
                frame_data, frame_num, entity_ids=combined_eids,
            )

        all_events.extend(events)

        if (frame_num + 1) % 50 == 0:
            print(f"  Frame {frame_num}: {len(all_events)} events so far")

    print(f"[deep_event_mapper] Total events extracted: {len(all_events)}")
    print(f"[deep_event_mapper] Total frames: {total_frames}")

    # --- Collect all discovered entity IDs ---
    all_entity_ids: Set[int] = {ev.entity_id for ev in all_events}
    print(f"[deep_event_mapper] Total unique entities: {len(all_entity_ids)}")

    # --- 1. Payload Structure Analysis ---
    print("[deep_event_mapper] Analyzing payload structures...")
    events_by_action: Dict[int, List[EventRecord]] = defaultdict(list)
    for ev in all_events:
        events_by_action[ev.action].append(ev)

    action_profiles = analyze_payload_structure(
        events_by_action, player_entity_ids, all_entity_ids,
    )
    print(f"[deep_event_mapper] Action codes profiled: {len(action_profiles)}")

    # --- 2. Entity Classification ---
    print("[deep_event_mapper] Classifying entities...")
    entity_profiles = classify_entities(all_events, player_entity_ids, total_frames)

    # Enrich entity profiles with player info
    player_lookup = {p["entity_id"]: p for p in player_info}
    for eid, ep in entity_profiles.items():
        if eid in player_lookup:
            ep.player_name = player_lookup[eid]["name"]
            ep.team = player_lookup[eid]["team"]
            ep.team_id = player_lookup[eid].get("team_id")

    cluster_counts = Counter(ep.behavior_cluster for ep in entity_profiles.values())
    print(f"[deep_event_mapper] Entity clusters: {dict(cluster_counts)}")

    # --- 3. Event Sequence Analysis ---
    print("[deep_event_mapper] Analyzing event sequences...")
    sequence_analysis = analyze_event_sequences(all_events, player_entity_ids)
    print(f"[deep_event_mapper] Bigrams: {sequence_analysis['total_bigrams']}, "
          f"always-follows rules: {len(sequence_analysis['always_follows'])}")

    # --- 4. Cross-Frame Analysis ---
    print("[deep_event_mapper] Performing cross-frame analysis...")
    cross_frame = analyze_cross_frame(all_events, total_frames, player_entity_ids)
    print(f"[deep_event_mapper] Detected phases: {len(cross_frame.get('detected_phases', []))}")

    # --- 5. Build reports ---
    print("[deep_event_mapper] Building reports...")
    report = build_json_report(
        replay_name=replay_name,
        total_frames=total_frames,
        player_info=player_info,
        action_profiles=action_profiles,
        entity_profiles=entity_profiles,
        sequence_analysis=sequence_analysis,
        cross_frame=cross_frame,
    )

    # --- Output ---
    if output_dir is None:
        output_dir = frame_dir

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / f"{replay_name}_deep_event_map.json"
    md_path = output_dir / f"{replay_name}_deep_event_map.md"

    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"[deep_event_mapper] JSON report: {json_path}")

    md_summary = generate_markdown_summary(report)
    md_path.write_text(md_summary, encoding="utf-8")
    print(f"[deep_event_mapper] Markdown report: {md_path}")

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deep Event Mapper - Map all VGR event codes with payload structures",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python deep_event_mapper.py /path/to/replay_folder\n"
            "  python deep_event_mapper.py /path/to/replay_folder --output ./reports\n"
            "  python deep_event_mapper.py /path/to/replay_folder --max-frames 100\n"
        ),
    )
    parser.add_argument(
        "replay_path",
        help="Path to replay folder containing .vgr frame files",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output directory for reports (default: same as replay folder)",
    )
    parser.add_argument(
        "--truth",
        default=None,
        help="Path to truth data JSON (optional, for future correlation)",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=None,
        help="Limit number of frames to process (for faster testing)",
    )
    parser.add_argument(
        "--scan-all",
        action="store_true",
        help="Scan for all entity patterns (slower but more comprehensive)",
    )

    args = parser.parse_args()

    replay_path = Path(args.replay_path)
    if not replay_path.exists():
        print(f"Error: path does not exist: {replay_path}")
        return 1

    output_dir = Path(args.output) if args.output else None
    truth_path = Path(args.truth) if args.truth else None

    try:
        report = run_analysis(
            replay_path=replay_path,
            output_dir=output_dir,
            truth_path=truth_path,
            max_frames=args.max_frames,
            scan_all_entities=args.scan_all,
        )
        total_codes = report["meta"]["total_action_codes_found"]
        total_entities = report["meta"]["total_entities_found"]
        print(f"\n[deep_event_mapper] Analysis complete.")
        print(f"  Action codes mapped: {total_codes}")
        print(f"  Entities classified: {total_entities}")
        return 0
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
