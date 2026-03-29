import tempfile
import unittest
from pathlib import Path

from vg.tools.dump_stride_report import build_dump_stride_report


class TestDumpStrideReport(unittest.TestCase):
    def test_build_dump_stride_report_detects_repeated_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dump = Path(tmp) / "sample.dmp"
            dump.write_bytes((b"ABCD" * 100) + (b"WXYZ" * 20))
            report = build_dump_stride_report(str(dump), 0, length=480, strides=[4, 8])

        self.assertEqual(report["stride_summaries"][0]["stride"], 4)
        self.assertGreater(report["stride_summaries"][0]["repeat_ratio"], 0.8)


if __name__ == "__main__":
    unittest.main()
