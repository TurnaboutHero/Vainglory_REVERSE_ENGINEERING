import json
import tempfile
import unittest
from pathlib import Path

from vg.tools.result_screen_capture_queue import build_result_screen_capture_queue


class TestResultScreenCaptureQueue(unittest.TestCase):
    def test_queue_marks_captured_and_missing_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            replay_root = root / "replays"
            replay_root.mkdir()
            captured_replay = replay_root / "captured.0.vgr"
            captured_replay.write_bytes(b"1")
            missing_replay = replay_root / "missing.0.vgr"
            missing_replay.write_bytes(b"2")

            memory_root = root / "memory_sessions"
            session = memory_root / "capture_captured"
            dumps = session / "dumps"
            dumps.mkdir(parents=True)
            screenshots = session / "screenshots"
            screenshots.mkdir()
            (session / "manifest.json").write_text(
                json.dumps({"replay_name": "captured"}),
                encoding="utf-8",
            )
            (dumps / "result_screen_full.dmp").write_bytes(b"dump")
            (screenshots / "result_screen.png").write_bytes(b"img")

            report = build_result_screen_capture_queue(str(replay_root), str(memory_root))

        self.assertEqual(report["captured_count"], 1)
        self.assertEqual(report["missing_session_count"], 1)
        self.assertEqual(report["row_count"], 2)

    def test_queue_can_create_missing_session_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            replay_root = root / "replays"
            replay_root.mkdir()
            replay_file = replay_root / "demo.0.vgr"
            replay_file.write_bytes(b"1")
            memory_root = root / "memory_sessions"

            report = build_result_screen_capture_queue(
                str(replay_root),
                str(memory_root),
                create_missing_sessions=True,
                session_output_root=str(memory_root),
            )

            row = report["rows"][0]
            self.assertTrue(row["manifest_created"])
            self.assertTrue(Path(row["manifest_path"]).exists())
            self.assertEqual(row["status"], "session_prepared")

    def test_queue_ignores_macosx_sidecar_replays(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            replay_root = root / "replays"
            macosx_root = replay_root / "__MACOSX" / "series"
            macosx_root.mkdir(parents=True)
            (macosx_root / "._demo.0.vgr").write_bytes(b"1")
            actual_root = replay_root / "series"
            actual_root.mkdir()
            (actual_root / "demo.0.vgr").write_bytes(b"2")

            report = build_result_screen_capture_queue(str(replay_root), str(root / "memory_sessions"))

        self.assertEqual(report["row_count"], 1)
        self.assertEqual(report["rows"][0]["replay_name"], "demo")


if __name__ == "__main__":
    unittest.main()
