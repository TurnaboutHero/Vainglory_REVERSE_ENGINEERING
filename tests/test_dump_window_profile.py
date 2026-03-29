import tempfile
import unittest
from pathlib import Path

from vg.tools.dump_window_profile import build_dump_window_profile


class TestDumpWindowProfile(unittest.TestCase):
    def test_build_dump_window_profile_summarizes_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dump = Path(tmp) / "sample.dmp"
            dump.write_bytes(b"ABCD1234\x00\x00WXYZ5678")
            report = build_dump_window_profile(str(dump), 0, length=16)

        self.assertEqual(report["window_start"], 0)
        self.assertEqual(report["length"], 16)
        self.assertGreater(report["printable_ratio"], 0.5)
        self.assertTrue(report["strings"])


if __name__ == "__main__":
    unittest.main()
