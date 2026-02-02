#!/usr/bin/env python3
"""
VGR Replay Parser - Vainglory Replay Data Extractor
Extracts player names, UUIDs, game modes, and match information from .vgr replay files.
"""

import os
import re
import json
import struct
import argparse
import difflib
from collections import Counter
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Any, Optional, Tuple

# Import mapping module
try:
    from vgr_mapping import VGRMapping, HERO_ID_MAP
    MAPPING_AVAILABLE = True
except ImportError:
    MAPPING_AVAILABLE = False

try:
    from vgr_truth import load_truth_data
    TRUTH_AVAILABLE = True
except ImportError:
    TRUTH_AVAILABLE = False


@dataclass
class PlayerData:
    """Player information extracted from replay"""
    name: str
    uuid: Optional[str] = None
    team: str = "unknown"  # "left" or "right"
    team_id: Optional[int] = None
    position: int = 0      # Player order in replay
    entity_id: Optional[int] = None
    hero_id: Optional[int] = None
    hero_name: Optional[str] = "Unknown"
    hero_name_ko: Optional[str] = None
    skin_id: Optional[int] = None
    # Stats
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    minion_kills: Optional[int] = 0
    gold: int = 0
    bounty: Optional[int] = None
    items: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass 
class MatchInfo:
    """Match metadata extracted from replay"""
    mode: str
    mode_friendly: str
    map_name: str
    team_size: int
    total_frames: int
    duration_seconds: Optional[int] = None
    winner: Optional[str] = None
    score_left: Optional[int] = None
    score_right: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class VGRParser:
    """Parser for Vainglory replay files (.vgr)"""
    
    # Player block marker in binary
    PLAYER_BLOCK_MARKER = bytes([0xDA, 0x03, 0xEE])
    PLAYER_BLOCK_MARKER_ALT = bytes([0xE0, 0x03, 0xEE])
    
    # Known game mode patterns
    GAME_MODE_PATTERNS = [
        'GameMode_HF_Ranked',      # 3v3 Halcyon Fold Ranked
        'GameMode_HF_Casual',      # 3v3 Halcyon Fold Casual
        'GameMode_5v5_Ranked',     # 5v5 Ranked
        'GameMode_5v5_Casual',     # 5v5 Casual
        'GameMode_Blitz',          # Blitz
        'GameMode_ARAL',           # ARAL (All Random All Lane)
        'GameMode_BR',             # Battle Royale
    ]
    
    # UUID pattern (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)
    UUID_PATTERN = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.IGNORECASE)
    
    # Player name pattern (alphanumeric with underscores, 3-20 chars)
    PLAYER_NAME_PATTERN = re.compile(r'[A-Za-z0-9_]{3,20}')
    
    def __init__(
        self,
        replay_path: str,
        detect_heroes: bool = False,
        debug_events: bool = False,
        truth_path: Optional[str] = None,
        auto_truth: bool = True,
    ):
        """
        Initialize parser with path to replay folder or .0.vgr file.
        
        Args:
            replay_path: Path to replay cache folder or specific .0.vgr file
        """
        self.replay_path = Path(replay_path)
        self.data: Dict[str, Any] = {}
        self.detect_heroes = detect_heroes
        self.debug_events = debug_events
        self.truth_path = truth_path
        self.auto_truth = auto_truth
        
    def _find_first_frame(self) -> Optional[Path]:
        """Find the .0.vgr file (first frame with metadata)"""
        if self.replay_path.is_file() and str(self.replay_path).endswith('.0.vgr'):
            return self.replay_path
            
        # Search for .0.vgr file in directory
        if self.replay_path.is_dir():
            for file in self.replay_path.rglob('*.0.vgr'):
                return file
        return None

    def _team_label_from_id(self, team_id: Optional[int]) -> str:
        """Map team byte to label."""
        if team_id == 1:
            return "left"
        if team_id == 2:
            return "right"
        return "unknown"
    
    def _extract_strings(self, data: bytes) -> List[str]:
        """Extract readable ASCII strings from binary data"""
        text = data.decode('ascii', errors='replace')
        text = re.sub(r'[^\x20-\x7E]', ' ', text)
        matches = self.PLAYER_NAME_PATTERN.findall(text)
        return list(dict.fromkeys(matches))  # Remove duplicates, preserve order
    
    def _find_game_mode(self, strings: List[str]) -> Optional[str]:
        """Find game mode from extracted strings"""
        for s in strings:
            for mode in self.GAME_MODE_PATTERNS:
                if mode in s or s in mode:
                    return mode
        # Check for partial matches
        for s in strings:
            if s.startswith('GameMode_'):
                return s
        return None
    
    def _extract_uuids(self, data: bytes) -> List[str]:
        """Extract UUIDs from binary data"""
        text = data.decode('ascii', errors='replace')
        return list(dict.fromkeys(self.UUID_PATTERN.findall(text)))
    
    def _filter_player_names(self, strings: List[str], uuids: List[str]) -> List[str]:
        """Filter likely player names from extracted strings"""
        # Exclude known non-player strings
        exclude_patterns = [
            'GameMode', 'Guest', 'cache', 'replay', 'Manifest',
            'Hero', 'Skin', 'Item', 'Ability', 'Effect'
        ]
        
        # UUID parts to exclude
        uuid_parts = set()
        for uuid in uuids:
            uuid_parts.update(uuid.split('-'))
        
        players = []
        for s in strings:
            # Skip too short or too long
            if len(s) < 4 or len(s) > 20:
                continue
            # Skip known patterns
            if any(p.lower() in s.lower() for p in exclude_patterns):
                continue
            # Skip UUID parts
            if s.lower() in uuid_parts:
                continue
            # Skip if all digits
            if s.isdigit():
                continue
            # Skip common file/code patterns
            if s.startswith('0x') or s.endswith('.vgr'):
                continue
            players.append(s)
        
        return players[:10]  # Return at most 10 (5v5 max)
    
    def _get_team_size(self, game_mode: Optional[str]) -> int:
        """Get team size based on game mode"""
        if not game_mode:
            return 3  # Default to 3v3
        if '5v5' in game_mode:
            return 5
        return 3
    
    def _get_map_name(self, game_mode: Optional[str]) -> str:
        """Get map name based on game mode"""
        if not game_mode:
            return "Unknown"
        if '5v5' in game_mode:
            return "Sovereign Rise"
        if 'HF' in game_mode:
            return "Halcyon Fold"
        if 'Blitz' in game_mode or 'ARAL' in game_mode:
            return "Halcyon Fold"
        return "Unknown"
    
    def _detect_heroes(self, data: bytes, team_size: int = 3) -> List[Dict]:
        """
        Detect participating heroes based on event frequency analysis.
        Heroes that are actively played generate more events with their ID pattern.
        """
        # Hero ID to name mapping (from asset analysis)
        HERO_MAP = {
            9: ('SAW', '쏘우'), 10: ('Ringo', '링고'), 11: ('Taka', '타카'), 12: ('Krul', '크럴'),
            13: ('Skaarf', '스카프'), 14: ('Celeste', '셀레스트'), 15: ('Vox', '복스'), 16: ('Catherine', '캐서린'),
            17: ('Ardan', '아단'), 19: ('Glaive', '글레이브'), 20: ('Joule', '쥴'), 21: ('Koshka', '코쉬카'),
            23: ('Petal', '페탈'), 24: ('Adagio', '아다지오'), 25: ('Rona', '로나'), 27: ('Fortress', '포트리스'),
            28: ('Reim', '라임'), 29: ('Phinn', '핀'), 30: ('Blackfeather', '흑깃'), 31: ('Skye', '스카이'),
            36: ('Kestrel', '케스트럴'), 37: ('Alpha', '알파'), 38: ('Lance', '랜스'), 39: ('Ozo', '오조'),
            40: ('Lyra', '라이라'), 41: ('Samuel', '사무엘'), 42: ('Baron', '바론'), 44: ('Gwen', '그웬'),
            45: ('Flicker', '플리커'), 46: ('Idris', '이드리스'), 47: ('Grumpjaw', '사슬니'), 48: ('Baptiste', '바티스트'),
            54: ('Grace', '그레이스'), 55: ('Reza', '레자'), 58: ('Churnwalker', '어둠추적자'), 59: ('Lorelai', '로렐라이'),
            60: ('Tony', '토니'), 61: ('Varya', '바리야'), 62: ('Malene', '말렌'), 63: ('Kensei', '켄세이'),
            64: ('Kinetic', '키네틱'), 65: ('San Feng', '삼봉'), 66: ('Silvernail', '실버네일'), 67: ('Yates', '예이츠'),
            68: ('Inara', '이나라'), 69: ('Magnus', '마그누스'), 70: ('Caine', '케인'), 71: ('Leo', '레오'),
            72: ('Amael', '아마엘'),
        }
        
        # Count event patterns for each hero ID
        hero_counts = {}
        for hero_id, (name, name_ko) in HERO_MAP.items():
            pattern = bytes([hero_id, 0, 0, 0])
            count = data.count(pattern)
            if count > 15:  # Threshold to filter noise
                # Count death events (action type 0x80)
                death_pattern = bytes([hero_id, 0, 0, 0, 0x80])
                death_count = data.count(death_pattern)
                
                hero_counts[hero_id] = {
                    'id': hero_id,
                    'name': name,
                    'name_ko': name_ko,
                    'event_count': count,
                    'deaths': death_count  # NEW: estimated deaths
                }
        
        # Return top heroes (team_size * 2 for both teams)
        # Sort by event count first to get candidates
        sorted_by_count = sorted(hero_counts.values(), key=lambda x: -x['event_count'])
        top_candidates = sorted_by_count[:team_size * 2]
        
        # Then sort candidates by FIRST APPEARANCE offset to match player order
        # We need to find the first occurrence of each ID
        for hero in top_candidates:
            pattern = bytes([hero['id'], 0, 0, 0])
            hero['first_offset'] = data.find(pattern)
            
        # Sort by offset (ascending)
        final_heroes = sorted(top_candidates, key=lambda x: x['first_offset'])
        
        return final_heroes

    def _link_heroes_to_players(self, left_team, right_team, detected_heroes, data):
        """
        Link detected heroes to players based on sequential order.
        Assumption: Player blocks and Hero/Entity blocks specific to players appear in the same order.
        """
        all_players = left_team + right_team # Should be ordered by position 0..N
        
        # Sort players by position (just in case)
        all_players.sort(key=lambda p: p.position)
        
        # Map sequentially
        # If we have 6 players and 6 heroes, 1:1 mapping
        # If counts mismatch, try best effort
        
        count = min(len(all_players), len(detected_heroes))
        
        for i in range(count):
            player = all_players[i]
            hero = detected_heroes[i]
            
            player.hero_name = hero['name']
            player.hero_id = hero['id']
            player.deaths = hero['deaths'] // 2
    
    def _parse_player_blocks(self, data: bytes) -> List[PlayerData]:
        """Find player blocks and extract name, team id, and entity id."""
        players: List[PlayerData] = []
        seen = set()
        search_start = 0
        markers = (self.PLAYER_BLOCK_MARKER, self.PLAYER_BLOCK_MARKER_ALT)

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

            # Player name starts after marker
            name_start = pos + len(marker)

            # Find end of name (look for non-printable or long null sequence)
            name_end = name_start
            while name_end < len(data) and name_end < name_start + 30:
                byte = data[name_end]
                if byte < 32 or byte > 126:  # Non-printable ASCII
                    break
                name_end += 1

            if name_end > name_start:
                try:
                    name = data[name_start:name_end].decode('ascii')
                except Exception:
                    name = ""

                if len(name) >= 3 and not name.startswith('GameMode'):
                    if name not in seen:
                        team_id = data[pos + 0xD5] if pos + 0xD5 < len(data) else None
                        entity_id = None
                        if pos + 0xA5 + 2 <= len(data):
                            entity_id = int.from_bytes(data[pos + 0xA5:pos + 0xA5 + 2], 'little')
                        player = PlayerData(
                            name=name,
                            position=len(players),
                            team=self._team_label_from_id(team_id),
                            team_id=team_id,
                            entity_id=entity_id,
                        )
                        players.append(player)
                        seen.add(name)

            search_start = pos + 1

        return players

    def _split_teams(self, players: List[PlayerData], team_size: int) -> Tuple[List[PlayerData], List[PlayerData]]:
        """Split players into left/right teams using team id if available."""
        players_sorted = sorted(players, key=lambda p: p.position)
        left_team = [p for p in players_sorted if p.team == "left"]
        right_team = [p for p in players_sorted if p.team == "right"]
        unknown = [p for p in players_sorted if p.team == "unknown"]

        if left_team or right_team:
            left_needed = max(team_size - len(left_team), 0)
            right_needed = max(team_size - len(right_team), 0)
            for player in unknown:
                if left_needed > 0:
                    player.team = "left"
                    left_team.append(player)
                    left_needed -= 1
                elif right_needed > 0:
                    player.team = "right"
                    right_team.append(player)
                    right_needed -= 1
                else:
                    player.team = "left"
                    left_team.append(player)
            return left_team, right_team

        left_team = players_sorted[:team_size]
        right_team = players_sorted[team_size:]
        for player in left_team:
            player.team = "left"
        for player in right_team:
            player.team = "right"
        return left_team, right_team

    def _read_all_frames(self, frame_dir: Path, replay_name: str) -> bytes:
        """Read all frames for a replay in order."""
        frames = list(frame_dir.glob(f"{replay_name}.*.vgr"))
        def _frame_index(path: Path) -> int:
            try:
                return int(path.stem.split('.')[-1])
            except ValueError:
                return 0
        frames.sort(key=_frame_index)
        return b"".join(frame.read_bytes() for frame in frames)

    def _scan_entity_actions(self, data: bytes, entity_id: int) -> Dict[str, int]:
        """Count action types for a given entity id using [id][00 00][action]."""
        base = entity_id.to_bytes(2, 'little') + b'\x00\x00'
        counts: Counter[int] = Counter()
        idx = 0
        while True:
            idx = data.find(base, idx)
            if idx == -1:
                break
            if idx + 4 < len(data):
                counts[data[idx + 4]] += 1
            idx += 1
        return {f"0x{act:02X}": cnt for act, cnt in counts.items() if cnt > 0}

    def _find_truth_data(self, replay_name: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Find matching truth data in the current working directory."""
        if not TRUTH_AVAILABLE:
            return None, None
        candidates = []
        cwd = Path.cwd()
        for pattern in ("MATCH_DATA_*.md", "MATCH_DATA_*.txt", "match_truth*.json", "truth*.json"):
            candidates.extend(cwd.glob(pattern))
        for path in candidates:
            truth = load_truth_data(str(path), replay_name)
            if truth:
                return truth, str(path)
        return None, None

    def _apply_truth_data(self, truth: Dict[str, Any], players: List[PlayerData], match_info: MatchInfo) -> None:
        """Apply truth data to players and match info."""
        truth_players = truth.get("players", {})
        players_by_name = {p.name: p for p in players}
        players_by_lower = {p.name.lower(): p for p in players}

        def find_player(target: str) -> Optional[PlayerData]:
            player = players_by_name.get(target)
            if player:
                return player
            player = players_by_lower.get(target.lower())
            if player:
                return player
            prefix = target.split("_", 1)[0]
            candidates = [name for name in players_by_name if name.split("_", 1)[0] == prefix]
            if not candidates:
                return None
            match = difflib.get_close_matches(target, candidates, n=1, cutoff=0.85)
            if not match:
                return None
            matched_name = match[0]
            player = players_by_name.get(matched_name)
            if not player:
                return None
            if matched_name != target:
                del players_by_name[matched_name]
                players_by_lower.pop(matched_name.lower(), None)
                player.name = target
                players_by_name[target] = player
                players_by_lower[target.lower()] = player
            return player

        for name, tdata in truth_players.items():
            player = find_player(name)
            if not player:
                continue
            if tdata.get("team"):
                player.team = tdata["team"]
            if tdata.get("hero_name"):
                player.hero_name = tdata["hero_name"]
            if tdata.get("hero_name_ko"):
                player.hero_name_ko = tdata["hero_name_ko"]
            if tdata.get("kills") is not None:
                player.kills = tdata["kills"]
            if tdata.get("deaths") is not None:
                player.deaths = tdata["deaths"]
            if tdata.get("assists") is not None:
                player.assists = tdata["assists"]
            if tdata.get("gold") is not None:
                player.gold = tdata["gold"]
            if "minion_kills" in tdata:
                player.minion_kills = tdata["minion_kills"]
            elif "bounty" in tdata:
                player.minion_kills = None
            if tdata.get("bounty") is not None:
                player.bounty = tdata["bounty"]

            if MAPPING_AVAILABLE and player.hero_name:
                hero_info = VGRMapping.get_hero_by_name(player.hero_name)
                if hero_info:
                    player.hero_id = hero_info["id"]
                    if not player.hero_name_ko:
                        player.hero_name_ko = hero_info.get("name_ko")

        truth_match = truth.get("match_info", {})
        if truth_match.get("duration_seconds") is not None:
            match_info.duration_seconds = truth_match["duration_seconds"]
        if truth_match.get("winner"):
            match_info.winner = truth_match["winner"]
        if truth_match.get("score_left") is not None:
            match_info.score_left = truth_match["score_left"]
        if truth_match.get("score_right") is not None:
            match_info.score_right = truth_match["score_right"]
    
    def _assign_teams(self, player_names: List[str], team_size: int) -> Tuple[List[PlayerData], List[PlayerData]]:
        """Assign players to teams based on position"""
        left_team = []
        right_team = []
        
        for i, name in enumerate(player_names):
            player = PlayerData(
                name=name,
                position=i,
                team="left" if i < team_size else "right"
            )
            
            if i < team_size:
                left_team.append(player)
            else:
                right_team.append(player)
        
        return left_team, right_team
    
    def _map_uuids_to_players(self, players: List[PlayerData], uuids: List[str]) -> None:
        """Try to map UUIDs to players based on position"""
        for i, player in enumerate(players):
            if i < len(uuids):
                player.uuid = uuids[i]
    
    def parse(self) -> Dict[str, Any]:
        """
        Parse the replay file and extract data.
        
        Returns:
            Dictionary containing extracted data
        """
        first_frame = self._find_first_frame()
        if not first_frame:
            raise FileNotFoundError(f"No .0.vgr file found in {self.replay_path}")
        
        # Count total frames
        frame_dir = first_frame.parent
        replay_name = first_frame.stem.rsplit('.', 1)[0]  # Remove .0 suffix
        frame_count = len(list(frame_dir.glob(f"{replay_name}.*.vgr")))
        
        # Read first frame
        with open(first_frame, 'rb') as f:
            data = f.read()
        
        # Extract data
        strings = self._extract_strings(data)
        uuids = self._extract_uuids(data)
        game_mode = self._find_game_mode(strings)
        
        # Get team configuration
        team_size = self._get_team_size(game_mode)
        map_name = self._get_map_name(game_mode)
        
        # Try marker-based extraction first
        players = self._parse_player_blocks(data)
        if players:
            left_team, right_team = self._split_teams(players, team_size)
            player_names = [p.name for p in players]
        else:
            # Fallback to string filtering
            player_names = self._filter_player_names(strings, uuids)
            left_team, right_team = self._assign_teams(player_names, team_size)
        
        # Map UUIDs to players
        all_players = left_team + right_team
        self._map_uuids_to_players(all_players, uuids)
        
        # Build match info
        match_info = MatchInfo(
            mode=game_mode or "Unknown",
            mode_friendly=self._friendly_game_mode(game_mode),
            map_name=map_name,
            team_size=team_size,
            total_frames=frame_count
        )
        
        detected_heroes = []
        all_data = None
        if self.detect_heroes or self.debug_events:
            all_data = self._read_all_frames(frame_dir, replay_name)

        # Detect heroes based on event frequency (heuristic, opt-in)
        if self.detect_heroes:
            detected_heroes = self._detect_heroes(data, team_size)
            self._link_heroes_to_players(left_team, right_team, detected_heroes, data)

        # Apply truth data if available
        truth = None
        truth_source = None
        if self.truth_path and TRUTH_AVAILABLE:
            truth = load_truth_data(self.truth_path, replay_name)
            if truth:
                truth_source = self.truth_path
        if not truth and self.auto_truth:
            truth, truth_source = self._find_truth_data(replay_name)
        if truth:
            self._apply_truth_data(truth, all_players, match_info)
            left_team = [p for p in all_players if p.team == "left"]
            right_team = [p for p in all_players if p.team == "right"]
            player_names = [p.name for p in all_players]
        
        # Build result
        self.data = {
            'replay_file': str(first_frame),
            'replay_name': replay_name,
            'parsed_at': datetime.now().isoformat(),
            'match_info': match_info.to_dict(),
            'teams': {
                'left': [p.to_dict() for p in left_team],
                'right': [p.to_dict() for p in right_team]
            },
            'detected_heroes': detected_heroes,  # NEW: Heroes detected by event analysis
            'truth_source': truth_source,
            # Legacy fields for backwards compatibility
            'frame_count': frame_count,
            'file_size_bytes': len(data),
            'game_mode': game_mode,
            'game_mode_friendly': self._friendly_game_mode(game_mode),
            'players': player_names,
            'player_count': len(player_names),
            'player_uuids': uuids[:10]
        }

        if self.debug_events and all_data:
            event_debug = {}
            for player in all_players:
                if player.entity_id is None:
                    continue
                event_debug[player.name] = self._scan_entity_actions(all_data, player.entity_id)
            self.data['event_debug'] = event_debug
        
        return self.data
    
    def _friendly_game_mode(self, mode: Optional[str]) -> str:
        """Convert game mode to friendly name"""
        if not mode:
            return "Unknown"
        mode_map = {
            'GameMode_HF_Ranked': '3v3 Ranked (Halcyon Fold)',
            'GameMode_HF_Casual': '3v3 Casual (Halcyon Fold)',
            'GameMode_5v5_Ranked': '5v5 Ranked (Sovereign Rise)',
            'GameMode_5v5_Casual': '5v5 Casual (Sovereign Rise)',
            'GameMode_Blitz': 'Blitz',
            'GameMode_ARAL': 'ARAL',
            'GameMode_BR': 'Battle Royale',
        }
        return mode_map.get(mode, mode)
    
    def to_json(self, indent: int = 2) -> str:
        """Return parsed data as JSON string"""
        return json.dumps(self.data, indent=indent, ensure_ascii=False)


def scan_replay_folders(
    base_path: str,
    detect_heroes: bool = False,
    debug_events: bool = False,
    truth_path: Optional[str] = None,
    auto_truth: bool = True,
) -> List[Dict[str, Any]]:
    """
    Scan all replay folders and extract data from each.
    
    Args:
        base_path: Base path containing replay date folders
        
    Returns:
        List of parsed replay data dictionaries
    """
    base = Path(base_path)
    results = []
    
    # Find all .0.vgr files
    for vgr_file in base.rglob('*.0.vgr'):
        if vgr_file.name.startswith("._") or "__MACOSX" in vgr_file.parts:
            continue
        try:
            parser = VGRParser(
                str(vgr_file),
                detect_heroes=detect_heroes,
                debug_events=debug_events,
                truth_path=truth_path,
                auto_truth=auto_truth,
            )
            data = parser.parse()
            results.append(data)
            print(f"[OK] Parsed: {vgr_file.parent.name}/{vgr_file.name}")
        except Exception as e:
            print(f"[ERR] Error parsing {vgr_file}: {e}")
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description='VGR Replay Parser - Extract data from Vainglory replay files'
    )
    parser.add_argument(
        'path',
        help='Path to replay folder or .0.vgr file'
    )
    parser.add_argument(
        '-o', '--output',
        help='Output JSON file path (default: stdout)'
    )
    parser.add_argument(
        '-b', '--batch',
        action='store_true',
        help='Batch process all replays in subfolders'
    )
    parser.add_argument(
        '--pretty',
        action='store_true',
        default=True,
        help='Pretty print JSON output (default: True)'
    )
    parser.add_argument(
        '--detect-heroes',
        action='store_true',
        help='Enable heuristic hero detection (may be inaccurate)'
    )
    parser.add_argument(
        '--debug-events',
        action='store_true',
        help='Include per-player event action counts for analysis'
    )
    parser.add_argument(
        '--truth',
        help='Path to truth data (MATCH_DATA_*.md or JSON) to reconcile output'
    )
    parser.add_argument(
        '--no-auto-truth',
        action='store_true',
        help='Disable automatic MATCH_DATA_*.md lookup'
    )
    
    args = parser.parse_args()
    
    if args.batch:
        results = scan_replay_folders(
            args.path,
            detect_heroes=args.detect_heroes,
            debug_events=args.debug_events,
            truth_path=args.truth,
            auto_truth=not args.no_auto_truth,
        )
        output = json.dumps(results, indent=2 if args.pretty else None, ensure_ascii=False)
    else:
        vgr_parser = VGRParser(
            args.path,
            detect_heroes=args.detect_heroes,
            debug_events=args.debug_events,
            truth_path=args.truth,
            auto_truth=not args.no_auto_truth,
        )
        data = vgr_parser.parse()
        output = json.dumps(data, indent=2 if args.pretty else None, ensure_ascii=False)
    
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output)
        print(f"\n결과가 {args.output}에 저장되었습니다.")
    else:
        print(output)


if __name__ == '__main__':
    main()
