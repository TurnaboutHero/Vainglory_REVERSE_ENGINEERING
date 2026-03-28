"""Create Windows minidumps for a target process without external dependencies."""

from __future__ import annotations

import argparse
import ctypes
import json
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional


PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
GENERIC_WRITE = 0x40000000
CREATE_ALWAYS = 2
FILE_ATTRIBUTE_NORMAL = 0x80
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

DUMP_TYPE_FLAGS = {
    "normal": 0x00000000,
    "data-segs": 0x00000001,
    "full-memory": 0x00000002,
    "handle-data": 0x00000004,
    "thread-info": 0x00001000,
    "indirect-memory": 0x00000040,
    "scan-memory": 0x00000010,
}
DUMP_MODE_PRESETS = {
    "normal": DUMP_TYPE_FLAGS["normal"],
    "lean": (
        DUMP_TYPE_FLAGS["data-segs"]
        | DUMP_TYPE_FLAGS["handle-data"]
        | DUMP_TYPE_FLAGS["thread-info"]
        | DUMP_TYPE_FLAGS["indirect-memory"]
    ),
    "full": DUMP_TYPE_FLAGS["full-memory"] | DUMP_TYPE_FLAGS["thread-info"],
}


def dump_mode_flag(mode: str) -> int:
    if mode not in DUMP_MODE_PRESETS:
        raise ValueError(f"Unsupported dump mode: {mode}")
    return DUMP_MODE_PRESETS[mode]


def build_dump_metadata(pid: int, process_name: str, output_path: str, mode: str) -> Dict[str, object]:
    return {
        "captured_at": datetime.now().isoformat(),
        "pid": pid,
        "process_name": process_name,
        "output_path": str(Path(output_path).resolve()),
        "mode": mode,
        "dump_flags_hex": f"0x{dump_mode_flag(mode):08X}",
    }


def _find_pid_by_name(process_name: str) -> Optional[int]:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    TH32CS_SNAPPROCESS = 0x00000002

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == INVALID_HANDLE_VALUE:
        return None
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        found = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while found:
            if entry.szExeFile.lower() == process_name.lower():
                return int(entry.th32ProcessID)
            found = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return None


def create_minidump(pid: int, output_path: str, mode: str = "lean") -> Dict[str, object]:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    dbghelp = ctypes.WinDLL("Dbghelp", use_last_error=True)

    process_handle = kernel32.OpenProcess(
        PROCESS_QUERY_INFORMATION | PROCESS_VM_READ,
        False,
        pid,
    )
    if not process_handle:
        raise OSError(f"OpenProcess failed for pid={pid}: {ctypes.get_last_error()}")

    file_handle = kernel32.CreateFileW(
        str(output),
        GENERIC_WRITE,
        0,
        None,
        CREATE_ALWAYS,
        FILE_ATTRIBUTE_NORMAL,
        None,
    )
    if file_handle == INVALID_HANDLE_VALUE:
        kernel32.CloseHandle(process_handle)
        raise OSError(f"CreateFileW failed for {output}: {ctypes.get_last_error()}")

    try:
        dbghelp.MiniDumpWriteDump.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.LPVOID,
            wintypes.LPVOID,
        ]
        dbghelp.MiniDumpWriteDump.restype = wintypes.BOOL

        success = dbghelp.MiniDumpWriteDump(
            process_handle,
            pid,
            file_handle,
            dump_mode_flag(mode),
            None,
            None,
            None,
        )
        if not success:
            raise OSError(f"MiniDumpWriteDump failed: {ctypes.get_last_error()}")
    finally:
        kernel32.CloseHandle(file_handle)
        kernel32.CloseHandle(process_handle)

    process_name = _resolve_process_name(pid) or f"pid-{pid}"
    metadata = build_dump_metadata(pid, process_name, str(output), mode)
    metadata["size_bytes"] = output.stat().st_size
    return metadata


def _resolve_process_name(pid: int) -> Optional[str]:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        QueryFullProcessImageNameW = kernel32.QueryFullProcessImageNameW
        QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        QueryFullProcessImageNameW.restype = wintypes.BOOL
        buffer_len = wintypes.DWORD(260)
        buffer = ctypes.create_unicode_buffer(buffer_len.value)
        ok = QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(buffer_len))
        if not ok:
            return None
        return Path(buffer.value).name
    finally:
        kernel32.CloseHandle(handle)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a Windows minidump for a process.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pid", type=int, help="Target process id")
    group.add_argument("--process-name", help="Target process executable name, e.g. Vainglory.exe")
    parser.add_argument("--output", required=True, help="Output .dmp file path")
    parser.add_argument(
        "--mode",
        choices=sorted(DUMP_MODE_PRESETS.keys()),
        default="lean",
        help="Dump mode preset",
    )
    args = parser.parse_args()

    pid = args.pid
    if pid is None:
        pid = _find_pid_by_name(str(args.process_name))
        if pid is None:
            raise SystemExit(f"Process not found: {args.process_name}")

    metadata = create_minidump(pid, args.output, mode=args.mode)
    print(json.dumps(metadata, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
