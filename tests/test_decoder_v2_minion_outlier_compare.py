import unittest
from unittest.mock import patch

from vg.decoder_v2.minion_outlier_compare import build_minion_outlier_compare


class TestMinionOutlierCompare(unittest.TestCase):
    def test_build_minion_outlier_compare_contrasts_target_and_baseline(self) -> None:
        matches = [
            {"replay_name": "target", "replay_file": "C:/replays/target/target.0.vgr", "players": {}},
            {"replay_name": "ref1", "replay_file": "C:/replays/ref1/ref1.0.vgr", "players": {}},
            {"replay_name": "ref2", "replay_file": "C:/replays/ref2/ref2.0.vgr", "players": {}},
        ]
        reports = [
            {
                "aggregate": {
                    "positive_residual_players": 7,
                    "positive_target_samples": 100,
                    "nonpositive_target_samples": 20,
                    "positive_header_summary": [{"header_hex": "28043f", "count": 60}],
                    "positive_credit_pattern_summary": [{"pattern": "0x02@14.34", "count": 50}],
                }
            },
            {
                "aggregate": {
                    "positive_residual_players": 0,
                    "positive_target_samples": 0,
                    "nonpositive_target_samples": 200,
                    "positive_header_summary": [],
                    "nonpositive_header_summary": [{"header_hex": "28043f", "count": 40}],
                    "positive_credit_pattern_summary": [],
                    "nonpositive_credit_pattern_summary": [{"pattern": "0x02@14.34", "count": 10}],
                }
            },
            {
                "aggregate": {
                    "positive_residual_players": 0,
                    "positive_target_samples": 0,
                    "nonpositive_target_samples": 100,
                    "positive_header_summary": [],
                    "nonpositive_header_summary": [{"header_hex": "28043f", "count": 20}],
                    "positive_credit_pattern_summary": [],
                    "nonpositive_credit_pattern_summary": [{"pattern": "0x02@14.34", "count": 5}],
                }
            },
        ]

        with patch(
            "vg.decoder_v2.minion_outlier_compare._load_truth_matches",
            return_value=matches,
        ), patch(
            "vg.decoder_v2.minion_outlier_compare.build_minion_window_report",
            side_effect=reports,
        ):
            report = build_minion_outlier_compare("truth.json", "target")

        self.assertEqual(report["target_replay_name"], "target")
        self.assertEqual(report["reference_match_count"], 2)
        self.assertEqual(report["header_rate_deltas"][0]["header_hex"], "28043f")
        self.assertEqual(report["credit_pattern_rate_deltas"][0]["pattern"], "0x02@14.34")


if __name__ == "__main__":
    unittest.main()
