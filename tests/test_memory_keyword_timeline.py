import json
import tempfile
import unittest
from pathlib import Path

from vg.tools.memory_keyword_timeline import build_memory_keyword_timeline


class TestMemoryKeywordTimeline(unittest.TestCase):
    def test_build_memory_keyword_timeline_tracks_present_and_missing_dumps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dump_path = root / "menu.dmp"
            dump_path.write_bytes(b"Temporary ashasha")
            manifest_path = root / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "phases": [
                            {"phase": "menu_home", "dump_path": str(dump_path)},
                            {"phase": "replay_loaded_initial", "dump_path": str(root / "missing.dmp")},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            report = build_memory_keyword_timeline(str(manifest_path), ["Temporary ashasha"])

        self.assertEqual(len(report["timeline"]), 2)
        self.assertTrue(report["timeline"][0]["available"])
        self.assertFalse(report["timeline"][1]["available"])
        self.assertGreater(
            report["timeline"][0]["keywords"]["Temporary ashasha"]["total_matches"],
            0,
        )


if __name__ == "__main__":
    unittest.main()
