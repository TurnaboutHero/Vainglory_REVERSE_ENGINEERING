import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import patch

from vg.tools.vgrplay_inject import find_live_temp_replay, inject_replay_with_vgrplay


class TestVgrplayInject(unittest.TestCase):
    def test_find_live_temp_replay_picks_latest_vgr(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            older = Path(tmp) / "demo.1.vgr"
            newer = Path(tmp) / "demo.2.vgr"
            older.write_text("a", encoding="utf-8")
            newer.write_text("b", encoding="utf-8")
            os.utime(older, (1, 1))
            os.utime(newer, (2, 2))
            result = find_live_temp_replay(tmp)
        self.assertTrue(result["latest_file"].endswith("demo.2.vgr"))
        self.assertEqual(result["oname"], "demo")

    def test_inject_replay_with_vgrplay_reports_changed_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            before = Path(tmp) / "slot.0.vgr"
            before.write_text("before", encoding="utf-8")

            def fake_run(cmd, capture_output, text):
                before.write_text("after", encoding="utf-8")
                return type("Completed", (), {"returncode": 0, "stdout": "ok", "stderr": ""})()

            with patch("vg.tools.vgrplay_inject.subprocess.run", side_effect=fake_run):
                report = inject_replay_with_vgrplay(
                    source_dir="C:/src/replay",
                    replay_name="demo-replay",
                    temp_dir=tmp,
                    vgrplay_path="C:/tools/vgrplay.exe",
                )

        self.assertEqual(report["returncode"], 0)
        self.assertGreaterEqual(report["changed_count"], 1)
        self.assertIn("slot.0.vgr", report["changed_files"])


if __name__ == "__main__":
    unittest.main()
