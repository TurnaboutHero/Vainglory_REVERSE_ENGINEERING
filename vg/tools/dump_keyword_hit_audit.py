"""Audit dump keyword hits and classify likely false-positive neighborhoods."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List

from .dump_neighborhood_report import build_dump_neighborhood_report


GLYPH_RE = re.compile(r"(?:cid\d{4,}|uni[0-9A-Fa-f]{3,})")
UPPER_TOKEN_RE = re.compile(r"[A-Z0-9_. -]{6,}")
UPPER_WORD_RE = re.compile(r"[A-Z0-9_]{4,}")
LOCALE_MARKERS = (
    "koreana",
    "schinese",
    "english",
    "german",
    "spanish",
    "french",
    "japanese",
    "russian",
    "vietnamese",
    "south-korea",
    "south korea",
    "united-states",
    "united-states",
    "zh-hans",
    "zh-hant",
)
CONFIG_MARKERS = (
    '\\"',
    "imagename",
    "skinkey",
    "experiment",
    "limitededition",
    "seasonchest",
    "availability",
    "favorit",
    "proto",
)
SYMBOL_MARKERS = (
    "kindred@nuo@@",
    "?av",
    "request",
    "command",
    "site",
    "ticket_",
)
RUNTIME_MARKERS = (
    '"handle"',
    '"entitlement_',
    "gamemode_",
    "temporary ",
    "ranked",
    "practice",
)


def classify_keyword_context(context_ascii: str) -> str:
    lower = context_ascii.lower()
    if len(GLYPH_RE.findall(context_ascii)) >= 3:
        return "glyph_table"
    if any(marker in lower for marker in LOCALE_MARKERS):
        return "locale_table"
    if any(marker in lower for marker in RUNTIME_MARKERS):
        return "runtime_state"
    if any(marker in lower for marker in CONFIG_MARKERS):
        return "config_or_proto"
    if any(marker in lower for marker in SYMBOL_MARKERS):
        return "symbol_table"

    uppercase_tokens = UPPER_TOKEN_RE.findall(context_ascii)
    uppercase_words = UPPER_WORD_RE.findall(context_ascii)
    letters = [ch for ch in context_ascii if ch.isalpha()]
    lowercase_count = sum(1 for ch in letters if ch.islower())
    if (len(uppercase_tokens) >= 3 or len(uppercase_words) >= 5) and letters and lowercase_count / len(letters) < 0.12:
        return "asset_or_table_noise"
    return "unknown"


def build_dump_keyword_hit_audit(dump_path: str, keywords: List[str], radius: int = 160) -> Dict[str, object]:
    per_keyword = []
    for keyword in keywords:
        report = build_dump_neighborhood_report(dump_path, keyword, radius=radius)
        classes: Dict[str, int] = {}
        audited_hits = []
        for hit in report["hits"]:
            hit_class = classify_keyword_context(hit["context_ascii"])
            classes[hit_class] = classes.get(hit_class, 0) + 1
            audited_hits.append(
                {
                    "encoding": hit["encoding"],
                    "offset": hit["offset"],
                    "classification": hit_class,
                    "context_ascii": hit["context_ascii"][:240],
                }
            )
        per_keyword.append(
            {
                "keyword": keyword,
                "hit_count": report["hit_count"],
                "class_counts": classes,
                "sample_hits": audited_hits[:20],
            }
        )

    return {
        "dump_path": str(Path(dump_path).resolve()),
        "radius": radius,
        "keywords": per_keyword,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit dump keyword hits and classify likely false-positive contexts.")
    parser.add_argument("--dump", required=True, help="Dump file path")
    parser.add_argument("--keywords", nargs="+", required=True, help="Keywords to audit")
    parser.add_argument("--radius", type=int, default=160, help="Neighborhood radius in bytes")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args()

    report = build_dump_keyword_hit_audit(args.dump, args.keywords, radius=args.radius)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"Dump keyword audit saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
