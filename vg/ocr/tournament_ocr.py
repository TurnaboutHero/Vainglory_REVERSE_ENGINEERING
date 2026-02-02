#!/usr/bin/env python3
"""
OCR-based mapper for tournament result images to replay files.
Outputs a truth JSON that can be used with vgr_parser.py --truth.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import easyocr


UI_WORDS = {
    "REPLAY", "RATE", "SOCIAL", "FINISH", "SHARE",
    "VICTORY", "DEFEAT",
}


@dataclass
class Token:
    text: str
    x: float
    y: float
    w: float
    h: float
    conf: float


def _center(box: List[List[float]]) -> Tuple[float, float, float, float]:
    xs = [p[0] for p in box]
    ys = [p[1] for p in box]
    x = sum(xs) / len(xs)
    y = sum(ys) / len(ys)
    w = max(xs) - min(xs)
    h = max(ys) - min(ys)
    return x, y, w, h


def _normalize_text(text: str) -> str:
    cleaned = text.strip()
    cleaned = cleaned.replace("’", "'").replace("`", "'")
    cleaned = cleaned.replace("|", "/").replace("\\", "/")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def _is_kda(text: str) -> Optional[str]:
    match = re.search(r"(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{1,2})", text)
    if not match:
        return None
    return f"{match.group(1)}/{match.group(2)}/{match.group(3)}"


def _parse_gold(text: str) -> Optional[int]:
    cleaned = text.lower().replace("o", "0").replace("O", "0")
    match = re.search(r"(\d+(?:\.\d+)?)\s*k", cleaned)
    if not match:
        return None
    value = float(match.group(1))
    return int(value * 1000)


def _parse_time(text: str) -> Optional[int]:
    match = re.search(r"(\d{1,2})[:.](\d{2})", text)
    if not match:
        return None
    minutes = int(match.group(1))
    seconds = int(match.group(2))
    return minutes * 60 + seconds


def _parse_int(text: str) -> Optional[int]:
    cleaned = re.sub(r"[^\d]", "", text)
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def _fix_cs(value: int) -> int:
    if 400 <= value <= 999:
        value = value % 100
    if value >= 1000:
        value = int(str(value)[-3:])
    return value


def _tokenize(results: List[Any]) -> List[Token]:
    tokens: List[Token] = []
    for box, text, conf in results:
        x, y, w, h = _center(box)
        tokens.append(Token(_normalize_text(text), x, y, w, h, conf))
    return tokens


def _cluster_rows(tokens: List[Token], height: int) -> List[List[Token]]:
    if not tokens:
        return []
    tokens = sorted(tokens, key=lambda t: t.y)
    threshold = max(18.0, height * 0.05)
    rows: List[List[Token]] = [[tokens[0]]]
    row_y = tokens[0].y
    for token in tokens[1:]:
        if abs(token.y - row_y) > threshold:
            rows.append([token])
            row_y = token.y
        else:
            rows[-1].append(token)
            row_y = sum(t.y for t in rows[-1]) / len(rows[-1])
    return rows


def _extract_player_from_row(tokens: List[Token]) -> Dict[str, Any]:
    name_parts: List[Tuple[float, str]] = []
    kda: Optional[str] = None
    kda_x: Optional[float] = None
    gold: Optional[int] = None
    numbers: List[Tuple[float, int]] = []

    for token in sorted(tokens, key=lambda t: t.x):
        text = token.text
        upper = text.upper()
        if not text or upper in UI_WORDS:
            continue

        kda_match = _is_kda(text)
        if kda_match:
            kda = kda_match
            kda_x = token.x
            prefix = text.split(kda_match, 1)[0].strip()
            if prefix:
                name_parts.append((token.x, prefix))
            continue

        maybe_gold = _parse_gold(text)
        if maybe_gold is not None:
            gold = maybe_gold
            continue

        number = _parse_int(text)
        if number is not None and "/" not in text:
            if kda_x is None:
                name_parts.append((token.x, text))
            elif token.x > kda_x:
                numbers.append((token.x, number))
            continue

        if re.search(r"[A-Za-z_]", text):
            name_parts.append((token.x, text))

    name_parts = sorted(name_parts, key=lambda x: x[0])
    name_text = " ".join(p[1] for p in name_parts).strip()
    name_text = name_text.replace(" ", "_")
    name_text = re.sub(r"__+", "_", name_text)
    name_text = name_text.strip("_")
    name_text = re.sub(r"[^A-Za-z0-9_]+", "", name_text)
    segments = name_text.split("_")
    if len(segments) >= 3 and segments[0].isdigit() and len(segments[0]) <= 3 and segments[1].isdigit():
        name_text = "_".join(segments[1:])
    matches = re.findall(r"(\d{3,4}_[A-Za-z0-9]+)", name_text)
    if matches:
        name_text = matches[-1]

    kills = deaths = assists = None
    if kda:
        parts = kda.split("/")
        if len(parts) == 3:
            kills, deaths, assists = (int(parts[0]), int(parts[1]), int(parts[2]))

    cs = None
    if numbers:
        cs_candidate = max(numbers, key=lambda x: x[0])[1]
        cs = _fix_cs(cs_candidate)

    return {
        "name": name_text or None,
        "kills": kills,
        "deaths": deaths,
        "assists": assists,
        "gold": gold,
        "minion_kills": cs,
    }


def _parse_match_info(tokens: List[Token], width: int, height: int) -> Dict[str, Any]:
    top_tokens = [t for t in tokens if t.y < height * 0.22]
    duration = None
    for token in top_tokens:
        duration = _parse_time(token.text)
        if duration is not None:
            break

    score_left = None
    score_right = None
    for token in top_tokens:
        if "k" in token.text.lower():
            continue
        if _parse_time(token.text) is not None:
            continue
        value = _parse_int(token.text)
        if value is None:
            continue
        if value > 60:
            continue
        if token.x < width * 0.5:
            score_left = value if score_left is None else max(score_left, value)
        else:
            score_right = value if score_right is None else max(score_right, value)

    winner = None
    for token in top_tokens:
        if "VICTORY" in token.text.upper():
            winner = "left" if token.x < width * 0.5 else "right"
            break

    return {
        "duration_seconds": duration,
        "winner": winner,
        "score_left": score_left,
        "score_right": score_right,
    }


def _parse_image(tokens: List[Token], width: int, height: int) -> Dict[str, Any]:
    usable = [t for t in tokens if t.text and t.text.upper() not in UI_WORDS]
    left_tokens = [t for t in usable if t.x < width * 0.5]
    right_tokens = [t for t in usable if t.x >= width * 0.5]

    left_rows = _cluster_rows(left_tokens, height)
    right_rows = _cluster_rows(right_tokens, height)

    left_players = []
    for row in left_rows:
        player = _extract_player_from_row(row)
        if player["name"] and player["kills"] is not None:
            left_players.append(player)

    right_players = []
    for row in right_rows:
        player = _extract_player_from_row(row)
        if player["name"] and player["kills"] is not None:
            right_players.append(player)

    left_players = sorted(left_players, key=lambda p: p["name"])
    right_players = sorted(right_players, key=lambda p: p["name"])

    return {
        "match_info": _parse_match_info(tokens, width, height),
        "left": left_players,
        "right": right_players,
    }


def _read_image_size(path: Path) -> Tuple[int, int]:
    from PIL import Image
    with Image.open(path) as im:
        return im.size


def build_mapping(root: Path) -> List[Tuple[Path, Path]]:
    pairs = []
    for img in root.rglob("result*.jp*g"):
        if "__MACOSX" in img.parts:
            continue
        vgrs = sorted(img.parent.glob("*.0.vgr"))
        if not vgrs:
            continue
        pairs.append((img, vgrs[0]))
    return pairs


def main() -> int:
    parser = argparse.ArgumentParser(description="OCR tournament result images and map to replays.")
    parser.add_argument("root", help="Root folder with result images and .vgr files")
    parser.add_argument("--output", default="tournament_truth.json", help="Output truth JSON")
    parser.add_argument("--raw-output", default="tournament_ocr_raw.json", help="Raw OCR JSON")
    parser.add_argument("--gpu", action="store_true", help="Use GPU if available")
    args = parser.parse_args()

    root = Path(args.root)
    if not root.exists():
        print(f"Path not found: {root}")
        return 1

    reader = easyocr.Reader(["en"], gpu=args.gpu, verbose=False)
    pairs = build_mapping(root)

    matches = []
    raw_dump = []

    for img, vgr in pairs:
        width, height = _read_image_size(img)
        results = reader.readtext(str(img))
        tokens = _tokenize(results)
        parsed = _parse_image(tokens, width, height)

        players: Dict[str, Any] = {}
        for player in parsed["left"]:
            players[player["name"]] = {
                "team": "left",
                "hero_name": "Unknown",
                "kills": player["kills"],
                "deaths": player["deaths"],
                "assists": player["assists"],
                "gold": player["gold"],
                "minion_kills": player["minion_kills"],
            }
        for player in parsed["right"]:
            players[player["name"]] = {
                "team": "right",
                "hero_name": "Unknown",
                "kills": player["kills"],
                "deaths": player["deaths"],
                "assists": player["assists"],
                "gold": player["gold"],
                "minion_kills": player["minion_kills"],
            }

        matches.append({
            "replay_name": vgr.stem.rsplit(".", 1)[0],
            "replay_file": str(vgr),
            "result_image": str(img),
            "match_info": parsed["match_info"],
            "players": players,
        })

        raw_dump.append({
            "result_image": str(img),
            "tokens": [
                {
                    "text": t.text,
                    "x": float(t.x),
                    "y": float(t.y),
                    "w": float(t.w),
                    "h": float(t.h),
                    "conf": float(t.conf),
                }
                for t in tokens
            ],
        })

    Path(args.output).write_text(json.dumps({"matches": matches}, indent=2), encoding="utf-8")
    Path(args.raw_output).write_text(json.dumps({"images": raw_dump}, indent=2), encoding="utf-8")
    print(f"Wrote {len(matches)} matches to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
