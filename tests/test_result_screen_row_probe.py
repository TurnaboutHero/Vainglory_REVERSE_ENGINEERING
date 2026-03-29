import tempfile
import unittest
from pathlib import Path

from vg.tools.result_screen_row_probe import probe_result_screen_rows


class TestResultScreenRowProbe(unittest.TestCase):
    def test_probe_result_screen_rows_extracts_nearby_stats(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dump = Path(tmp) / "sample.dmp"
            payload = "8815_DIOR 12/1/4 13.8k 145".encode("utf-16-le")
            dump.write_bytes(payload)
            report = probe_result_screen_rows(str(dump), ["8815_DIOR"], radius=64)

        row = report["players"][0]
        self.assertEqual(row["hit_count"], 1)
        hit = row["hits"][0]
        self.assertIn("12/1/4", hit["kda_candidates"])
        self.assertIn("13.8k", hit["gold_candidates"])
        self.assertIn("145", hit["numeric_candidates"])


if __name__ == "__main__":
    unittest.main()
