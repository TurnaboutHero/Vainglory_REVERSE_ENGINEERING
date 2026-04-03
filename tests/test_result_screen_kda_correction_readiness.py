import json
import tempfile
import unittest
from pathlib import Path

from vg.tools.result_screen_kda_correction_readiness import (
    build_result_screen_kda_correction_readiness,
)


class TestResultScreenKdaCorrectionReadiness(unittest.TestCase):
    def test_readiness_classifies_session_missing_result_dump(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory_root = Path(tmp) / "memory_sessions"
            session = memory_root / "probe"
            session.mkdir(parents=True)
            (session / "manifest.json").write_text(json.dumps({"replay_name": "sample"}), encoding="utf-8")
            output_root = Path(tmp) / "output"
            output_root.mkdir()

            report = build_result_screen_kda_correction_readiness(str(memory_root), str(output_root))

        self.assertEqual(report["rows"][0]["status"], "missing_result_dump")

    def test_readiness_marks_already_corrected_exported_for_decoded_only_replay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory_root = Path(tmp) / "memory_sessions"
            memory_root.mkdir()
            output_root = Path(tmp) / "output"
            output_root.mkdir()
            (output_root / "debug.json").write_text(
                json.dumps({"safe_output": {"replay_name": "sample", "replay_file": "sample.0.vgr", "players": []}}),
                encoding="utf-8",
            )
            (output_root / "export.json").write_text(
                json.dumps(
                    {
                        "schema_version": "decoder_v2.index_export.v2",
                        "matches": [
                            {"replay_name": "sample", "kda_correction": {"applied": True}},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            report = build_result_screen_kda_correction_readiness(str(memory_root), str(output_root))

        self.assertEqual(report["rows"][0]["status"], "already_corrected_exported")


if __name__ == "__main__":
    unittest.main()
