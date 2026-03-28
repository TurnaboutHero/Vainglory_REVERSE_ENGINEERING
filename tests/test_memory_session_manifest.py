import tempfile
import unittest
from pathlib import Path

from vg.tools.memory_session_manifest import build_memory_session_manifest


class TestMemorySessionManifest(unittest.TestCase):
    def test_build_memory_session_manifest_creates_phase_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = build_memory_session_manifest(
                session_root=tmp,
                replay_source_dir="C:/replays/source",
                replay_name="demo-replay",
                phases=["menu_home", "scoreboard_open"],
            )
            self.assertEqual(manifest["replay_name"], "demo-replay")
            self.assertEqual(len(manifest["phases"]), 2)
            self.assertTrue(Path(manifest["session_root"]).exists())


if __name__ == "__main__":
    unittest.main()
