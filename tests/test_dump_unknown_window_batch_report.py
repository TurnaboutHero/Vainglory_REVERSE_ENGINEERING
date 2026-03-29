import json
import tempfile
import unittest
from pathlib import Path

from vg.tools.dump_unknown_window_batch_report import build_unknown_window_batch_report


class TestDumpUnknownWindowBatchReport(unittest.TestCase):
    def test_build_unknown_window_batch_report_profiles_unknown_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            diff = Path(tmp) / "diff.json"
            dump = Path(tmp) / "sample.dmp"
            diff.write_text(
                json.dumps(
                    {
                        "top_windows": [
                            {
                                "window_start": 0,
                                "classification": "unknown",
                                "delta_count": 10,
                                "after_samples": ["111", "222"],
                                "after_contexts": ["111 222 333 444"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            dump.write_bytes((b"111 222 333 444\x00" * 40)[:4096])
            report = build_unknown_window_batch_report(str(diff), str(dump), max_windows=5)

        self.assertEqual(report["window_count"], 1)
        self.assertEqual(report["windows"][0]["window_start"], 0)
        self.assertIn("top_stride", report["windows"][0])


if __name__ == "__main__":
    unittest.main()
