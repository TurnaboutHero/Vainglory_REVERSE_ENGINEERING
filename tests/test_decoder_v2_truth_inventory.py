import json
import tempfile
import unittest
from pathlib import Path

from vg.decoder_v2.truth_inventory import build_truth_inventory


class TestDecoderV2TruthInventory(unittest.TestCase):
    def test_build_truth_inventory_reports_covered_and_missing_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir) / "replays"
            covered_dir = base / "covered"
            missing_dir = base / "missing"
            covered_dir.mkdir(parents=True)
            missing_dir.mkdir(parents=True)
            (covered_dir / "result.png").touch()
            (covered_dir / "sample.0.vgr").touch()
            (missing_dir / "other.0.vgr").touch()
            (missing_dir / "replayManifest-abc.txt").touch()

            truth_path = Path(temp_dir) / "truth.json"
            truth_path.write_text(
                json.dumps(
                    {
                        "matches": [
                            {
                                "replay_name": "sample",
                                "replay_file": str(covered_dir / "sample.0.vgr"),
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            report = build_truth_inventory(str(base), str(truth_path))

        self.assertEqual(report["total_replay_directories"], 2)
        self.assertEqual(report["covered_directories"], 1)
        self.assertEqual(report["missing_directories"], 1)
        self.assertEqual(report["directories_with_result_images"], 1)
        self.assertEqual(report["directories_with_manifest"], 1)


if __name__ == "__main__":
    unittest.main()
