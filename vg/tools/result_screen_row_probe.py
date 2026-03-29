"""Probe result-screen dump neighborhoods around exact player labels."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List


UTF16_PRINTABLE_RE = re.compile(rb"(?:[\x20-\x7E]\x00|[\x80-\xFF][\x00-\xFF]){4,}")
KDA_RE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{1,2}\b")
GOLD_RE = re.compile(r"\b\d{1,2}\.\dk\b", re.IGNORECASE)
MINION_RE = re.compile(r"(?<![\d/])\d{1,3}(?![\d/])")


def _find_all(data: bytes, needle: bytes) -> List[int]:
    out = []
    start = 0
    while True:
        idx = data.find(needle, start)
        if idx == -1:
            break
        out.append(idx)
        start = idx + 1
    return out


def _extract_utf16_strings(chunk: bytes) -> List[str]:
    values = []
    for match in UTF16_PRINTABLE_RE.finditer(chunk):
        try:
            values.append(match.group().decode("utf-16-le", errors="ignore"))
        except Exception:
            continue
    return values


def probe_result_screen_rows(dump_path: str, player_names: List[str], radius: int = 384) -> Dict[str, object]:
    data = Path(dump_path).read_bytes()
    rows = []
    for player_name in player_names:
        needle = player_name.encode("utf-16-le")
        hits = []
        for offset in _find_all(data, needle):
            start = max(0, offset - radius)
            end = min(len(data), offset + len(needle) + radius)
            chunk = data[start:end]
            strings = _extract_utf16_strings(chunk)
            kd_as = sorted({m.group(0) for s in strings for m in KDA_RE.finditer(s)})
            golds = sorted({m.group(0) for s in strings for m in GOLD_RE.finditer(s)})
            minions = sorted(
                {
                    m.group(0)
                    for s in strings
                    for m in MINION_RE.finditer(s)
                    if m.group(0) not in player_name and len(m.group(0)) <= 3
                }
            )
            hits.append(
                {
                    "offset": offset,
                    "context_start": start,
                    "context_end": end,
                    "utf16_strings": strings[:80],
                    "kda_candidates": kd_as,
                    "gold_candidates": golds,
                    "numeric_candidates": minions[:80],
                }
            )
        rows.append(
            {
                "player_name": player_name,
                "hit_count": len(hits),
                "hits": hits,
            }
        )
    return {
        "dump_path": str(Path(dump_path).resolve()),
        "radius": radius,
        "players": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe result-screen dump neighborhoods around exact player labels.")
    parser.add_argument("--dump", required=True, help="Result-screen dump path")
    parser.add_argument("--player", action="append", required=True, help="Player name to probe (repeatable)")
    parser.add_argument("--radius", type=int, default=384, help="Neighborhood radius")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args()

    report = probe_result_screen_rows(args.dump, args.player, radius=args.radius)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"Result screen row probe saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
