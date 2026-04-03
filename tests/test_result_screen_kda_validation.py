import json
import tempfile
import unittest
from pathlib import Path

from vg.tools.result_screen_kda_validation import build_result_screen_kda_validation


class TestResultScreenKdaValidation(unittest.TestCase):
    def test_validation_uses_result_screen_reference_when_truth_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory_root = Path(tmp) / "memory_sessions"
            session = memory_root / "probe" / "bundle"
            session.mkdir(parents=True)
            (session / "result_screen_kda_correction_merge.json").write_text(
                json.dumps(
                    {
                        "replay_name": "sample",
                        "players": [
                            {"name": "a", "kills": 1, "deaths": 2, "assists": 3},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            output_root = Path(tmp) / "output"
            output_root.mkdir()
            (output_root / "debug.json").write_text(
                json.dumps(
                    {
                        "safe_output": {
                            "replay_name": "sample",
                            "players": [{"name": "a", "kills": 1, "deaths": 2, "assists": 3}],
                        }
                    }
                ),
                encoding="utf-8",
            )
            truth = Path(tmp) / "truth.json"
            truth.write_text(json.dumps({"matches": []}), encoding="utf-8")

            report = build_result_screen_kda_validation(str(memory_root), str(output_root), str(truth))

        self.assertEqual(report["rows"][0]["reference_source"], "result_screen")
        self.assertEqual(report["rows"][0]["corrected_correct_rows"], 1)


if __name__ == "__main__":
    unittest.main()
