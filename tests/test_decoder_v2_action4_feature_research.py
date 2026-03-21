import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vg.decoder_v2.action4_feature_research import build_action4_feature_report


class TestDecoderV2Action4FeatureResearch(unittest.TestCase):
    def test_build_action4_feature_report_summarizes_values(self) -> None:
        truth_payload = {
            "matches": [
                {
                    "replay_name": f"sample{i}",
                    "replay_file": f"sample{i}.0.vgr",
                    "players": {"player1": {"minion_kills": 5}},
                }
                for i in range(5)
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            truth_path = Path(temp_dir) / "truth.json"
            truth_path.write_text(json.dumps(truth_payload), encoding="utf-8")

            parsed = {
                "teams": {
                    "left": [{"name": "player1", "entity_id": 0x1234}],
                    "right": [],
                }
            }

            with patch("vg.core.vgr_parser.VGRParser") as parser_cls, patch(
                "vg.decoder_v2.action4_feature_research._load_action4_value_counters",
                return_value={0x3412: {46.0: 5}},
            ), patch(
                "vg.decoder_v2.minions.collect_minion_candidates"
            ) as minion_mock:
                parser_cls.return_value.parse.return_value = parsed
                minion_mock.return_value = [type("C", (), {"player_name": "player1", "action_0e_value_1": 4})()]
                report = build_action4_feature_report(str(truth_path))

        self.assertEqual(report["top_action4_values_vs_truth"][0]["value"], 46.0)
        self.assertEqual(report["top_action4_values_vs_residual"][0]["value"], 46.0)


if __name__ == "__main__":
    unittest.main()
