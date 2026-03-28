import tempfile
import unittest
from pathlib import Path

from vg.tools.dump_string_diff import build_dump_string_diff, extract_strings_from_bytes


class TestDumpStringDiff(unittest.TestCase):
    def test_extract_strings_from_bytes_reads_ascii_and_utf16(self) -> None:
        payload = b"hello_world\x00noise" + "PLAYER_ONE".encode("utf-16-le")
        values = extract_strings_from_bytes(payload)
        self.assertIn("hello_world", values)
        self.assertIn("PLAYER_ONE", values)

    def test_build_dump_string_diff_reports_added_and_removed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            before = Path(tmp) / "before.dmp"
            after = Path(tmp) / "after.dmp"
            before.write_bytes(b"alpha bravo charlie")
            after.write_bytes(b"alpha delta echo")
            report = build_dump_string_diff(str(before), str(after))
        self.assertGreater(report["added_count"], 0)
        self.assertGreater(report["removed_count"], 0)


if __name__ == "__main__":
    unittest.main()
