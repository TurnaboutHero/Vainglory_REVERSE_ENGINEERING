import json
import tempfile
import unittest
from pathlib import Path

from vg.tools.result_screen_capture_inventory import build_result_screen_capture_inventory


class TestResultScreenCaptureInventory(unittest.TestCase):
    def test_inventory_detects_dump_and_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session = root / "probe"
            dumps = session / "dumps"
            dumps.mkdir(parents=True)
            (session / "manifest.json").write_text(json.dumps({"replay_name": "sample"}), encoding="utf-8")
            (dumps / "result_screen_full.dmp").write_bytes(b"dump")
            (session / "result_screen_desktop.png").write_bytes(b"png")

            report = build_result_screen_capture_inventory(str(root))

        self.assertEqual(report["rows"][0]["status"], "captured_result_dump")
        self.assertTrue(report["rows"][0]["has_result_image"])


if __name__ == "__main__":
    unittest.main()
