import tempfile
import unittest
from pathlib import Path

from vg.tools.result_screen_unique_kda_reconstruction import build_result_screen_unique_kda_reconstruction


def _build_unique_kda_dump() -> bytes:
    import struct
    from vg.tools.minidump_parser import MINIDUMP_SIGNATURE

    blob = "12/1/4".encode("utf-16-le") + b"\x00" * 16 + "2/5/2".encode("utf-16-le")
    header = struct.pack("<IIIIIIQ", MINIDUMP_SIGNATURE, 0x0000A793, 1, 32, 0, 0, 0)
    stream = struct.pack("<III", 9, 32, 44)
    memory64 = struct.pack("<QQQQ", 1, 76, 0x4000, len(blob))
    return header + stream + memory64 + blob


class TestResultScreenUniqueKDAReconstruction(unittest.TestCase):
    def test_build_result_screen_unique_kda_reconstruction_marks_only_unique_kdas(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dump = Path(tmp) / "sample.dmp"
            dump.write_bytes(_build_unique_kda_dump())
            expected = [
                {"name": "a", "team": "left", "kills": 12, "deaths": 1, "assists": 4},
                {"name": "b", "team": "right", "kills": 2, "deaths": 5, "assists": 2},
                {"name": "c", "team": "right", "kills": 2, "deaths": 5, "assists": 2},
            ]
            report = build_result_screen_unique_kda_reconstruction(str(dump), expected)

        reconstructable = [row["name"] for row in report["player_rows"] if row["auto_reconstructable"]]
        self.assertEqual(reconstructable, ["a"])


if __name__ == "__main__":
    unittest.main()
