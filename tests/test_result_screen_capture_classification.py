import json
import tempfile
import unittest
from pathlib import Path

from vg.tools.result_screen_capture_classification import build_result_screen_capture_classification


class TestResultScreenCaptureClassification(unittest.TestCase):
    def test_classification_marks_ready_for_processing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            session = root / "probe"
            dumps = session / "dumps"
            dumps.mkdir(parents=True)
            (session / "manifest.json").write_text(json.dumps({"replay_name": "sample"}), encoding="utf-8")
            (dumps / "result_screen_full.dmp").write_bytes(b"dump")

            report = build_result_screen_capture_classification(str(root))

        self.assertEqual(report["rows"][0]["processing_status"], "ready_for_processing")


if __name__ == "__main__":
    unittest.main()
