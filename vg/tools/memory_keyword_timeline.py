"""Build a keyword timeline across a memory-session manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

from .dump_keyword_search import search_dump_keywords


def build_memory_keyword_timeline(manifest_path: str, keywords: List[str]) -> Dict[str, object]:
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    rows = []
    for phase in manifest["phases"]:
        dump_path = phase["dump_path"]
        if not Path(dump_path).exists():
            rows.append(
                {
                    "phase": phase["phase"],
                    "dump_path": str(Path(dump_path).resolve()),
                    "available": False,
                    "keywords": {},
                }
            )
            continue

        report = search_dump_keywords(dump_path, keywords)
        keyword_summary = {}
        for item in report["keywords"]:
            total_count = sum(match["count"] for match in item["matches"].values())
            keyword_summary[item["keyword"]] = {
                "total_matches": total_count,
                "encodings": item["matches"],
            }
        rows.append(
            {
                "phase": phase["phase"],
                "dump_path": report["dump_path"],
                "available": True,
                "keywords": keyword_summary,
            }
        )

    return {
        "manifest_path": str(Path(manifest_path).resolve()),
        "keywords": keywords,
        "timeline": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a keyword timeline across a memory session manifest.")
    parser.add_argument("--manifest", required=True, help="Session manifest JSON path")
    parser.add_argument("--keyword", action="append", required=True, help="Keyword to track")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args()

    report = build_memory_keyword_timeline(args.manifest, list(args.keyword))
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"Memory keyword timeline saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
