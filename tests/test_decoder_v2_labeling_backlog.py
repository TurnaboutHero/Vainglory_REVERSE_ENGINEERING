import json
import tempfile
import unittest
from pathlib import Path

from vg.decoder_v2.labeling_backlog import build_labeling_backlog


class TestDecoderV2LabelingBacklog(unittest.TestCase):
    def test_build_labeling_backlog_groups_missing_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir) / "replays"
            covered_dir = base / "covered"
            manifest_dir = base / "manifest_only"
            raw_dir = base / "raw_only"
            covered_dir.mkdir(parents=True)
            manifest_dir.mkdir(parents=True)
            raw_dir.mkdir(parents=True)
            (covered_dir / "sample.0.vgr").touch()
            (covered_dir / "result.png").touch()
            (manifest_dir / "other.0.vgr").touch()
            (manifest_dir / "replayManifest-abc.txt").touch()
            (raw_dir / "raw.0.vgr").touch()

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

            report = build_labeling_backlog(str(base), str(truth_path))

        self.assertEqual(report["summary"]["covered_directories"], 1)
        self.assertEqual(report["summary"]["manifest_only"], 1)
        self.assertEqual(report["summary"]["raw_only"], 1)


if __name__ == "__main__":
    unittest.main()
