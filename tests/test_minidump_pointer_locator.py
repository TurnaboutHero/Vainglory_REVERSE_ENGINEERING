import json
import struct
import tempfile
import unittest
from pathlib import Path

from vg.tools.minidump_parser import MINIDUMP_SIGNATURE
from vg.tools.minidump_pointer_locator import locate_pointers_in_minidump


def _build_pointer_dump() -> bytes:
    text = "8815_DIOR".encode("utf-16-le")
    # memory region starts at 0x3000; put pointer to 0x3000 at beginning
    blob = struct.pack("<Q", 0x3000) + b"\x00" * 8 + text
    header = struct.pack("<IIIIIIQ", MINIDUMP_SIGNATURE, 0x0000A793, 1, 32, 0, 0, 0)
    stream = struct.pack("<III", 9, 32, 44)
    memory64 = struct.pack("<QQQQ", 1, 76, 0x3000, len(blob))
    return header + stream + memory64 + blob


class TestMinidumpPointerLocator(unittest.TestCase):
    def test_locate_pointers_in_minidump_maps_pointer_vas(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dump = Path(tmp) / "sample.dmp"
            dump.write_bytes(_build_pointer_dump())
            report = locate_pointers_in_minidump(str(dump), [{"label": "name", "virtual_address": 0x3000}])

        vas = [hit["pointer_va"] for hit in report["targets"][0]["pointer_hits"]]
        self.assertIn(0x3000, vas)


if __name__ == "__main__":
    unittest.main()
