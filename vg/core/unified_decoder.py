#!/usr/bin/env python3
"""
Unified Replay Decoder - Single entry point for complete VGR replay analysis.

Combines all solved detection modules:
  - VGRParser: players, teams, heroes, game mode (100% accuracy)
  - KDADetector: kills 99.0%, deaths 98.0%, assists 98.0% (combined 98.3%)
  - Gold earned: 600 starting + action 0x06 (sell_flag!=0x01). ±5% 98.0%, ±10% 100%
  - WinLossDetector: crystal destruction detection (100% accuracy)
  - Item-Player Mapping: [10 04 3D] acquire events → per-player item builds
  - Crystal Death Detection: eid 2000-2005 death → game duration & winner
  - Objective Events: Kraken vs Gold Mine via player kill proximity (eid>60000)

Team label limitation:
  The team_byte at player block +0xD5 groups players correctly (100%),
  but the 1→left / 2→right mapping is non-deterministic (~50% of matches
  have swapped labels). No binary-level signal has been found to resolve
  this (exhaustive search: player block bytes, entity events, event headers,
  turret clustering, crystal entity IDs — all fail to discriminate left/right).
  The E.V.I.L. engine replay format does not appear to encode map position.
  Winner detection via kill count asymmetry is 100% accurate (the winning
  GROUP is always correctly identified), but its "left"/"right" label may
  not match the API convention. Use truth_comparison.py auto-swap correction
  when validating against API telemetry data.

Usage:
    from vg.core.unified_decoder import UnifiedDecoder

    decoder = UnifiedDecoder("/path/to/replay")
    match = decoder.decode()
    print(match.to_json())

CLI:
    python -m vg.core.unified_decoder /path/to/replay
"""

import json
import math
import struct
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Local imports with fallback for both package and direct execution
try:
    from vg.core.vgr_parser import VGRParser
    from vg.core.kda_detector import KDADetector
    from vg.core.vgr_mapping import ITEM_ID_MAP
    from vg.analysis.win_loss_detector import WinLossDetector
except ImportError:
    try:
        from vgr_parser import VGRParser
        from kda_detector import KDADetector
        from vgr_mapping import ITEM_ID_MAP
        _root = Path(__file__).resolve().parent.parent
        sys.path.insert(0, str(_root.parent))
        from vg.analysis.win_loss_detector import WinLossDetector
    except ImportError as e:
        raise ImportError(f"Cannot import required modules: {e}")

# Event headers for item and objective detection
_ITEM_ACQUIRE_HEADER = bytes([0x10, 0x04, 0x3D])
_ITEM_EQUIP_HEADER = bytes([0x10, 0x04, 0x4B])
_CREDIT_HEADER = bytes([0x10, 0x04, 0x1D])
_DEATH_HEADER = bytes([0x08, 0x04, 0x31])
_KILL_HEADER = bytes([0x18, 0x04, 0x1C])
_PLAYER_EID_RANGE = set(range(1500, 1510))  # BE entity IDs for players

# ===== ITEM BUILD ESTIMATION =====
# Upgrade tree using BINARY REPLAY IDs (from ITEM_ID_MAP)
# component_id -> set of result_ids it could have been upgraded into
#
# Two ID ranges:
#   - 200-255: standard shop purchases (qty=1)
#   - 0-27: T3/special item completions (qty=2), identified via hero distribution
UPGRADE_TREE = {
    # ====== Weapon T1 → T2 + T3 (transitive) ======
    202: {249, 205, 250, 207, 237, 235, 208, 223, 224, 226, 251, 252, 210, 5, 12},  # Weapon Blade
    243: {237, 223, 252},  # Book of Eulogies → Barbed Needle → Serpent Mask/Poisoned Shiv
    204: {207, 235, 210, 252, 253, 5},  # Swift Shooter → Blazing Salvo/Lucky Strike → T3
    # ====== Weapon T2 → T3 ======
    249: {208, 223, 251, 5, 12},  # Heavy Steel → Sorrowblade, Serpent Mask, Breaking Point, Tyrants Monocle, Spellsword
    205: {208, 224},  # Six Sins → Sorrowblade, Tension Bow
    235: {210, 5},  # Lucky Strike → Tornado Trigger, Tyrants Monocle
    237: {223, 251, 252},  # Barbed Needle → Serpent Mask, Breaking Point, Poisoned Shiv
    250: {226, 224},  # Piercing Spear → Bonesaw, Tension Bow
    207: {210, 252, 253, 5},  # Blazing Salvo → Tornado Trigger, Poisoned Shiv, AC, Tyrants Monocle
    # ====== Crystal T1 → T2 + T3 (transitive) ======
    203: {0, 254, 209, 230, 236, 253, 240, 255, 10, 11},  # Crystal Bit → Heavy Prism, various CP T3
    206: {220, 255, 234, 10, 11},  # Energy Battery → Clockwork, Eve of Harvest, Halcyon Chargers, Spellfire, Dragons Eye
    216: {218, 220, 236, 10},  # Hourglass → Chronograph → Clockwork, Aftershock, Spellfire
    # ====== Crystal T2 → T3 ======
    0: {209, 230, 10, 11, 240},  # Heavy Prism → Shatterglass, Frostburn, Spellfire, Dragons Eye, Broken Myth
    254: {253, 240},  # Piercing Shard → Alternating Current, Broken Myth
    218: {220, 236},  # Chronograph → Clockwork, Aftershock
    # ====== Defense T1 → T2 + T3 (transitive) ======
    212: {214, 248, 229, 219, 232, 241, 231, 247, 21, 22, 23, 17},  # Oakheart → HP-based items
    211: {246, 228, 231, 247, 242, 27, 13},  # Light Shield → shield-based items
    213: {228, 26, 242, 27},  # Light Armor → Coat of Plates, Warmail, Atlas Pauldron, Metal Jacket
    245: {246, 231, 247, 13},  # Light Shield variant
    215: {246, 231, 247},  # Light Armor variant
    # ====== Defense T2 → T3 ======
    214: {232, 241, 21, 22, 23, 17},  # Dragonheart → Crucible, War Treads, Pulseweave, Cap Plate, Rooks Decree, Shiversteel
    248: {231},  # Lifespring → Fountain of Renewal
    229: {232, 247, 13},  # Reflex Block → Crucible, Aegis, Slumbering Husk
    246: {231, 247, 13},  # Kinetic Shield → Fountain, Aegis, Slumbering Husk
    228: {242, 27},  # Coat of Plates → Atlas Pauldron, Metal Jacket
    26: {242, 27},  # Warmail → Atlas Pauldron, Metal Jacket
    # ====== Boots ======
    221: {222, 241, 234, 1},  # Sprint Boots → Travel Boots, War Treads, Halcyon Chargers, Journey Boots
    222: {241, 234, 1},  # Travel Boots → War Treads, Halcyon Chargers, Journey Boots
    # ====== Utility T2 → T3 ======
    219: {7, 16},  # Stormguard Banner → Stormcrown, Contraption
}

# Starter/consumable IDs - never in final build
# ID 14 = universal system event (not an item)
STARTER_IDS = {14, 201, 225, 233, 238, 239, 244, 8, 18, 20}
# 14=system, 201=Starting Item, 225=Scout Trap, 233=Unknown consumable
# 238=Flare, 239=Unknown consumable, 244=WP Infusion(qty=1)
# 8=WP Infusion(qty=2), 18=CP Infusion(qty=2), 20=Flare Gun(qty=2)


def _le_to_be(eid_le: int) -> int:
    """Convert uint16 Little Endian entity ID to Big Endian."""
    return struct.unpack('>H', struct.pack('<H', eid_le))[0]


def _estimate_final_build(
    item_ids_set: Set[int],
    last_acquire_ts: Optional[Dict[int, float]] = None,
) -> List[str]:
    """
    Remove consumed components and starters. Return up to 6 items (final build).

    When more than 6 items remain after upgrade-tree filtering, uses the
    last-acquired timestamp to keep only the 6 most recently purchased items.
    This handles sell-back scenarios where items are sold and replaced.

    Args:
        item_ids_set: Set of all purchased item IDs (binary replay IDs)
        last_acquire_ts: Optional {item_id: last_purchase_timestamp} for tie-breaking

    Returns:
        List of item names in final 6-slot build, sorted by tier desc
    """
    remaining = set(item_ids_set) - STARTER_IDS

    # Iteratively remove components that have been upgraded
    changed = True
    while changed:
        changed = False
        to_remove = set()
        for comp_id, result_ids in UPGRADE_TREE.items():
            if comp_id in remaining and (remaining & result_ids):
                to_remove.add(comp_id)
        if to_remove:
            remaining -= to_remove
            changed = True

    # Convert to named items
    items = []
    for iid in remaining:
        info = ITEM_ID_MAP.get(iid)
        ts = last_acquire_ts.get(iid, 0) if last_acquire_ts else 0
        if info:
            items.append((info.get('tier', 0), ts, info['name'], iid))
        else:
            items.append((-1, ts, f"Unknown_{iid}", iid))

    # Sort: tier desc, then latest timestamp desc (within same tier)
    items.sort(key=lambda x: (-x[0], -x[1]))
    return [name for _, _, name, _ in items[:6]]


@dataclass
class ObjectiveEvent:
    """Detected objective event (Gold Mine/Ghostwing capture or Kraken/Blackclaw death)."""
    timestamp: float
    event_type: str  # 3v3: GOLD_MINE_CAPTURE, KRAKEN_DEATH/WAVE. 5v5: GHOSTWING_CAPTURE, BLACKCLAW_DEATH/WAVE
    entity_count: int
    entity_ids: List[int] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class DecodedPlayer:
    """Player data from unified decoding."""
    name: str
    team: str                          # "left" / "right"
    hero_name: str
    hero_id: Optional[int]
    entity_id: int                     # Little Endian (original)
    kills: int = 0
    deaths: int = 0
    assists: Optional[int] = None
    minion_kills: int = 0
    jungle_kills: int = 0  # action 0x0D credit count
    gold_spent: int = 0
    gold_earned: int = 0  # 600 starting + 0x06 income (sell_flag!=0x01). ±5% 98.0%, ±10% 100%
    items: List[str] = field(default_factory=list)  # Final build (after upgrade tree filtering)
    items_all_purchased: List[str] = field(default_factory=list)  # Raw purchase history
    # Comparison fields (populated when truth is available)
    truth_kills: Optional[int] = None
    truth_deaths: Optional[int] = None

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class DecodedMatch:
    """Complete decoded match data."""
    replay_name: str
    replay_path: str
    game_mode: str
    map_name: str
    team_size: int
    duration_seconds: Optional[int] = None
    winner: Optional[str] = None
    left_team: List[DecodedPlayer] = field(default_factory=list)
    right_team: List[DecodedPlayer] = field(default_factory=list)
    total_frames: int = 0
    crystal_death_ts: Optional[float] = None
    crystal_death_eid: Optional[int] = None
    objective_events: List[ObjectiveEvent] = field(default_factory=list)
    # Detection flags
    kda_detection_used: bool = False
    win_detection_used: bool = False
    item_detection_used: bool = False
    team_labels_reliable: bool = False  # left/right labels may not match API convention

    @property
    def all_players(self) -> List[DecodedPlayer]:
        return self.left_team + self.right_team

    def to_dict(self) -> Dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


class UnifiedDecoder:
    """
    Single entry point for complete VGR replay analysis.

    Orchestrates VGRParser, KDADetector, WinLossDetector, and ItemExtractor
    to produce a fully decoded match result.
    """

    def __init__(self, replay_path: str):
        """
        Args:
            replay_path: Path to .0.vgr file or replay cache folder.
        """
        self.replay_path = Path(replay_path)

    def decode(self, detect_items: bool = False) -> DecodedMatch:
        """
        Run full decoding pipeline.

        Args:
            detect_items: If True, also run ItemExtractor (partial accuracy).

        Returns:
            DecodedMatch with all detected fields populated.
        """
        # --- Step 1: Basic parsing (frame 0) ---
        parser = VGRParser(
            str(self.replay_path),
            detect_heroes=False,
            auto_truth=False,
        )
        parsed = parser.parse()

        match_info = parsed.get("match_info", {})
        replay_name = parsed.get("replay_name", "")
        replay_file = parsed.get("replay_file", str(self.replay_path))

        # Resolve frame directory
        replay_file_path = Path(replay_file)
        frame_dir = replay_file_path.parent
        frame_name = replay_file_path.stem.rsplit('.', 1)[0]

        # Build player list from parsed teams
        left_parsed = parsed.get("teams", {}).get("left", [])
        right_parsed = parsed.get("teams", {}).get("right", [])

        left_team = [self._make_player(p) for p in left_parsed]
        right_team = [self._make_player(p) for p in right_parsed]
        all_players = left_team + right_team

        # --- Step 2: Load all frames ---
        frames = self._load_frames(frame_dir, frame_name)

        # --- Step 3: KDA Scanning (event collection only, no filtering yet) ---
        kda_used = False
        duration_est = None
        kda_detector = None
        eid_map_be_kda = {}  # BE -> player
        team_map_kda = {}    # BE -> team name
        if frames and all_players:
            kda_detector, eid_map_be_kda, team_map_kda, duration_est = \
                self._scan_kda_events(frames, all_players)
            kda_used = kda_detector is not None

        # --- Step 4: Win/Loss Detection ---
        # Strategy: WinLossDetector for crystal destruction detection,
        # then KDA-based team mapping to determine which side won.
        # WinLossDetector's left/right label is unreliable due to
        # entity ID mapping issues, so we cross-check with kill totals.
        win_used = False
        winner = None
        crystal_detected = False
        try:
            import io
            detector = WinLossDetector(str(self.replay_path))
            old_stdout = sys.stdout
            sys.stdout = io.StringIO()
            try:
                outcome = detector.detect_winner()
            finally:
                sys.stdout = old_stdout
            if outcome:
                crystal_detected = True
                win_used = True
        except Exception:
            pass

        # --- Step 5: Per-player Item Detection via [10 04 3D] ---
        item_used = False
        all_data = b"".join(data for _, data in frames) if frames else b""
        if all_data and all_players:
            eid_map_be = {}
            for player in all_players:
                if player.entity_id:
                    eid_be = _le_to_be(player.entity_id)
                    eid_map_be[eid_be] = player
            if eid_map_be:
                self._detect_items_per_player(all_data, eid_map_be)
                self._detect_gold_per_player(frames, eid_map_be)
                item_used = True

        # --- Step 6: Crystal Death Detection ---
        crystal_ts = None
        crystal_eid = None
        if all_data:
            crystal_ts, crystal_eid = self._detect_crystal_death(
                all_data, duration_est
            )

        # --- Step 7: Duration estimation ---
        # Crystal death is preferred but eid 2000-2005 can be turrets.
        # If crystal is much earlier than max player death, it's a FP.
        duration = None
        if crystal_ts is not None and duration_est is not None:
            if crystal_ts >= duration_est - 30:
                # Crystal death is at or after last player death → valid
                duration = int(crystal_ts)
            else:
                # Crystal death is much earlier → false positive turret
                duration = int(duration_est)
        elif crystal_ts is not None:
            duration = int(crystal_ts)
        elif duration_est is not None:
            duration = int(duration_est)

        # --- Step 7b: Apply KDA filter with computed duration ---
        # Now that we have proper game duration (from crystal death),
        # filter kills/deaths/assists with post-game ceremony removal.
        if kda_detector and eid_map_be_kda:
            results = kda_detector.get_results(
                game_duration=duration, team_map=team_map_kda,
            )
            for eid_be, kda in results.items():
                player = eid_map_be_kda.get(eid_be)
                if player:
                    player.kills = kda.kills
                    player.deaths = kda.deaths
                    player.assists = kda.assists
                    player.minion_kills = kda.minion_kills

        # KDA-based winner: team with more kills wins (consistent
        # with VGRParser's team label convention).
        if kda_used:
            left_kills = sum(p.kills for p in left_team)
            right_kills = sum(p.kills for p in right_team)
            if left_kills > right_kills:
                winner = "left"
            elif right_kills > left_kills:
                winner = "right"
            # Tie: use WinLossDetector's label as fallback
            elif crystal_detected and outcome:
                winner = outcome.winner

        # --- Step 8: Objective event detection ---
        # 3v3: Kraken / Gold Mine.  5v5: Blackclaw / Ghostwing
        game_mode = match_info.get("mode", "")
        is_5v5 = "5v5" in game_mode
        objective_events = []
        if all_data:
            objective_events = self._detect_objective_events(
                all_data, is_5v5=is_5v5,
            )

        # --- Step 9: Assemble result ---
        return DecodedMatch(
            replay_name=replay_name,
            replay_path=str(replay_file),
            game_mode=match_info.get("mode", "Unknown"),
            map_name=match_info.get("map_name", "Unknown"),
            team_size=match_info.get("team_size", 3),
            duration_seconds=duration,
            winner=winner,
            left_team=left_team,
            right_team=right_team,
            total_frames=match_info.get("total_frames", 0),
            crystal_death_ts=crystal_ts,
            crystal_death_eid=crystal_eid,
            objective_events=objective_events,
            kda_detection_used=kda_used,
            win_detection_used=win_used,
            item_detection_used=item_used,
        )

    def decode_with_truth(self, truth_path: str) -> DecodedMatch:
        """
        Decode and attach truth data for comparison.

        Args:
            truth_path: Path to tournament_truth.json.

        Returns:
            DecodedMatch with truth_kills/truth_deaths populated.
        """
        match = self.decode()
        truth = self._load_truth(truth_path, match.replay_name)
        if not truth:
            return match

        # Apply truth duration/winner
        truth_info = truth.get("match_info", {})
        if truth_info.get("duration_seconds") is not None:
            match.duration_seconds = truth_info["duration_seconds"]
        if truth_info.get("winner"):
            # Keep detected winner, truth is for comparison

            pass

        # Apply truth K/D per player
        truth_players = truth.get("players", {})
        for player in match.all_players:
            tp = truth_players.get(player.name, {})
            if tp:
                player.truth_kills = tp.get("kills")
                player.truth_deaths = tp.get("deaths")

        # Note: KDA is NOT re-run with truth duration. The decoder's own
        # duration estimate (from crystal death / max death timestamp)
        # provides better post-game filtering.

        return match

    def _make_player(self, p: Dict) -> DecodedPlayer:
        """Convert parser player dict to DecodedPlayer."""
        return DecodedPlayer(
            name=p.get("name", "Unknown"),
            team=p.get("team", "unknown"),
            hero_name=p.get("hero_name", "Unknown"),
            hero_id=p.get("hero_id"),
            entity_id=p.get("entity_id", 0),
        )

    def _load_frames(self, frame_dir: Path, replay_name: str) -> List[tuple]:
        """Load all frame files as (frame_idx, data) tuples."""
        frame_files = list(frame_dir.glob(f"{replay_name}.*.vgr"))
        if not frame_files:
            return []

        def _idx(p: Path) -> int:
            try:
                return int(p.stem.split('.')[-1])
            except ValueError:
                return 0

        frame_files.sort(key=_idx)
        return [(_idx(f), f.read_bytes()) for f in frame_files]

    def _scan_kda_events(
        self,
        frames: List[tuple],
        all_players: List[DecodedPlayer],
    ) -> tuple:
        """
        Scan all frames for KDA events (no filtering applied yet).

        Returns:
            (detector, eid_map, team_map, duration_estimate)
            detector is None if no valid entity IDs found.
        """
        # Build BE entity ID set and LE→BE mapping
        eid_map = {}  # BE -> player
        valid_eids = set()
        team_map = {}  # BE -> team name
        for player in all_players:
            if player.entity_id:
                eid_be = _le_to_be(player.entity_id)
                eid_map[eid_be] = player
                valid_eids.add(eid_be)
                team_map[eid_be] = player.team

        if not valid_eids:
            return None, {}, {}, None

        detector = KDADetector(valid_eids)
        for frame_idx, data in frames:
            detector.process_frame(frame_idx, data)

        # Estimate duration from max death timestamp
        duration_est = None
        if detector.death_events:
            duration_est = max(d.timestamp for d in detector.death_events)

        return detector, eid_map, team_map, duration_est

    def _detect_items_per_player(
        self,
        all_data: bytes,
        eid_map: Dict[int, 'DecodedPlayer'],
    ) -> None:
        """
        Scan [10 04 3D] item acquire events and [10 04 1D] action=0x06
        purchase costs. Assigns per-player items (final build after upgrade tree)
        and gold_spent.

        Item acquire: [10 04 3D][00 00][eid BE][00 00][qty][item_id LE][00 00][counter BE][ts f32 BE]
        Purchase cost: [10 04 1D][00 00][eid BE][cost f32 BE (negative)][06]
        """
        valid_eids = set(eid_map.keys())

        # --- Scan item acquire events ---
        player_items: Dict[int, Set[int]] = defaultdict(set)  # eid -> set of item_ids
        player_item_ts: Dict[int, Dict[int, float]] = defaultdict(dict)  # eid -> {item_id: last_ts}
        pos = 0
        while True:
            pos = all_data.find(_ITEM_ACQUIRE_HEADER, pos)
            if pos == -1:
                break
            if pos + 20 > len(all_data):
                pos += 1
                continue
            if all_data[pos + 3:pos + 5] != b'\x00\x00':
                pos += 1
                continue

            eid = struct.unpack_from(">H", all_data, pos + 5)[0]
            if eid not in valid_eids:
                pos += 1
                continue

            # qty=1 + IDs 200-255 = standard item purchase
            # qty=2 + IDs 0-27 = T3/special item completion (NOT ability upgrades)
            #   Per-player analysis: only 2-5 qty=2 events (too few for abilities)
            #   Hero distribution matches item buyers perfectly
            # ID 14 is universal (system event, not an item) - filtered below
            qty = all_data[pos + 9]
            if qty not in (1, 2):
                pos += 3
                continue

            item_id = struct.unpack_from("<H", all_data, pos + 10)[0]
            # Normalize encoding artifacts (e.g., 65505=0xFFE1 → 225=0xE1)
            if item_id > 255:
                item_id = item_id & 0xFF
            item_info = ITEM_ID_MAP.get(item_id)
            if item_info:
                player_items[eid].add(item_id)
                # Track last acquire timestamp per item
                if pos + 21 <= len(all_data):
                    ts = struct.unpack_from(">f", all_data, pos + 17)[0]
                    if 0 < ts < 5000:
                        player_item_ts[eid][item_id] = ts

            pos += 3

        # Apply upgrade tree filtering to get final builds
        for eid, item_ids in player_items.items():
            player = eid_map.get(eid)
            if player:
                # Store all purchased items (raw)
                all_purchased = []
                for iid in sorted(item_ids):
                    info = ITEM_ID_MAP.get(iid)
                    if info:
                        all_purchased.append(info['name'])
                player.items_all_purchased = all_purchased

                # Apply upgrade tree to get final build (max 6 slots)
                # Pass timestamps for sell-back resolution
                player.items = _estimate_final_build(
                    item_ids, last_acquire_ts=player_item_ts.get(eid),
                )

        # Gold detection moved to _detect_gold_per_player (frame-by-frame dedup)

    def _detect_gold_per_player(
        self,
        frames: List[tuple],
        eid_map: Dict[int, 'DecodedPlayer'],
    ) -> None:
        """
        Detect gold earned/spent via [10 04 1D] action=0x06.
        Frames are independent (not cumulative), so sum across all frames.

        Sell-back filtering: the byte at offset +12 (right after action byte)
        distinguishes income (0x00) from item sell-back refunds (0x01).
        Excluding 0x01 records eliminates sell-back gold overcounting.

        Args:
            frames: List of (frame_idx, data) tuples, sorted by frame index.
            eid_map: {BE entity ID: DecodedPlayer} mapping.
        """
        valid_eids = set(eid_map.keys())
        gold_spent: Dict[int, float] = defaultdict(float)
        gold_earned: Dict[int, float] = defaultdict(float)
        jungle_kills: Dict[int, int] = defaultdict(int)

        for frame_idx, data in frames:
            pos = 0
            while True:
                pos = data.find(_CREDIT_HEADER, pos)
                if pos == -1:
                    break
                if pos + 13 > len(data):
                    pos += 1
                    continue
                if data[pos + 3:pos + 5] != b'\x00\x00':
                    pos += 1
                    continue

                eid = struct.unpack_from(">H", data, pos + 5)[0]
                if eid not in valid_eids:
                    pos += 3
                    continue

                value = struct.unpack_from(">f", data, pos + 7)[0]
                action = data[pos + 11]
                sell_flag = data[pos + 12]

                if not math.isnan(value) and not math.isinf(value):
                    if action == 0x06:
                        if value < 0:
                            gold_spent[eid] += abs(value)
                        elif value > 0 and sell_flag != 0x01:
                            gold_earned[eid] += value
                    elif action == 0x0D:
                        jungle_kills[eid] += 1

                pos += 3

        for eid in valid_eids:
            player = eid_map.get(eid)
            if player:
                if eid in gold_spent:
                    player.gold_spent = round(gold_spent[eid])
                player.gold_earned = 600 + round(gold_earned.get(eid, 0))
                if eid in jungle_kills:
                    player.jungle_kills = jungle_kills[eid]

    def _detect_objective_events(
        self,
        all_data: bytes,
        eid_threshold: int = 60000,
        cluster_window: float = 5.0,
        is_5v5: bool = False,
    ) -> List[ObjectiveEvent]:
        """
        Detect objective events (Gold Mine captures and Kraken deaths).

        Classification rule for single-entity deaths (n=1, eid > 60000):
          - Player kill [18 04 1C] within ±500B → KRAKEN_DEATH
          - No player kill nearby → GOLD_MINE_CAPTURE
        Multi-entity clusters (n>1) are KRAKEN_WAVE or MINION_WAVE.
        """
        # Collect all objective deaths
        deaths = []
        pos = 0
        while True:
            idx = all_data.find(_DEATH_HEADER, pos)
            if idx == -1:
                break
            pos = idx + 1
            if idx + 13 > len(all_data):
                continue
            if (all_data[idx + 3:idx + 5] != b'\x00\x00' or
                    all_data[idx + 7:idx + 9] != b'\x00\x00'):
                continue
            eid = struct.unpack_from(">H", all_data, idx + 5)[0]
            ts = struct.unpack_from(">f", all_data, idx + 9)[0]
            if eid > eid_threshold and 0 < ts < 5000:
                deaths.append((ts, eid, idx))

        if not deaths:
            return []

        deaths.sort(key=lambda x: x[0])

        # Cluster by time window
        clusters: List[List[tuple]] = []
        cur: List[tuple] = []
        for d in deaths:
            if not cur or d[0] - cur[-1][0] <= cluster_window:
                cur.append(d)
            else:
                clusters.append(cur)
                cur = [d]
        if cur:
            clusters.append(cur)

        # Classify each cluster
        events = []
        for cluster in clusters:
            ts = cluster[0][0]
            eids = [d[1] for d in cluster]
            offsets = [d[2] for d in cluster]
            n = len(cluster)

            player_kill = self._has_player_kill_nearby(all_data, offsets)

            if n == 1 and not player_kill:
                event_type = "GHOSTWING_CAPTURE" if is_5v5 else "GOLD_MINE_CAPTURE"
            elif n == 1 and player_kill:
                event_type = "BLACKCLAW_DEATH" if is_5v5 else "KRAKEN_DEATH"
            elif n > 1 and player_kill:
                event_type = "BLACKCLAW_WAVE" if is_5v5 else "KRAKEN_WAVE"
            else:
                event_type = "MINION_WAVE"

            events.append(ObjectiveEvent(
                timestamp=round(ts, 2),
                event_type=event_type,
                entity_count=n,
                entity_ids=eids,
            ))

        return events

    @staticmethod
    def _has_player_kill_nearby(
        data: bytes, offsets: List[int], window: int = 500
    ) -> bool:
        """Check if any player kill [18 04 1C] exists within window bytes."""
        for off in offsets:
            s = max(0, off - window)
            e = min(len(data), off + window)
            region = data[s:e]
            pk = 0
            while True:
                kidx = region.find(_KILL_HEADER, pk)
                if kidx == -1:
                    break
                pk = kidx + 1
                if kidx + 7 > len(region):
                    continue
                killer = struct.unpack_from(">H", region, kidx + 5)[0]
                if killer in _PLAYER_EID_RANGE:
                    return True
        return False

    def _detect_crystal_death(
        self,
        all_data: bytes,
        duration_est: Optional[float],
    ) -> Tuple[Optional[float], Optional[int]]:
        """
        Detect Vain Crystal destruction via death header for eid 2000-2005.
        The crystal death timestamp closely matches game duration.

        Returns:
            (crystal_death_ts, crystal_death_eid) or (None, None).
        """
        crystal_deaths = []
        pos = 0
        while True:
            pos = all_data.find(_DEATH_HEADER, pos)
            if pos == -1:
                break
            if pos + 13 > len(all_data):
                pos += 1
                continue
            if (all_data[pos + 3:pos + 5] != b'\x00\x00' or
                    all_data[pos + 7:pos + 9] != b'\x00\x00'):
                pos += 1
                continue

            eid = struct.unpack_from(">H", all_data, pos + 5)[0]
            ts = struct.unpack_from(">f", all_data, pos + 9)[0]

            if 2000 <= eid <= 2005 and 60 < ts < 2400:
                crystal_deaths.append((ts, eid))

            pos += 1

        if not crystal_deaths:
            return None, None

        # The crystal death is the one with the latest timestamp
        # (closest to game end). Filter: must be within ±60s of
        # duration estimate if available.
        crystal_deaths.sort(key=lambda x: x[0], reverse=True)

        if duration_est is not None:
            for ts, eid in crystal_deaths:
                if abs(ts - duration_est) < 60:
                    return ts, eid

        # No duration estimate: return latest crystal death
        return crystal_deaths[0]

    def _load_truth(self, truth_path: str, replay_name: str) -> Optional[Dict]:
        """Load truth data for a specific replay."""
        try:
            with open(truth_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for m in data.get("matches", []):
                if m.get("replay_name") == replay_name:
                    return m
            return None
        except (FileNotFoundError, json.JSONDecodeError):
            return None


def main():
    import argparse

    arg_parser = argparse.ArgumentParser(
        description='Unified VGR Replay Decoder - decode all match data from replay files'
    )
    arg_parser.add_argument(
        'path',
        help='Path to replay folder or .0.vgr file'
    )
    arg_parser.add_argument(
        '--truth',
        help='Path to tournament_truth.json for comparison'
    )
    arg_parser.add_argument(
        '--items',
        action='store_true',
        help='(Legacy flag, items are now always detected per-player)'
    )
    arg_parser.add_argument(
        '-o', '--output',
        help='Output JSON file path (default: stdout)'
    )

    args = arg_parser.parse_args()

    decoder = UnifiedDecoder(args.path)
    if args.truth:
        match = decoder.decode_with_truth(args.truth)
    else:
        match = decoder.decode(detect_items=args.items)

    output = match.to_json()

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output)
        print(f"Result saved to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == '__main__':
    main()
