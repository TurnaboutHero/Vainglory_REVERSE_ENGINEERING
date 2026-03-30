"""Grid-search KDA kill/death buffer configs against truth fixtures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .kda_postgame_audit import build_kda_postgame_audit

BufferConfig = Tuple[int, int]


def build_kda_buffer_grid_search(
    truth_path: str,
    *,
    kill_buffers: Sequence[int],
    death_buffers: Sequence[int],
) -> Dict[str, object]:
    configs: List[BufferConfig] = [
        (kill_buffer, death_buffer)
        for kill_buffer in kill_buffers
        for death_buffer in death_buffers
    ]
    audit = build_kda_postgame_audit(truth_path, buffer_configs=configs)

    rows = []
    for key, config_row in audit["buffer_config_summary"].items():
        complete = config_row["complete_only"]
        rows.append(
            {
                "config_key": key,
                "kill_buffer": config_row["kill_buffer"],
                "death_buffer": config_row["death_buffer"],
                "kill_pct": complete["kills"]["pct"],
                "death_pct": complete["deaths"]["pct"],
                "assist_pct": complete["assists"]["pct"],
                "combined_pct": complete["combined_kda"]["pct"],
                "combined_correct": complete["combined_kda"]["correct"],
                "combined_total": complete["combined_kda"]["total"],
            }
        )
    rows.sort(
        key=lambda row: (
            row["combined_pct"],
            row["kill_pct"],
            row["death_pct"],
            row["assist_pct"],
            -row["kill_buffer"],
            -row["death_buffer"],
        ),
        reverse=True,
    )

    return {
        "truth_path": str(Path(truth_path).resolve()),
        "kill_buffers": list(kill_buffers),
        "death_buffers": list(death_buffers),
        "rows": rows,
        "best_config": rows[0] if rows else None,
    }


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Grid-search KDA kill/death buffers against truth fixtures.")
    parser.add_argument("--truth", default="vg/output/tournament_truth.json", help="Truth JSON path")
    parser.add_argument("--kill-buffer", action="append", type=int, required=True, help="Kill buffer candidate (repeatable)")
    parser.add_argument("--death-buffer", action="append", type=int, required=True, help="Death buffer candidate (repeatable)")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args(list(argv) if argv is not None else None)

    report = build_kda_buffer_grid_search(
        args.truth,
        kill_buffers=list(args.kill_buffer),
        death_buffers=list(args.death_buffer),
    )
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"KDA buffer grid search saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
