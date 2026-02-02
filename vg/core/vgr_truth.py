#!/usr/bin/env python3
"""
Truth data loader for Vainglory replays.
Supports JSON and markdown tables (MATCH_DATA_*.md).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional

UUID_PAIR_PATTERN = re.compile(
    r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
    r'-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})',
    re.IGNORECASE,
)
TIME_PATTERN = re.compile(r'(\d+)\s*분\s*(\d+)\s*초')
SCORE_PATTERN = re.compile(r'(\d+)\s*vs\s*(\d+)', re.IGNORECASE)


def load_truth_data(path: str, replay_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Load truth data from JSON or markdown. Returns a dict for a single replay."""
    truth_path = Path(path)
    if not truth_path.exists():
        return None

    if truth_path.suffix.lower() == ".json":
        data = json.loads(truth_path.read_text(encoding="utf-8"))
        return _select_truth_match(data, replay_name)

    if truth_path.suffix.lower() in {".md", ".txt"}:
        text = truth_path.read_text(encoding="utf-8", errors="replace")
        return _parse_truth_markdown(text, replay_name)

    return None


def _select_truth_match(data: Dict[str, Any], replay_name: Optional[str]) -> Optional[Dict[str, Any]]:
    """Select a single match from JSON data."""
    if not replay_name:
        return data

    if isinstance(data, dict):
        if data.get("replay_name") == replay_name:
            return data

        matches = data.get("matches")
        if isinstance(matches, dict):
            return matches.get(replay_name)
        if isinstance(matches, list):
            for match in matches:
                if match.get("replay_name") == replay_name:
                    return match

    return None


def _parse_truth_markdown(text: str, replay_name: Optional[str]) -> Optional[Dict[str, Any]]:
    """Parse MATCH_DATA_*.md into a truth data dict."""
    match_name = None
    match = UUID_PAIR_PATTERN.search(text)
    if match:
        match_name = match.group(1)
        if replay_name and match_name != replay_name:
            return None

    duration_seconds = None
    time_match = TIME_PATTERN.search(text)
    if time_match:
        minutes = int(time_match.group(1))
        seconds = int(time_match.group(2))
        duration_seconds = minutes * 60 + seconds

    score_left = None
    score_right = None
    score_match = SCORE_PATTERN.search(text)
    if score_match:
        score_left = int(score_match.group(1))
        score_right = int(score_match.group(2))

    winner = None
    for line in text.splitlines():
        if "Blue Team" in line and "승리" in line:
            winner = "left"
        if "Red Team" in line and "승리" in line:
            winner = "right"

    players: Dict[str, Any] = {}
    current_team: Optional[str] = None
    for line in text.splitlines():
        if line.startswith("##") and "Blue Team" in line:
            current_team = "left"
            continue
        if line.startswith("##") and "Red Team" in line:
            current_team = "right"
            continue
        if not current_team:
            continue
        if not line.strip().startswith("|"):
            continue

        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 7:
            continue
        if cells[0].lower() in {"플레이어", "player"}:
            continue
        if set(cells[0]) == {"-"}:
            continue

        player_name = cells[0]
        hero_name, hero_name_ko = _parse_hero_cell(cells[1])
        kills = _safe_int(cells[2])
        deaths = _safe_int(cells[3])
        assists = _safe_int(cells[4])
        gold = _parse_gold(cells[5])
        cs = _safe_int(cells[6])

        players[player_name] = {
            "team": current_team,
            "hero_name": hero_name,
            "hero_name_ko": hero_name_ko,
            "kills": kills,
            "deaths": deaths,
            "assists": assists,
            "gold": gold,
            "minion_kills": cs,
        }

    return {
        "replay_name": match_name,
        "match_info": {
            "duration_seconds": duration_seconds,
            "winner": winner,
            "score_left": score_left,
            "score_right": score_right,
        },
        "players": players,
        "source_format": "markdown",
    }


def _parse_hero_cell(cell: str) -> tuple[str, Optional[str]]:
    text = cell.replace("**", "").strip()
    hero_name = text
    hero_name_ko = None
    if "(" in text and ")" in text:
        before, after = text.split("(", 1)
        hero_name = before.strip()
        hero_name_ko = after.split(")", 1)[0].strip()
    return hero_name, hero_name_ko


def _parse_gold(cell: str) -> Optional[int]:
    if not cell:
        return None
    value = cell.strip().lower().replace(",", "")
    try:
        if value.endswith("k"):
            return int(float(value[:-1]) * 1000)
        if value.endswith("m"):
            return int(float(value[:-1]) * 1000000)
        return int(float(value))
    except ValueError:
        return None


def _safe_int(value: str) -> Optional[int]:
    try:
        return int(value)
    except ValueError:
        return None
