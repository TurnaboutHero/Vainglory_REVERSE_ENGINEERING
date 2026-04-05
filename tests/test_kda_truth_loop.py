import json
import tempfile
import unittest
from pathlib import Path

from vg.tools.kda_truth_loop import build_kda_truth_loop_report


class TestKdaTruthLoop(unittest.TestCase):
    def test_build_kda_truth_loop_report_creates_next_capture_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            replay_dir = root / "replays" / "finals2"
            replay_dir.mkdir(parents=True)
            replay_file = replay_dir / "sample.0.vgr"
            replay_file.write_bytes(b"test")

            memory_root = root / "memory_sessions"
            output_root = root / "output"
            output_root.mkdir()
            truth = root / "truth.json"
            truth.write_text(json.dumps({"matches": []}), encoding="utf-8")

            pipeline_report = {
                "bundled_session_count": 0,
                "failed_session_count": 0,
                "backlog": {
                    "row_count": 1,
                    "rows": [
                        {
                            "replay_name": "sample-replay",
                            "priority": 1,
                            "reason": ["truth_residual:p1:kills"],
                            "replay_file": str(replay_file),
                        }
                    ],
                },
                "readiness": {"rows": []},
            }

            from unittest.mock import patch

            with patch("vg.tools.kda_truth_loop.build_result_screen_kda_correction_pipeline", return_value=pipeline_report):
                report = build_kda_truth_loop_report(
                    str(memory_root),
                    str(output_root),
                    truth_path=str(truth),
                    session_output_root=str(memory_root),
                )

                next_capture = report["next_capture"]
                self.assertIsNotNone(next_capture)
                self.assertTrue(next_capture["manifest_created"])
                self.assertTrue(Path(next_capture["manifest_path"]).exists())

    def test_build_kda_truth_loop_report_resolves_replay_file_from_decoded_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            replay_dir = root / "replays" / "semi2"
            replay_dir.mkdir(parents=True)
            replay_file = replay_dir / "semi.0.vgr"
            replay_file.write_bytes(b"test")

            memory_root = root / "memory_sessions"
            output_root = root / "output"
            output_root.mkdir()
            truth = root / "truth.json"
            truth.write_text(json.dumps({"matches": []}), encoding="utf-8")

            decoded_payload = output_root / "decoded.json"
            decoded_payload.write_text(
                json.dumps(
                    {
                        "safe_output": {
                            "replay_name": "decoded-only-replay",
                            "replay_file": str(replay_file),
                        }
                    }
                ),
                encoding="utf-8",
            )

            pipeline_report = {
                "bundled_session_count": 0,
                "failed_session_count": 0,
                "backlog": {
                    "row_count": 1,
                    "rows": [
                        {
                            "replay_name": "decoded-only-replay",
                            "priority": 3,
                            "reason": ["decoded_payload_available_no_result_dump"],
                            "replay_file": None,
                        }
                    ],
                },
                "readiness": {
                    "rows": [
                        {
                            "replay_name": "decoded-only-replay",
                            "decoded_payload_path": str(decoded_payload),
                        }
                    ]
                },
            }

            from unittest.mock import patch

            with patch("vg.tools.kda_truth_loop.build_result_screen_kda_correction_pipeline", return_value=pipeline_report):
                report = build_kda_truth_loop_report(
                    str(memory_root),
                    str(output_root),
                    truth_path=str(truth),
                    session_output_root=str(memory_root),
                )
                next_capture = report["next_capture"]
                self.assertEqual(next_capture["replay_file"], str(replay_file))
                self.assertTrue(next_capture["manifest_created"])


if __name__ == "__main__":
    unittest.main()
