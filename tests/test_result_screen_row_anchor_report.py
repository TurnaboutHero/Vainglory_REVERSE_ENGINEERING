import json
import tempfile
import unittest
from pathlib import Path

from vg.tools.result_screen_row_anchor_report import build_result_screen_row_anchor_report


def _build_anchor_dump() -> bytes:
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


class TestResultScreenRowAnchorReport(unittest.TestCase):
    def test_build_result_screen_row_anchor_report_scores_nearby_stats(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dump = Path(tmp) / "sample.dmp"
            expected = Path(tmp) / "expected.json"
            dump.write_bytes(_build_anchor_dump())
            expected.write_text(
                '[{"name":"8815_DIOR","team":"left","hero_name":"Baron","kills":12,"deaths":1,"assists":4,"gold":"13.8k"}]',
                encoding="utf-8",
            )
            report = build_result_screen_row_anchor_report(str(dump), json.loads(expected.read_text(encoding="utf-8")), max_distance=0x80)

        anchor = report["rows"][0]["anchor"]
        self.assertIsNotNone(anchor)
        self.assertIsNotNone(anchor["kda_distance"])
        self.assertIsNotNone(anchor["gold_distance"])


if __name__ == "__main__":
    unittest.main()
