import tempfile
import unittest
from pathlib import Path

from vg.tools.result_screen_va_cluster_report import build_result_screen_va_cluster_report


def _build_va_cluster_dump() -> bytes:
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


class TestResultScreenVAClusterReport(unittest.TestCase):
    def test_build_result_screen_va_cluster_report_groups_close_strings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dump = Path(tmp) / "sample.dmp"
            dump.write_bytes(_build_va_cluster_dump())
            report = build_result_screen_va_cluster_report(str(dump), ["8815_DIOR", "12/1/4", "13.8k"], max_gap=0x80)

        self.assertEqual(report["cluster_count"], 1)
        self.assertEqual(set(report["clusters"][0]["distinct_values"]), {"8815_DIOR", "12/1/4", "13.8k"})


if __name__ == "__main__":
    unittest.main()
