"""Extract plausible player-handle-like strings from dump string inventories."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List

from .dump_string_diff import extract_strings_from_bytes


HANDLE_PATTERNS = [
    re.compile(r"^\d{4}_[A-Za-z0-9_]{2,20}$"),
]
NOISE_SUBSTRINGS = {
    "skinkey",
    "_skin_",
    "card_",
    "themekey",
    "cardid",
    "experiment",
    "individual_",
    "season",
    "value_type",
    "trophy_type",
    "windows_",
    "gamemode_",
    "uia_",
    "ocl_",
}


def _score_candidate(value: str) -> int:
    score = 0
    if "_" in value:
        score += 20
    if re.search(r"\d", value):
        score += 5
    if re.match(r"^\d{4}_", value):
        score += 10
    if len(value) <= 20:
        score += 5
    if any(ch.isupper() for ch in value):
        score += 3
    return score


def is_probable_handle(value: str) -> bool:
    token = value.strip().strip('"').strip("'")
    if not token:
        return False
    if any(ch in token for ch in "*\\/.:{}[]()<> "):
        return False
    lower = token.lower()
    if any(noise in lower for noise in NOISE_SUBSTRINGS):
        return False
    prefix = token.split("_", 1)[0]
    if not any(ch.isdigit() for ch in prefix):
        return False
    return any(pattern.match(token) for pattern in HANDLE_PATTERNS)


def build_player_handle_candidates(dump_path: str, *, required_prefix: str | None = None) -> Dict[str, object]:
    dump = Path(dump_path)
    strings = extract_strings_from_bytes(dump.read_bytes())
    candidates = {}
    for value in strings:
        for token in re.findall(r"[A-Za-z0-9_]{4,32}", value):
            if is_probable_handle(token):
                if required_prefix and not token.startswith(required_prefix):
                    continue
                candidates[token] = _score_candidate(token)
    ranked = sorted(
        (
            {"candidate": candidate, "score": score}
            for candidate, score in candidates.items()
        ),
        key=lambda row: (row["score"], len(row["candidate"])),
        reverse=True,
    )
    return {
        "dump_path": str(dump.resolve()),
        "required_prefix": required_prefix,
        "candidate_count": len(ranked),
        "candidates": ranked[:500],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract plausible player-handle candidates from a dump file.")
    parser.add_argument("--dump", required=True, help="Dump file path")
    parser.add_argument("--required-prefix", help="Optional prefix filter for candidate handles")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args()

    report = build_player_handle_candidates(args.dump, required_prefix=args.required_prefix)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"Dump player-handle candidates saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
