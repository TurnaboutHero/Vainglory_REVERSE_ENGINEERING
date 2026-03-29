import tempfile
import unittest
from pathlib import Path

from vg.tools.result_screen_cluster_assignment_report import build_result_screen_cluster_assignment_report


def _build_cluster_dump() -> bytes:
    import struct
    from vg.tools.minidump_parser import MINIDUMP_SIGNATURE

    blob = (
        "8815_DIOR".encode("utf-16-le")
        + b"\x00" * 16
        + "12/1/4".encode("utf-16-le")
        + b"\x00" * 16
        + "13.8k".encode("utf-16-le")
    )
    header = struct.pack("<IIIIIIQ", MINIDUMP_SIGNATURE, 0x0000A793, 1, 32, 0, 0, 0)
    stream = struct.pack("<III", 9, 32, 44)
    memory64 = struct.pack("<QQQQ", 1, 76, 0x4000, len(blob))
    return header + stream + memory64 + blob


class TestResultScreenClusterAssignmentReport(unittest.TestCase):
    def test_build_result_screen_cluster_assignment_report_marks_present_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dump = Path(tmp) / "sample.dmp"
            dump.write_bytes(_build_cluster_dump())
            expected = [{"name": "8815_DIOR", "team": "left", "kills": 12, "deaths": 1, "assists": 4, "gold": "13.8k"}]
            report = build_result_screen_cluster_assignment_report(str(dump), expected, max_gap=0x80)

        top = report["assignments"][0]
        self.assertEqual(top["resolved_kda"], 1)
        self.assertEqual(top["resolved_gold"], 1)


if __name__ == "__main__":
    unittest.main()
