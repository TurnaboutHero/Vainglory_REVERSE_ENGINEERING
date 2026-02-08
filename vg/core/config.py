#!/usr/bin/env python3
"""
VGR Configuration - Path and environment settings for Vainglory replay analysis.

Environment Variables:
    VG_REPLAY_PATH: Base path to replay files (required for replay analysis)

Usage:
    Set VG_REPLAY_PATH before running:
        export VG_REPLAY_PATH="/path/to/vg/replays"  # Unix/Mac
        set VG_REPLAY_PATH=D:\\path\\to\\vg\\replays     # Windows
"""
import os
from pathlib import Path
from typing import Optional

# Cache for lazy initialization
_replay_base_path: Optional[Path] = None


def get_replay_base_path() -> Path:
    """Get replay base path from environment variable.

    Returns:
        Path to replay directory.

    Raises:
        ValueError: If VG_REPLAY_PATH is not set or path doesn't exist.
    """
    global _replay_base_path

    if _replay_base_path is not None:
        return _replay_base_path

    env_path = os.environ.get('VG_REPLAY_PATH')

    if not env_path:
        raise ValueError(
            "VG_REPLAY_PATH environment variable is not set. "
            "Please set it to your Vainglory replay directory:\n"
            "  Unix/Mac: export VG_REPLAY_PATH='/path/to/vg/replays'\n"
            "  Windows:  set VG_REPLAY_PATH=D:\\path\\to\\vg\\replays"
        )

    path = Path(env_path)
    if not path.exists():
        raise ValueError(
            f"VG_REPLAY_PATH points to non-existent directory: {env_path}"
        )

    _replay_base_path = path
    return _replay_base_path


def get_tournament_replays_path() -> Path:
    """Get tournament replays subdirectory path."""
    return get_replay_base_path() / 'Tournament_Replays'


# Output directory (relative to package, always available)
OUTPUT_PATH = Path(__file__).parent.parent / 'output'
