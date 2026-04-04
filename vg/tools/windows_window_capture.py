"""Capture a specific Windows application window to an image file."""

from __future__ import annotations

import argparse
import ctypes
import json
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

from PIL import ImageGrab


def normalize_window_rect(left: int, top: int, right: int, bottom: int) -> Tuple[int, int, int, int]:
    if right <= left or bottom <= top:
        raise ValueError("Invalid window rect")
    return left, top, right, bottom


def build_window_capture_metadata(
    process_name: str,
    output_path: str,
    rect: Tuple[int, int, int, int],
) -> Dict[str, object]:
    left, top, right, bottom = rect
    return {
        "captured_at": datetime.now().isoformat(),
        "process_name": process_name,
        "output_path": str(Path(output_path).resolve()),
        "rect": {
            "left": left,
            "top": top,
            "right": right,
            "bottom": bottom,
            "width": right - left,
            "height": bottom - top,
        },
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
    if snapshot == ctypes.c_void_p(-1).value:
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


def _find_main_window_handle(pid: int) -> Optional[int]:
    user32 = ctypes.WinDLL("user32", use_last_error=True)

    handles = []
    rect = wintypes.RECT()

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum_proc(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        window_pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
        if int(window_pid.value) != pid:
            return True
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return True
        width = rect.right - rect.left
        height = rect.bottom - rect.top
        if width <= 0 or height <= 0:
            return True
        handles.append(int(hwnd))
        return True

    user32.EnumWindows(enum_proc, 0)
    return handles[0] if handles else None


def _get_window_rect(hwnd: int) -> Tuple[int, int, int, int]:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    rect = wintypes.RECT()
    ok = user32.GetWindowRect(hwnd, ctypes.byref(rect))
    if not ok:
        raise OSError(f"GetWindowRect failed: {ctypes.get_last_error()}")
    return normalize_window_rect(rect.left, rect.top, rect.right, rect.bottom)


def capture_window_by_process_name(process_name: str, output_path: str) -> Dict[str, object]:
    pid = _find_pid_by_name(process_name)
    if pid is None:
        raise FileNotFoundError(f"Process not found: {process_name}")
    hwnd = _find_main_window_handle(pid)
    if hwnd is None:
        raise FileNotFoundError(f"No visible main window found for: {process_name}")
    rect = _get_window_rect(hwnd)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    image = ImageGrab.grab(bbox=rect, all_screens=True)
    image.save(output)
    metadata = build_window_capture_metadata(process_name, str(output), rect)
    metadata["pid"] = pid
    metadata["hwnd"] = hwnd
    metadata["size_bytes"] = output.stat().st_size
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture a Windows application window to an image file.")
    parser.add_argument("--process-name", required=True, help="Process executable name, e.g. Vainglory.exe")
    parser.add_argument("--output", required=True, help="Output image path")
    args = parser.parse_args()

    metadata = capture_window_by_process_name(args.process_name, args.output)
    print(json.dumps(metadata, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
