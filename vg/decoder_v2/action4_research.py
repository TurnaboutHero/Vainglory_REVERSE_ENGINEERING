"""Research helpers for credit action 0x04 payload semantics."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional

from .credit_events import iter_credit_events


def build_action4_report(replay_file: str, truth_path: Optional[str] = None) -> Dict[str, object]:
    """Build a per-player credit action 0x04 report for one replay."""
    truth_match = None
    if truth_path:
        truth_payload = json.loads(Path(truth_path).read_text(encoding="utf-8"))
        replay_name = Path(replay_file).stem.rsplit(".", 1)[0]
        truth_match = next(
            (match for match in truth_payload.get("matches", []) if match["replay_name"] == replay_name),
            None,
        )

    per_player: Dict[int, Counter] = defaultdict(Counter)
    per_player_payloads: Dict[int, List[dict]] = defaultdict(list)
    for event in iter_credit_events(replay_file):
        if event.action != 0x04:
            continue
        key = round(event.value, 2) if event.value is not None else "nan"
        per_player[event.entity_id_be][key] += 1
        if len(per_player_payloads[event.entity_id_be]) < 25:
            per_player_payloads[event.entity_id_be].append(
                {
                    "frame_idx": event.frame_idx,
                    "raw_record_hex": event.raw_record_hex,
                    "value": event.value,
                    "file_offset": event.file_offset,
                }
            )

    from vg.core.vgr_parser import VGRParser

    parsed = VGRParser(replay_file, auto_truth=False).parse()
    rows = []
    for team in ("left", "right"):
        for player in parsed["teams"][team]:
            entity_id = player.get("entity_id")
            if not entity_id:
                continue
            entity_be = int.from_bytes(entity_id.to_bytes(2, "little"), "big")
            truth_player = truth_match["players"].get(player["name"]) if truth_match else None
            rows.append(
                {
                    "player_name": player["name"],
                    "entity_id_le": entity_id,
                    "truth_minion_kills": truth_player.get("minion_kills") if truth_player else None,
                    "action4_total": sum(per_player[entity_be].values()),
                    "top_action4_payloads": [
                        {"value": key, "count": count}
                        for key, count in per_player[entity_be].most_common(15)
                    ],
                    "sample_payloads": per_player_payloads[entity_be],
                }
            )

    return {
        "replay_file": replay_file,
        "truth_path": truth_path,
        "rows": rows,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Research action 0x04 payload patterns for one replay.")
    parser.add_argument("replay_file", help="Replay file path")
    parser.add_argument("--truth", help="Optional truth JSON path")
    parser.add_argument("-o", "--output", help="Optional output path")
    args = parser.parse_args(argv)

    report = build_action4_report(args.replay_file, args.truth)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(payload, encoding="utf-8")
        print(f"Action4 report saved to {output_path}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
