"""Parse basic minidump headers, streams, and memory ranges."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path
from typing import Dict, List, Optional


MINIDUMP_SIGNATURE = 0x504D444D  # 'MDMP'
STREAM_TYPE_NAMES = {
    0: "UnusedStream",
    1: "ReservedStream0",
    2: "ReservedStream1",
    3: "ThreadListStream",
    4: "ModuleListStream",
    5: "MemoryListStream",
    6: "ExceptionStream",
    7: "SystemInfoStream",
    8: "ThreadExListStream",
    9: "Memory64ListStream",
    10: "CommentStreamA",
    11: "CommentStreamW",
    12: "HandleDataStream",
    13: "FunctionTableStream",
    14: "UnloadedModuleListStream",
    15: "MiscInfoStream",
    16: "MemoryInfoListStream",
    17: "ThreadInfoListStream",
    18: "HandleOperationListStream",
    19: "TokenStream",
    20: "JavaScriptDataStream",
    21: "SystemMemoryInfoStream",
    22: "ProcessVmCountersStream",
    23: "IptTraceStream",
    24: "ThreadNamesStream",
}


def parse_minidump_header(data: bytes) -> Dict[str, object]:
    if len(data) < 32:
        raise ValueError("Data too short for MINIDUMP_HEADER")
    signature, version, stream_count, stream_dir_rva, checksum, timestamp, flags = struct.unpack_from("<IIIIIIQ", data, 0)
    if signature != MINIDUMP_SIGNATURE:
        raise ValueError(f"Invalid minidump signature: 0x{signature:08X}")
    return {
        "signature_hex": f"0x{signature:08X}",
        "version_hex": f"0x{version:08X}",
        "stream_count": stream_count,
        "stream_directory_rva": stream_dir_rva,
        "checksum": checksum,
        "timestamp": timestamp,
        "flags_hex": f"0x{flags:016X}",
    }


def parse_minidump_streams(data: bytes) -> List[Dict[str, object]]:
    header = parse_minidump_header(data)
    streams = []
    directory_rva = int(header["stream_directory_rva"])
    for index in range(int(header["stream_count"])):
        offset = directory_rva + (index * 12)
        if offset + 12 > len(data):
            raise ValueError("Stream directory extends beyond file size")
        stream_type, data_size, rva = struct.unpack_from("<III", data, offset)
        streams.append(
            {
                "index": index,
                "stream_type": stream_type,
                "stream_name": STREAM_TYPE_NAMES.get(stream_type, f"StreamType{stream_type}"),
                "data_size": data_size,
                "rva": rva,
            }
        )
    return streams


def _find_stream(streams: List[Dict[str, object]], stream_type: int) -> Optional[Dict[str, object]]:
    for stream in streams:
        if int(stream["stream_type"]) == stream_type:
            return stream
    return None


def parse_memory_ranges(data: bytes) -> List[Dict[str, object]]:
    streams = parse_minidump_streams(data)
    memory64 = _find_stream(streams, 9)
    if memory64 is not None:
        rva = int(memory64["rva"])
        if rva + 16 > len(data):
            raise ValueError("Memory64List stream header truncated")
        range_count, base_rva = struct.unpack_from("<QQ", data, rva)
        cursor = rva + 16
        file_rva = base_rva
        ranges = []
        for index in range(range_count):
            if cursor + 16 > len(data):
                raise ValueError("Memory64List stream truncated")
            start_va, size = struct.unpack_from("<QQ", data, cursor)
            ranges.append(
                {
                    "index": index,
                    "virtual_address": start_va,
                    "size": size,
                    "file_rva": file_rva,
                }
            )
            file_rva += size
            cursor += 16
        return ranges

    memory = _find_stream(streams, 5)
    if memory is None:
        return []
    rva = int(memory["rva"])
    if rva + 4 > len(data):
        raise ValueError("MemoryList stream header truncated")
    range_count = struct.unpack_from("<I", data, rva)[0]
    cursor = rva + 4
    ranges = []
    for index in range(range_count):
        if cursor + 16 > len(data):
            raise ValueError("MemoryList stream truncated")
        start_va, data_size, file_rva = struct.unpack_from("<QII", data, cursor)
        ranges.append(
            {
                "index": index,
                "virtual_address": start_va,
                "size": data_size,
                "file_rva": file_rva,
            }
        )
        cursor += 16
    return ranges


def map_file_offset_to_va(ranges: List[Dict[str, object]], file_offset: int) -> Optional[int]:
    for row in ranges:
        start = int(row["file_rva"])
        end = start + int(row["size"])
        if start <= file_offset < end:
            return int(row["virtual_address"]) + (file_offset - start)
    return None


def build_minidump_layout_report(dump_path: str) -> Dict[str, object]:
    path = Path(dump_path)
    data = path.read_bytes()
    header = parse_minidump_header(data)
    streams = parse_minidump_streams(data)
    ranges = parse_memory_ranges(data)
    return {
        "dump_path": str(path.resolve()),
        "size_bytes": len(data),
        "header": header,
        "streams": streams,
        "memory_range_count": len(ranges),
        "memory_ranges_sample": ranges[:50],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse a minidump header, streams, and memory ranges.")
    parser.add_argument("--dump", required=True, help="Minidump path")
    parser.add_argument("-o", "--output", help="Optional output JSON path")
    args = parser.parse_args()

    report = build_minidump_layout_report(args.dump)
    payload = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"Minidump layout report saved to {args.output}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
