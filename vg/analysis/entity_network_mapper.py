#!/usr/bin/env python3
"""
Entity Network Mapper - Full entity discovery, interaction graph, and lifecycle tracking
for Vainglory replay files.

Maps ALL entities in the game (players, turrets, minions, jungle monsters, objectives)
and their interactions over time.

Event structure: [EntityID(2B LE)][00 00][ActionCode(1B)][Payload...]
"""

import os
import sys
import json
import struct
import argparse
import math
from pathlib import Path
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any, Optional, Tuple, Set
from datetime import datetime

# Optional imports from vg.core
try:
    from vg.core.vgr_parser import VGRParser
except ImportError:
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent / "core"))
        from vgr_parser import VGRParser
    except ImportError:
        VGRParser = None


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Action codes known to contain target entity IDs in payload
INTERACTION_ACTIONS = {0x42, 0x43, 0x44}

# Offsets within payload where target entity IDs may appear (2-byte LE each)
TARGET_ENTITY_OFFSETS = [5, 7, 9, 11, 13, 15]

# Action codes associated with movement / position updates
MOVEMENT_ACTIONS = {0x02, 0x03, 0x04, 0x05, 0x06}

# Action codes associated with attacks / damage
ATTACK_ACTIONS = {0x42, 0x43, 0x44, 0x0E}

# System entity (entity 0 often represents global/system events)
SYSTEM_ENTITY_ID = 0

# Minimum events to consider an entity "real" (filter noise)
MIN_ENTITY_EVENTS = 5

# Gap threshold: if an entity disappears for this many frames, consider it dead
DEATH_GAP_FRAMES = 3

# Turret classification thresholds
TURRET_MAX_MOVEMENT_RATIO = 0.05  # Turrets move very little
TURRET_MIN_INTERACTION_EVENTS = 10  # Turrets interact with minions a lot

# Minion spawn periodicity window (frames)
MINION_SPAWN_PERIOD_MIN = 2
MINION_SPAWN_PERIOD_MAX = 8

# Vainglory structure constants
TURRETS_3V3 = 4 + 2  # 2 per lane per team + 2 vain crystals
TURRETS_5V5 = 18 + 2  # 3 lanes x 3 turrets x 2 teams + 2 vain crystals


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class EntityInfo:
    """Information about a single entity discovered in the replay."""
    entity_id: int
    is_player: bool = False
    player_name: Optional[str] = None
    classification: str = "unknown"  # player, turret, minion, jungle, objective, system, unknown
    first_frame: int = 0
    last_frame: int = 0
    total_events: int = 0
    event_distribution: Dict[str, int] = field(default_factory=dict)
    unique_action_codes: int = 0
    movement_events: int = 0
    attack_events: int = 0
    movement_ratio: float = 0.0
    frames_active: List[int] = field(default_factory=list)
    lifecycle_spans: List[Tuple[int, int]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Convert lifecycle spans tuples to lists for JSON
        d["lifecycle_spans"] = [list(span) for span in self.lifecycle_spans]
        # Don't serialize the full frames_active list in output (too large)
        del d["frames_active"]
        d["num_frames_active"] = len(self.frames_active)
        return d


@dataclass
class Interaction:
    """A directed interaction between two entities."""
    source_id: int
    target_id: int
    action_code: int
    count: int = 0
    first_frame: int = 0
    last_frame: int = 0
    frames: List[int] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        del d["frames"]
        d["num_frames"] = len(self.frames)
        return d


@dataclass
class KillCandidate:
    """A potential kill event: source attacked target, and target disappeared."""
    source_id: int
    target_id: int
    last_interaction_frame: int
    target_last_seen_frame: int
    target_respawn_frame: Optional[int] = None
    gap_frames: int = 0
    action_code: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Frame reading utilities
# ---------------------------------------------------------------------------

def find_replay_files(replay_path: Path) -> Tuple[Optional[Path], str]:
    """
    Find the .0.vgr file and derive replay name.

    Returns:
        (frame_dir, replay_name) or (None, "") if not found.
    """
    if replay_path.is_file() and str(replay_path).endswith('.vgr'):
        frame_dir = replay_path.parent
        # Derive replay name: e.g. "replayname.0.vgr" -> "replayname"
        stem = replay_path.stem  # "replayname.0"
        replay_name = stem.rsplit('.', 1)[0] if '.' in stem else stem
        return frame_dir, replay_name

    if replay_path.is_dir():
        for f in replay_path.rglob('*.0.vgr'):
            frame_dir = f.parent
            stem = f.stem
            replay_name = stem.rsplit('.', 1)[0] if '.' in stem else stem
            return frame_dir, replay_name

    return None, ""


def read_frame_files(frame_dir: Path, replay_name: str) -> List[Tuple[int, bytes]]:
    """
    Read all frame files in order.

    Returns:
        List of (frame_index, frame_data) sorted by index.
    """
    frames = list(frame_dir.glob(f"{replay_name}.*.vgr"))
    result = []
    for f in frames:
        try:
            idx = int(f.stem.split('.')[-1])
        except ValueError:
            idx = 0
        result.append((idx, f.read_bytes()))
    result.sort(key=lambda x: x[0])
    return result


def read_all_frame_data(frame_dir: Path, replay_name: str) -> bytes:
    """Concatenate all frame data in order."""
    frames = read_frame_files(frame_dir, replay_name)
    return b"".join(data for _, data in frames)


# ---------------------------------------------------------------------------
# Player block extraction
# ---------------------------------------------------------------------------

PLAYER_BLOCK_MARKER = bytes([0xDA, 0x03, 0xEE])
PLAYER_BLOCK_MARKER_ALT = bytes([0xE0, 0x03, 0xEE])
ENTITY_ID_OFFSET = 0xA5


def extract_player_entities(data: bytes) -> Dict[int, str]:
    """
    Extract player entity IDs from player blocks in the first frame.

    Returns:
        Dict mapping entity_id -> player_name.
    """
    players: Dict[int, str] = {}
    search_start = 0
    markers = (PLAYER_BLOCK_MARKER, PLAYER_BLOCK_MARKER_ALT)

    while True:
        pos = -1
        marker = None
        for candidate in markers:
            idx = data.find(candidate, search_start)
            if idx != -1 and (pos == -1 or idx < pos):
                pos = idx
                marker = candidate
        if pos == -1 or marker is None:
            break

        name_start = pos + len(marker)
        name_end = name_start
        while name_end < len(data) and name_end < name_start + 30:
            byte = data[name_end]
            if byte < 32 or byte > 126:
                break
            name_end += 1

        if name_end > name_start:
            try:
                name = data[name_start:name_end].decode('ascii')
            except Exception:
                name = ""

            if len(name) >= 3 and not name.startswith('GameMode'):
                if pos + ENTITY_ID_OFFSET + 2 <= len(data):
                    entity_id = int.from_bytes(
                        data[pos + ENTITY_ID_OFFSET:pos + ENTITY_ID_OFFSET + 2], 'little'
                    )
                    if entity_id not in players:
                        players[entity_id] = name

        search_start = pos + 1

    return players


# ---------------------------------------------------------------------------
# Event scanning
# ---------------------------------------------------------------------------

def scan_events_in_frame(
    data: bytes,
    frame_index: int,
    entity_events: Dict[int, Dict[str, Any]],
    interaction_map: Dict[Tuple[int, int, int], Interaction],
    all_entity_ids: Set[int],
):
    """
    Scan a single frame for all entity events and interactions.

    Updates entity_events and interaction_map in place.

    Event pattern: [EntityID(2B LE)][00 00][ActionCode(1B)][Payload...]
    """
    length = len(data)
    # We need at least 5 bytes: 2 entity + 2 zero + 1 action
    if length < 5:
        return

    idx = 0
    while idx <= length - 5:
        # Check for the [XX XX][00 00] pattern
        if data[idx + 2] == 0x00 and data[idx + 3] == 0x00:
            entity_id = int.from_bytes(data[idx:idx + 2], 'little')

            # Skip entity 0 initial scan for speed -- but track it
            action_code = data[idx + 4]

            # Record this entity's event
            if entity_id not in entity_events:
                entity_events[entity_id] = {
                    "first_frame": frame_index,
                    "last_frame": frame_index,
                    "total_events": 0,
                    "action_counts": Counter(),
                    "frames_seen": set(),
                    "movement_events": 0,
                    "attack_events": 0,
                }

            info = entity_events[entity_id]
            info["last_frame"] = frame_index
            info["total_events"] += 1
            info["action_counts"][action_code] += 1
            info["frames_seen"].add(frame_index)

            if action_code in MOVEMENT_ACTIONS:
                info["movement_events"] += 1
            if action_code in ATTACK_ACTIONS:
                info["attack_events"] += 1

            all_entity_ids.add(entity_id)

            # Check for target entity IDs in payload (interaction events)
            if action_code in INTERACTION_ACTIONS:
                for offset in TARGET_ENTITY_OFFSETS:
                    abs_offset = idx + 5 + offset  # +5 = past the header
                    if abs_offset + 2 <= length:
                        target_id = int.from_bytes(
                            data[abs_offset:abs_offset + 2], 'little'
                        )
                        # Validate: target should be a reasonable entity ID
                        # and not zero-padding noise
                        if target_id > 0 and target_id != entity_id:
                            # Check if followed by 00 00 to validate entity pattern
                            # Or if the target_id has been seen as a source entity
                            # For initial scan we record all, filter later
                            key = (entity_id, target_id, action_code)
                            if key not in interaction_map:
                                interaction_map[key] = Interaction(
                                    source_id=entity_id,
                                    target_id=target_id,
                                    action_code=action_code,
                                    first_frame=frame_index,
                                    last_frame=frame_index,
                                )
                            inter = interaction_map[key]
                            inter.count += 1
                            inter.last_frame = frame_index
                            inter.frames.append(frame_index)

            idx += 5  # Skip past this event header
        else:
            idx += 1


def scan_all_frames(
    frames: List[Tuple[int, bytes]],
) -> Tuple[Dict[int, Dict[str, Any]], Dict[Tuple[int, int, int], Interaction], Set[int]]:
    """
    Scan all frames for entity events and interactions.

    Returns:
        (entity_events, interaction_map, all_entity_ids)
    """
    entity_events: Dict[int, Dict[str, Any]] = {}
    interaction_map: Dict[Tuple[int, int, int], Interaction] = {}
    all_entity_ids: Set[int] = set()

    for frame_index, data in frames:
        scan_events_in_frame(data, frame_index, entity_events, interaction_map, all_entity_ids)

    return entity_events, interaction_map, all_entity_ids


# ---------------------------------------------------------------------------
# Entity classification
# ---------------------------------------------------------------------------

def classify_entities(
    entity_events: Dict[int, Dict[str, Any]],
    player_entities: Dict[int, str],
    interaction_map: Dict[Tuple[int, int, int], Interaction],
    total_frames: int,
    min_events: int = MIN_ENTITY_EVENTS,
    gap_threshold: int = DEATH_GAP_FRAMES,
) -> Dict[int, EntityInfo]:
    """
    Classify all discovered entities by behavior.

    Classification heuristics:
    - player: entity ID found in player blocks
    - system: entity ID 0 (global events)
    - turret: low movement ratio, persistent presence, high minion interaction
    - minion: periodic spawns, short lifespan, linear movement
    - jungle: fixed spawn location, periodic respawn
    - objective: very few instances, high-value interactions (kraken/dragon)
    - unknown: doesn't match any pattern
    """
    entities: Dict[int, EntityInfo] = {}

    for eid, info in entity_events.items():
        if info["total_events"] < min_events:
            continue

        action_counts = info["action_counts"]
        total = info["total_events"]
        movement = info["movement_events"]
        attack = info["attack_events"]
        movement_ratio = movement / total if total > 0 else 0.0
        frames_seen = sorted(info["frames_seen"])
        unique_actions = len(action_counts)

        # Build event distribution as hex strings
        event_dist = {
            f"0x{code:02X}": count
            for code, count in action_counts.most_common()
        }

        entity = EntityInfo(
            entity_id=eid,
            first_frame=info["first_frame"],
            last_frame=info["last_frame"],
            total_events=total,
            event_distribution=event_dist,
            unique_action_codes=unique_actions,
            movement_events=movement,
            attack_events=attack,
            movement_ratio=round(movement_ratio, 4),
            frames_active=frames_seen,
        )

        # Classification
        if eid == SYSTEM_ENTITY_ID:
            entity.classification = "system"
        elif eid in player_entities:
            entity.is_player = True
            entity.player_name = player_entities[eid]
            entity.classification = "player"
        else:
            entity.classification = _classify_non_player(
                entity, interaction_map, total_frames
            )

        # Build lifecycle spans
        entity.lifecycle_spans = _compute_lifecycle_spans(frames_seen, gap_threshold)

        entities[eid] = entity

    return entities


def _classify_non_player(
    entity: EntityInfo,
    interaction_map: Dict[Tuple[int, int, int], Interaction],
    total_frames: int,
) -> str:
    """
    Classify a non-player entity based on behavioral heuristics.

    Returns classification string.
    """
    eid = entity.entity_id
    frames_seen = entity.frames_active
    total = entity.total_events
    movement_ratio = entity.movement_ratio
    lifespan = entity.last_frame - entity.first_frame + 1 if entity.last_frame >= entity.first_frame else 1
    frame_coverage = len(frames_seen) / max(total_frames, 1)

    # Count interactions where this entity is a target or source
    interactions_as_source = 0
    interactions_as_target = 0
    for (src, tgt, act), inter in interaction_map.items():
        if src == eid:
            interactions_as_source += inter.count
        if tgt == eid:
            interactions_as_target += inter.count

    total_interactions = interactions_as_source + interactions_as_target

    # --- Turret detection ---
    # Turrets: low movement, present for long periods, eventually destroyed (single lifecycle)
    # They interact heavily with minions (as source attacking, and as target being attacked)
    if (movement_ratio <= TURRET_MAX_MOVEMENT_RATIO
            and total_interactions >= TURRET_MIN_INTERACTION_EVENTS
            and frame_coverage > 0.15
            and len(entity.lifecycle_spans) <= 2):
        return "turret"

    # --- Minion detection ---
    # Minions: short lifespan, appear in waves, moderate movement
    # They typically live for a few frames and then disappear
    num_spans = len(entity.lifecycle_spans)
    avg_span_length = 0
    if num_spans > 0:
        avg_span_length = sum(
            end - start + 1 for start, end in entity.lifecycle_spans
        ) / num_spans

    if (num_spans == 1
            and avg_span_length <= total_frames * 0.3
            and total < 200
            and movement_ratio > 0.0):
        return "minion"

    # --- Jungle monster detection ---
    # Jungle monsters: fixed spawn, periodic respawns (multiple lifecycle spans),
    # relatively short active periods
    if (num_spans >= 2
            and avg_span_length < total_frames * 0.2
            and frame_coverage < 0.5):
        return "jungle"

    # --- Objective detection ---
    # Objectives (kraken, dragon, vain crystal): rare, high-value,
    # long gap between appearances or single long span near end
    if (total_interactions > 20
            and movement_ratio <= 0.1
            and total < 300
            and frame_coverage < 0.3):
        return "objective"

    return "unknown"


def _compute_lifecycle_spans(
    frames_seen: List[int],
    gap_threshold: int,
) -> List[Tuple[int, int]]:
    """
    Compute lifecycle spans (spawn/death/respawn cycles) from frame presence data.

    A gap of more than gap_threshold frames between appearances indicates death/respawn.

    Returns:
        List of (spawn_frame, death_frame) tuples.
    """
    if not frames_seen:
        return []

    spans = []
    span_start = frames_seen[0]
    prev_frame = frames_seen[0]

    for frame in frames_seen[1:]:
        if frame - prev_frame > gap_threshold:
            spans.append((span_start, prev_frame))
            span_start = frame
        prev_frame = frame

    # Close the last span
    spans.append((span_start, prev_frame))
    return spans


# ---------------------------------------------------------------------------
# Interaction graph construction
# ---------------------------------------------------------------------------

def build_interaction_graph(
    interaction_map: Dict[Tuple[int, int, int], Interaction],
    entities: Dict[int, EntityInfo],
) -> List[Dict[str, Any]]:
    """
    Build a directed interaction graph, filtering to only include known entities.

    Returns list of edge dictionaries.
    """
    edges = []
    for (src, tgt, act), inter in interaction_map.items():
        # Only include interactions where both source and target are known entities
        if src not in entities or tgt not in entities:
            continue

        src_info = entities[src]
        tgt_info = entities[tgt]

        edge = {
            "source_id": src,
            "source_type": src_info.classification,
            "source_name": src_info.player_name or f"entity_{src}",
            "target_id": tgt,
            "target_type": tgt_info.classification,
            "target_name": tgt_info.player_name or f"entity_{tgt}",
            "action_code": f"0x{act:02X}",
            "count": inter.count,
            "first_frame": inter.first_frame,
            "last_frame": inter.last_frame,
            "num_frames": len(inter.frames),
        }
        edges.append(edge)

    # Sort by count descending
    edges.sort(key=lambda e: -e["count"])
    return edges


# ---------------------------------------------------------------------------
# Kill candidate detection
# ---------------------------------------------------------------------------

def find_kill_candidates(
    interaction_map: Dict[Tuple[int, int, int], Interaction],
    entities: Dict[int, EntityInfo],
) -> List[KillCandidate]:
    """
    Find potential kill events: interactions where the target entity stops appearing
    shortly after the interaction.

    Heuristic: if the target's last_frame is close to the last interaction frame
    and the target has a lifecycle gap (respawn) afterward, it's a kill candidate.
    """
    candidates = []

    for (src, tgt, act), inter in interaction_map.items():
        if src not in entities or tgt not in entities:
            continue
        if act not in ATTACK_ACTIONS:
            continue

        target_entity = entities[tgt]
        source_entity = entities[src]

        # Skip system entity as target
        if tgt == SYSTEM_ENTITY_ID:
            continue

        # Check if target has lifecycle gaps (deaths/respawns)
        for i, (span_start, span_end) in enumerate(target_entity.lifecycle_spans):
            # Check if the interaction happened near the end of a lifecycle span
            if inter.last_frame <= span_end and inter.last_frame >= span_start:
                # The interaction happened during this span
                # Check if there's a gap after this span (death)
                respawn_frame = None
                gap = 0
                if i + 1 < len(target_entity.lifecycle_spans):
                    next_span_start = target_entity.lifecycle_spans[i + 1][0]
                    gap = next_span_start - span_end
                    respawn_frame = next_span_start
                elif span_end < target_entity.last_frame:
                    # Last span but not the overall last frame -- unusual
                    pass
                elif span_end == target_entity.last_frame and span_end < (
                    max(e.last_frame for e in entities.values()) if entities else 0
                ):
                    # Entity permanently died (never respawned)
                    gap = 9999  # large gap = permanent death

                if gap > DEATH_GAP_FRAMES:
                    candidate = KillCandidate(
                        source_id=src,
                        target_id=tgt,
                        last_interaction_frame=inter.last_frame,
                        target_last_seen_frame=span_end,
                        target_respawn_frame=respawn_frame,
                        gap_frames=gap,
                        action_code=act,
                    )
                    candidates.append(candidate)

    # Deduplicate: keep one candidate per (source, target, span_end)
    seen = set()
    unique_candidates = []
    for c in candidates:
        key = (c.source_id, c.target_id, c.target_last_seen_frame)
        if key not in seen:
            seen.add(key)
            unique_candidates.append(c)

    # Sort by frame
    unique_candidates.sort(key=lambda c: c.target_last_seen_frame)
    return unique_candidates


# ---------------------------------------------------------------------------
# Turret / objective mapping
# ---------------------------------------------------------------------------

def map_turrets_and_objectives(
    entities: Dict[int, EntityInfo],
    interaction_map: Dict[Tuple[int, int, int], Interaction],
    is_5v5: bool,
) -> Dict[str, Any]:
    """
    Map turret and objective entities, detect destruction order.

    Returns dictionary with turret and objective mapping data.
    """
    turrets = {
        eid: e for eid, e in entities.items()
        if e.classification == "turret"
    }
    objectives = {
        eid: e for eid, e in entities.items()
        if e.classification == "objective"
    }

    expected_turrets = TURRETS_5V5 if is_5v5 else TURRETS_3V3

    # Determine turret destruction order by last_frame
    turret_list = sorted(turrets.values(), key=lambda t: t.last_frame)

    # Categorize turrets by when they were destroyed vs survived
    total_game_frames = max(
        (e.last_frame for e in entities.values()), default=0
    )

    destroyed_turrets = []
    surviving_turrets = []
    for t in turret_list:
        # A turret that disappears before the game ends was likely destroyed
        if len(t.lifecycle_spans) == 1 and t.last_frame < total_game_frames - 2:
            destroyed_turrets.append({
                "entity_id": t.entity_id,
                "destroyed_frame": t.last_frame,
                "first_frame": t.first_frame,
                "total_events": t.total_events,
            })
        else:
            surviving_turrets.append({
                "entity_id": t.entity_id,
                "first_frame": t.first_frame,
                "last_frame": t.last_frame,
                "total_events": t.total_events,
            })

    # Objective entities
    objective_list = []
    for o in objectives.values():
        objective_list.append({
            "entity_id": o.entity_id,
            "first_frame": o.first_frame,
            "last_frame": o.last_frame,
            "total_events": o.total_events,
            "lifecycle_spans": [list(s) for s in o.lifecycle_spans],
            "num_respawns": max(0, len(o.lifecycle_spans) - 1),
        })

    return {
        "expected_turrets": expected_turrets,
        "found_turrets": len(turrets),
        "destroyed_turrets": destroyed_turrets,
        "surviving_turrets": surviving_turrets,
        "destruction_order": [t["entity_id"] for t in destroyed_turrets],
        "objectives": objective_list,
    }


# ---------------------------------------------------------------------------
# Entity timeline construction
# ---------------------------------------------------------------------------

def build_entity_timeline(
    entities: Dict[int, EntityInfo],
) -> Dict[str, Any]:
    """
    Build timeline data for all entities.

    Returns dict with per-entity lifecycle information.
    """
    timeline = {}
    for eid, entity in entities.items():
        timeline[str(eid)] = {
            "entity_id": eid,
            "classification": entity.classification,
            "name": entity.player_name or f"entity_{eid}",
            "first_frame": entity.first_frame,
            "last_frame": entity.last_frame,
            "total_events": entity.total_events,
            "num_frames_active": len(entity.frames_active),
            "lifecycle_spans": [list(s) for s in entity.lifecycle_spans],
            "num_deaths": max(0, len(entity.lifecycle_spans) - 1),
            "is_player": entity.is_player,
        }
    return timeline


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(
    entities: Dict[int, EntityInfo],
    interaction_edges: List[Dict[str, Any]],
    kill_candidates: List[KillCandidate],
    turret_data: Dict[str, Any],
    player_entities: Dict[int, str],
    total_frames: int,
    replay_name: str,
) -> str:
    """Generate a human-readable markdown report."""
    lines = []

    lines.append(f"# Entity Network Report: {replay_name}")
    lines.append(f"Generated: {datetime.now().isoformat()}")
    lines.append("")

    # --- Summary ---
    lines.append("## Summary")
    lines.append("")
    classification_counts = Counter(e.classification for e in entities.values())
    lines.append(f"- **Total entities discovered**: {len(entities)}")
    lines.append(f"- **Total frames**: {total_frames}")
    lines.append(f"- **Player entities**: {classification_counts.get('player', 0)}")
    lines.append(f"- **Turret entities**: {classification_counts.get('turret', 0)}")
    lines.append(f"- **Minion entities**: {classification_counts.get('minion', 0)}")
    lines.append(f"- **Jungle entities**: {classification_counts.get('jungle', 0)}")
    lines.append(f"- **Objective entities**: {classification_counts.get('objective', 0)}")
    lines.append(f"- **System entities**: {classification_counts.get('system', 0)}")
    lines.append(f"- **Unknown entities**: {classification_counts.get('unknown', 0)}")
    lines.append(f"- **Total interactions tracked**: {len(interaction_edges)}")
    lines.append(f"- **Kill candidates found**: {len(kill_candidates)}")
    lines.append("")

    # --- Player entities ---
    lines.append("## Player Entities")
    lines.append("")
    lines.append("| Entity ID | Player Name | Total Events | Unique Actions | First Frame | Last Frame |")
    lines.append("|-----------|-------------|--------------|----------------|-------------|------------|")
    player_list = sorted(
        [e for e in entities.values() if e.is_player],
        key=lambda e: e.entity_id,
    )
    for e in player_list:
        lines.append(
            f"| {e.entity_id} | {e.player_name or 'N/A'} | {e.total_events} "
            f"| {e.unique_action_codes} | {e.first_frame} | {e.last_frame} |"
        )
    lines.append("")

    # --- Non-player entity classification ---
    lines.append("## Non-Player Entity Classification")
    lines.append("")
    for cls in ["turret", "minion", "jungle", "objective", "system", "unknown"]:
        cls_entities = sorted(
            [e for e in entities.values() if e.classification == cls],
            key=lambda e: -e.total_events,
        )
        if not cls_entities:
            continue

        lines.append(f"### {cls.title()} ({len(cls_entities)} entities)")
        lines.append("")
        # Show top 20 by event count
        shown = cls_entities[:20]
        lines.append("| Entity ID | Events | Movement % | Lifecycles | First | Last |")
        lines.append("|-----------|--------|------------|------------|-------|------|")
        for e in shown:
            lines.append(
                f"| {e.entity_id} | {e.total_events} | {e.movement_ratio:.1%} "
                f"| {len(e.lifecycle_spans)} | {e.first_frame} | {e.last_frame} |"
            )
        if len(cls_entities) > 20:
            lines.append(f"| ... | ({len(cls_entities) - 20} more) | | | | |")
        lines.append("")

    # --- Top interactions ---
    lines.append("## Top Interactions (by frequency)")
    lines.append("")
    lines.append("| Source | Target | Action | Count | Frames |")
    lines.append("|--------|--------|--------|-------|--------|")
    for edge in interaction_edges[:50]:
        lines.append(
            f"| {edge['source_name']} ({edge['source_type']}) "
            f"| {edge['target_name']} ({edge['target_type']}) "
            f"| {edge['action_code']} | {edge['count']} | {edge['first_frame']}-{edge['last_frame']} |"
        )
    lines.append("")

    # --- Player interaction summary ---
    lines.append("## Player Interaction Summary")
    lines.append("")
    for e in player_list:
        eid = e.entity_id
        name = e.player_name or f"entity_{eid}"
        lines.append(f"### {name} (entity {eid})")
        lines.append("")

        # Outgoing interactions
        outgoing = [
            edge for edge in interaction_edges
            if edge["source_id"] == eid
        ]
        if outgoing:
            lines.append("**Attacks/interactions initiated:**")
            lines.append("")
            for edge in outgoing[:10]:
                lines.append(
                    f"- -> {edge['target_name']} ({edge['target_type']}): "
                    f"{edge['action_code']} x{edge['count']}"
                )
            lines.append("")

        # Incoming interactions
        incoming = [
            edge for edge in interaction_edges
            if edge["target_id"] == eid
        ]
        if incoming:
            lines.append("**Attacked/targeted by:**")
            lines.append("")
            for edge in incoming[:10]:
                lines.append(
                    f"- <- {edge['source_name']} ({edge['source_type']}): "
                    f"{edge['action_code']} x{edge['count']}"
                )
            lines.append("")

    # --- Kill candidates ---
    lines.append("## Kill Candidates")
    lines.append("")
    if kill_candidates:
        lines.append("| Source | Target | Action | Last Hit Frame | Target Death Frame | Respawn Frame | Gap |")
        lines.append("|--------|--------|--------|----------------|--------------------|--------------:|-----|")
        for kc in kill_candidates[:50]:
            src_name = entities[kc.source_id].player_name or f"entity_{kc.source_id}" if kc.source_id in entities else str(kc.source_id)
            tgt_name = entities[kc.target_id].player_name or f"entity_{kc.target_id}" if kc.target_id in entities else str(kc.target_id)
            respawn = str(kc.target_respawn_frame) if kc.target_respawn_frame is not None else "never"
            lines.append(
                f"| {src_name} | {tgt_name} | 0x{kc.action_code:02X} "
                f"| {kc.last_interaction_frame} | {kc.target_last_seen_frame} "
                f"| {respawn} | {kc.gap_frames} |"
            )
        lines.append("")
    else:
        lines.append("No kill candidates found.")
        lines.append("")

    # --- Turret / objective mapping ---
    lines.append("## Turret & Objective Mapping")
    lines.append("")
    lines.append(f"- Expected turrets: {turret_data['expected_turrets']}")
    lines.append(f"- Found turrets: {turret_data['found_turrets']}")
    lines.append(f"- Destroyed: {len(turret_data['destroyed_turrets'])}")
    lines.append(f"- Surviving: {len(turret_data['surviving_turrets'])}")
    lines.append("")

    if turret_data["destroyed_turrets"]:
        lines.append("**Destruction order:**")
        lines.append("")
        for i, t in enumerate(turret_data["destroyed_turrets"], 1):
            lines.append(f"{i}. Entity {t['entity_id']} - destroyed at frame {t['destroyed_frame']}")
        lines.append("")

    if turret_data["objectives"]:
        lines.append("**Objectives:**")
        lines.append("")
        for o in turret_data["objectives"]:
            lines.append(
                f"- Entity {o['entity_id']}: frames {o['first_frame']}-{o['last_frame']}, "
                f"{o['num_respawns']} respawns"
            )
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main analysis pipeline
# ---------------------------------------------------------------------------

def analyze_replay(
    replay_path: str,
    output_dir: Optional[str] = None,
    min_events: int = MIN_ENTITY_EVENTS,
    gap_threshold: int = DEATH_GAP_FRAMES,
) -> Dict[str, Any]:
    """
    Run the full entity network analysis on a replay.

    Args:
        replay_path: Path to replay folder or .0.vgr file.
        output_dir: Directory for output files. Defaults to replay directory.
        min_events: Minimum events to consider an entity real.
        gap_threshold: Frame gap threshold for death detection.

    Returns:
        Dictionary with all analysis results.
    """
    replay_path_obj = Path(replay_path)
    frame_dir, replay_name = find_replay_files(replay_path_obj)

    if frame_dir is None:
        raise FileNotFoundError(f"No .vgr files found at {replay_path}")

    print(f"[INFO] Replay: {replay_name}")
    print(f"[INFO] Frame directory: {frame_dir}")

    # Read frames
    frames = read_frame_files(frame_dir, replay_name)
    total_frames = len(frames)
    print(f"[INFO] Total frames: {total_frames}")

    if total_frames == 0:
        raise ValueError("No frames found")

    # Extract player entities from first frame
    first_frame_data = frames[0][1]
    player_entities = extract_player_entities(first_frame_data)
    print(f"[INFO] Player entities found: {len(player_entities)}")
    for eid, name in player_entities.items():
        print(f"       entity {eid} -> {name}")

    # Detect game mode for turret expectations
    is_5v5 = len(player_entities) > 6

    # Scan all frames for events and interactions
    print("[INFO] Scanning all frames for entity events...")
    entity_events, interaction_map, all_entity_ids = scan_all_frames(frames)
    print(f"[INFO] Raw entity IDs discovered: {len(all_entity_ids)}")
    print(f"[INFO] Raw interactions: {len(interaction_map)}")

    # Classify entities
    print("[INFO] Classifying entities...")
    entities = classify_entities(
        entity_events, player_entities, interaction_map, total_frames,
        min_events=min_events, gap_threshold=gap_threshold,
    )
    print(f"[INFO] Classified entities (>={min_events} events): {len(entities)}")

    classification_counts = Counter(e.classification for e in entities.values())
    for cls, count in classification_counts.most_common():
        print(f"       {cls}: {count}")

    # Build interaction graph (filtered to known entities)
    print("[INFO] Building interaction graph...")
    interaction_edges = build_interaction_graph(interaction_map, entities)
    print(f"[INFO] Interaction edges: {len(interaction_edges)}")

    # Find kill candidates
    print("[INFO] Searching for kill candidates...")
    kill_candidates = find_kill_candidates(interaction_map, entities)
    print(f"[INFO] Kill candidates: {len(kill_candidates)}")

    # Map turrets and objectives
    print("[INFO] Mapping turrets and objectives...")
    turret_data = map_turrets_and_objectives(entities, interaction_map, is_5v5)

    # Build entity timeline
    print("[INFO] Building entity timeline...")
    timeline = build_entity_timeline(entities)

    # --- Prepare output ---
    if output_dir is None:
        output_dir_path = frame_dir
    else:
        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)

    # 1. entity_map.json
    entity_map = {
        "replay_name": replay_name,
        "total_frames": total_frames,
        "total_entities": len(entities),
        "player_count": len(player_entities),
        "classification_counts": dict(classification_counts),
        "entities": {
            str(eid): entity.to_dict()
            for eid, entity in sorted(entities.items())
        },
    }
    entity_map_path = output_dir_path / "entity_map.json"
    with open(entity_map_path, 'w', encoding='utf-8') as f:
        json.dump(entity_map, f, indent=2, ensure_ascii=False)
    print(f"[OK] Saved: {entity_map_path}")

    # 2. interaction_graph.json
    interaction_graph = {
        "replay_name": replay_name,
        "total_edges": len(interaction_edges),
        "edges": interaction_edges,
    }
    interaction_graph_path = output_dir_path / "interaction_graph.json"
    with open(interaction_graph_path, 'w', encoding='utf-8') as f:
        json.dump(interaction_graph, f, indent=2, ensure_ascii=False)
    print(f"[OK] Saved: {interaction_graph_path}")

    # 3. entity_timeline.json
    timeline_data = {
        "replay_name": replay_name,
        "total_frames": total_frames,
        "entities": timeline,
    }
    timeline_path = output_dir_path / "entity_timeline.json"
    with open(timeline_path, 'w', encoding='utf-8') as f:
        json.dump(timeline_data, f, indent=2, ensure_ascii=False)
    print(f"[OK] Saved: {timeline_path}")

    # 4. entity_network_report.md
    report = generate_report(
        entities, interaction_edges, kill_candidates,
        turret_data, player_entities, total_frames, replay_name,
    )
    report_path = output_dir_path / "entity_network_report.md"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"[OK] Saved: {report_path}")

    # Return summary
    return {
        "replay_name": replay_name,
        "total_frames": total_frames,
        "entities_found": len(entities),
        "player_entities": len(player_entities),
        "classification_counts": dict(classification_counts),
        "interaction_edges": len(interaction_edges),
        "kill_candidates": len(kill_candidates),
        "turrets_found": turret_data["found_turrets"],
        "turrets_destroyed": len(turret_data["destroyed_turrets"]),
        "output_files": {
            "entity_map": str(entity_map_path),
            "interaction_graph": str(interaction_graph_path),
            "entity_timeline": str(timeline_path),
            "report": str(report_path),
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Entity Network Mapper - Discover and map all entities in Vainglory replays"
    )
    parser.add_argument(
        "replay_path",
        help="Path to replay folder or .0.vgr file",
    )
    parser.add_argument(
        "--output-dir", "-o",
        help="Output directory for results (default: same as replay)",
        default=None,
    )
    parser.add_argument(
        "--min-events",
        type=int,
        default=MIN_ENTITY_EVENTS,
        help=f"Minimum events to consider an entity real (default: {MIN_ENTITY_EVENTS})",
    )
    parser.add_argument(
        "--gap-threshold",
        type=int,
        default=DEATH_GAP_FRAMES,
        help=f"Frame gap threshold for death detection (default: {DEATH_GAP_FRAMES})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print summary as JSON to stdout",
    )

    args = parser.parse_args()

    try:
        result = analyze_replay(
            args.replay_path,
            args.output_dir,
            min_events=args.min_events,
            gap_threshold=args.gap_threshold,
        )
        print("\n" + "=" * 60)
        print("ANALYSIS COMPLETE")
        print("=" * 60)
        print(f"Entities found:      {result['entities_found']}")
        print(f"Player entities:     {result['player_entities']}")
        print(f"Interaction edges:   {result['interaction_edges']}")
        print(f"Kill candidates:     {result['kill_candidates']}")
        print(f"Turrets found:       {result['turrets_found']}")
        print(f"Turrets destroyed:   {result['turrets_destroyed']}")
        print()
        print("Output files:")
        for name, path in result["output_files"].items():
            print(f"  {name}: {path}")

        if args.json:
            print("\n" + json.dumps(result, indent=2))

    except FileNotFoundError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Analysis failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
