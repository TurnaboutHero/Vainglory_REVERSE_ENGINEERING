import struct
import tempfile
import unittest
from pathlib import Path

from vg.tools.minidump_parser import (
    MINIDUMP_SIGNATURE,
    build_minidump_layout_report,
    map_file_offset_to_va,
    parse_memory_ranges,
    parse_minidump_header,
    parse_minidump_streams,
)


def _build_synthetic_memory64_dump() -> bytes:
    # Header: 1 stream, directory at 32, one Memory64List stream at 44.
    signature = MINIDUMP_SIGNATURE
    version = 0x0000A793
    stream_count = 1
    stream_dir_rva = 32
    checksum = 0
    timestamp = 0
    flags = 0
    header = struct.pack("<IIIIIIQ", signature, version, stream_count, stream_dir_rva, checksum, timestamp, flags)
    stream = struct.pack("<III", 9, 32, 44)
    memory64 = struct.pack("<QQQQ", 1, 76, 0x1000, 8)
    memory_blob = b"ABCDEFGH"
    return header + stream + memory64 + memory_blob


class TestMinidumpParser(unittest.TestCase):
    def test_parse_memory64_stream(self) -> None:
        data = _build_synthetic_memory64_dump()
        header = parse_minidump_header(data)
        streams = parse_minidump_streams(data)
        ranges = parse_memory_ranges(data)

        self.assertEqual(header["stream_count"], 1)
        self.assertEqual(streams[0]["stream_type"], 9)
        self.assertEqual(ranges[0]["virtual_address"], 0x1000)
        self.assertEqual(ranges[0]["file_rva"], 76)
        self.assertEqual(map_file_offset_to_va(ranges, 79), 0x1003)

    def test_build_minidump_layout_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dump = Path(tmp) / "sample.dmp"
            dump.write_bytes(_build_synthetic_memory64_dump())
            report = build_minidump_layout_report(str(dump))

        self.assertEqual(report["memory_range_count"], 1)
        self.assertEqual(report["memory_ranges_sample"][0]["virtual_address"], 0x1000)


if __name__ == "__main__":
    unittest.main()
