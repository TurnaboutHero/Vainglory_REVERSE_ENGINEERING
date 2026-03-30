import tempfile
import unittest
from pathlib import Path

from vg.tools.result_screen_kda_correction_report import build_result_screen_kda_correction_report


def _build_kda_dump() -> bytes:
    import struct
    from vg.tools.minidump_parser import MINIDUMP_SIGNATURE

    blob = (
        "12/1/4".encode("utf-16-le")
        + b"\x00" * 16
        + "2/5/2".encode("utf-16-le")
        + b"\x00" * 16
        + "2/5/2".encode("utf-16-le")
    )
    header = struct.pack("<IIIIIIQ", MINIDUMP_SIGNATURE, 0x0000A793, 1, 32, 0, 0, 0)
    stream = struct.pack("<III", 9, 32, 44)
    memory64 = struct.pack("<QQQQ", 1, 76, 0x4000, len(blob))
    return header + stream + memory64 + blob


class TestResultScreenKdaCorrectionReport(unittest.TestCase):
    def test_report_distinguishes_name_bound_and_group_confirmable_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dump = Path(tmp) / "sample.dmp"
            dump.write_bytes(_build_kda_dump())
            expected = [
                {"name": "a", "team": "left", "kills": 12, "deaths": 1, "assists": 4},
                {"name": "b", "team": "right", "kills": 2, "deaths": 5, "assists": 2},
                {"name": "c", "team": "right", "kills": 2, "deaths": 5, "assists": 2},
            ]

            report = build_result_screen_kda_correction_report(str(dump), expected)

        self.assertEqual(report["name_bound_reconstructable_rows"], 1)
        self.assertEqual(report["group_confirmable_rows"], 3)
        self.assertEqual(sorted(report["unresolved_name_bound_rows"]), ["b", "c"])


if __name__ == "__main__":
    unittest.main()
