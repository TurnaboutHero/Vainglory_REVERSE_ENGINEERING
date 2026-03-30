import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vg.tools.result_screen_kda_correction_pipeline import build_result_screen_kda_correction_pipeline


def _build_kda_dump() -> bytes:
    import struct
    from vg.tools.minidump_parser import MINIDUMP_SIGNATURE

    blob = (
        "12/1/4".encode("utf-16-le")
        + b"\x00" * 16
        + "2/5/2".encode("utf-16-le")
        + b"\x00" * 16
        + "2/5/2".encode("utf-16-le")
    )
    header = struct.pack("<IIIIIIQ", MINIDUMP_SIGNATURE, 0x0000A793, 1, 32, 0, 0, 0)
    stream = struct.pack("<III", 9, 32, 44)
    memory64 = struct.pack("<QQQQ", 1, 76, 0x4000, len(blob))
    return header + stream + memory64 + blob


class TestResultScreenKdaCorrectionPipeline(unittest.TestCase):
    def test_pipeline_bundles_session_and_builds_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory_sessions = root / "memory_sessions"
            session = memory_sessions / "probe"
            dumps = session / "dumps"
            dumps.mkdir(parents=True)
            (dumps / "result_screen_full.dmp").write_bytes(_build_kda_dump())
            (session / "manifest.json").write_text(
                json.dumps({"replay_name": "sample-replay"}),
                encoding="utf-8",
            )
            decoded = root / "target_replay_decoder_v2_debug.json"
            decoded.write_text(
                json.dumps(
                    {
                        "safe_output": {
                            "replay_name": "sample-replay",
                            "replay_file": "sample.0.vgr",
                            "players": [
                                {"name": "a", "team": "left", "kills": 12, "deaths": 1, "assists": 4},
                                {"name": "b", "team": "right", "kills": 2, "deaths": 5, "assists": 2},
                                {"name": "c", "team": "right", "kills": 2, "deaths": 5, "assists": 2},
                            ],
                        }
                    }
                ),
                encoding="utf-8",
            )

            with patch("vg.tools.result_screen_kda_correction_pipeline.build_index_ready_export") as mocked_export:
                mocked_export.return_value = {"matches": [], "kda_correction_summary": {}}
                report = build_result_screen_kda_correction_pipeline(
                    str(memory_sessions),
                    str(root),
                    export_base_path="dummy",
                )

        self.assertEqual(report["bundled_session_count"], 1)
        self.assertEqual(report["failed_session_count"], 0)
        self.assertEqual(report["inventory"]["preferred_correction_count"], 1)
        self.assertIsNotNone(report["export"])


if __name__ == "__main__":
    unittest.main()
