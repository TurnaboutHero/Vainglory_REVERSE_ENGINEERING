import tempfile
import unittest
from pathlib import Path

from vg.tools.result_screen_cluster_candidates import build_result_screen_cluster_candidates


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


class TestResultScreenClusterCandidates(unittest.TestCase):
    def test_build_result_screen_cluster_candidates_scores_expected_cluster(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dump = Path(tmp) / "sample.dmp"
            dump.write_bytes(_build_cluster_dump())
            expected = [{"name": "8815_DIOR", "team": "left", "kills": 12, "deaths": 1, "assists": 4, "gold": "13.8k"}]
            report = build_result_screen_cluster_candidates(str(dump), expected, max_gap=0x80)

        self.assertEqual(report["candidate_count"], 1)
        cand = report["candidates"][0]
        self.assertIn("8815_DIOR", cand["names"])
        self.assertIn("12/1/4", cand["kdas"])
        self.assertIn("13.8k", cand["golds"])


if __name__ == "__main__":
    unittest.main()
