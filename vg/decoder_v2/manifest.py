"""Replay manifest parsing helpers for decoder_v2."""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Optional


UUID_PAIR_PATTERN = re.compile(
    r"(?P<match_uuid>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
    r"-"
    r"(?P<session_uuid>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ReplayManifestRecord:
    """Parsed replay manifest content."""

    manifest_path: str
    match_uuid: Optional[str]
    session_uuid: Optional[str]
    raw_text: str

    def to_dict(self) -> Dict[str, Optional[str]]:
        return asdict(self)


def parse_replay_manifest(manifest_path: str) -> ReplayManifestRecord:
    """Parse a replay manifest file into UUID components."""
    path = Path(manifest_path)
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    match = UUID_PAIR_PATTERN.search(text)
    if not match:
        return ReplayManifestRecord(
            manifest_path=str(path),
            match_uuid=None,
            session_uuid=None,
            raw_text=text,
        )
    return ReplayManifestRecord(
        manifest_path=str(path),
        match_uuid=match.group("match_uuid"),
        session_uuid=match.group("session_uuid"),
        raw_text=text,
    )
