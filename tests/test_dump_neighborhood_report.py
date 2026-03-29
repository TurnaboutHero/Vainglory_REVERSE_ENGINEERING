import tempfile
import unittest
from pathlib import Path

from vg.tools.dump_neighborhood_report import build_dump_neighborhood_report


class TestDumpNeighborhoodReport(unittest.TestCase):
    def test_build_dump_neighborhood_report_captures_hit_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dump = Path(tmp) / "sample.dmp"
            dump.write_bytes(b"xxxxPLAYER_ONEyyyy")
            report = build_dump_neighborhood_report(str(dump), "PLAYER_ONE", radius=4)

        self.assertEqual(report["hit_count"], 2)  # ascii + utf8
        self.assertIn("PLAYER_ONE", report["hits"][0]["context_ascii"])


if __name__ == "__main__":
    unittest.main()
