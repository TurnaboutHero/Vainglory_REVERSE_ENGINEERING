import tempfile
import unittest
from pathlib import Path

from vg.tools.minidump_string_locator import locate_strings_in_minidump


def _build_locator_dump() -> bytes:
    import struct
    from vg.tools.minidump_parser import MINIDUMP_SIGNATURE

    text = "8815_DIOR".encode("utf-16-le")
    blob = text + b"\x00" * (64 - len(text))
    header = struct.pack("<IIIIIIQ", MINIDUMP_SIGNATURE, 0x0000A793, 1, 32, 0, 0, 0)
    stream = struct.pack("<III", 9, 32, 44)
    memory64 = struct.pack("<QQQQ", 1, 76, 0x2000, len(blob))
    return header + stream + memory64 + blob


class TestMinidumpStringLocator(unittest.TestCase):
    def test_locate_strings_in_minidump_maps_virtual_address(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dump = Path(tmp) / "sample.dmp"
            dump.write_bytes(_build_locator_dump())
            report = locate_strings_in_minidump(str(dump), ["8815_DIOR"])

        hit = report["strings"][0]["hits"][0]
        self.assertEqual(hit["virtual_address"], 0x2000)


if __name__ == "__main__":
    unittest.main()
