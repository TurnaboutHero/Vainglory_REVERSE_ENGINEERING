import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vg.decoder_v2.minion_research import build_minion_research_report


class TestDecoderV2MinionResearch(unittest.TestCase):
    def test_build_minion_research_report_summarizes_features(self) -> None:
        truth_payload = {
            "matches": [
                {
                    "replay_name": "sample",
                    "replay_file": str(Path("C:/fake/1/sample.0.vgr")),
                    "players": {"player1": {"minion_kills": 5}},
                }
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            truth_path = Path(temp_dir) / "truth.json"
            truth_path.write_text(json.dumps(truth_payload), encoding="utf-8")

            with patch("vg.decoder_v2.minion_research._load_player_credit_counters", return_value={"player1": { (0x0E, 1.0): 4, (0x0F, 1.0): 4, (0x0D, 1.0): 2}}), patch(
                "vg.decoder_v2.minion_research._load_player_action_counters",
                return_value={"player1": {0x05: 10}},
            ), patch(
                "vg.decoder_v2.minion_research.compare_minion_candidates_to_truth",
                return_value={"replay_name": "sample", "rows": []},
            ):
                report = build_minion_research_report(str(truth_path))

        self.assertIn("feature_summary", report)
        self.assertIn("0E@1.0", report["feature_summary"])
        self.assertEqual(report["feature_summary"]["0E@1.0"]["count"], 1)


if __name__ == "__main__":
    unittest.main()
