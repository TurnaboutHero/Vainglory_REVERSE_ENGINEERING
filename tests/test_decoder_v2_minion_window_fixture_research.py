import unittest
from unittest.mock import patch

from vg.decoder_v2.minion_window_fixture_research import build_minion_window_fixture_report


class TestMinionWindowFixtureResearch(unittest.TestCase):
    def test_build_minion_window_fixture_report_aggregates_match_reports(self) -> None:
        matches = [
            {"replay_name": "a", "replay_file": "C:/replays/1/a.0.vgr", "players": {}},
            {"replay_name": "b", "replay_file": "C:/replays/2/b.0.vgr", "players": {}},
            {"replay_name": "c", "replay_file": "C:/replays/Incomplete/c.0.vgr", "players": {}},
        ]
        reports = [
            {
                "aggregate": {
                    "positive_residual_players": 1,
                    "nonpositive_or_unknown_players": 1,
                    "positive_target_samples": 10,
                    "nonpositive_target_samples": 5,
                    "positive_header_summary": [{"header_hex": "28043f", "count": 8}],
                    "nonpositive_header_summary": [{"header_hex": "28043f", "count": 1}],
                    "positive_credit_pattern_summary": [{"pattern": "0x02@14.34", "count": 9}],
                    "nonpositive_credit_pattern_summary": [{"pattern": "0x03@1.0", "count": 20}],
                    "positive_enriched_headers": [{"header_hex": "28043f", "delta_per_target_event": 0.6}],
                    "positive_enriched_credit_patterns": [{"pattern": "0x02@14.34", "delta_per_target_event": 0.7}],
                }
            },
            {
                "aggregate": {
                    "positive_residual_players": 2,
                    "nonpositive_or_unknown_players": 0,
                    "positive_target_samples": 12,
                    "nonpositive_target_samples": 4,
                    "positive_header_summary": [{"header_hex": "28043f", "count": 10}],
                    "nonpositive_header_summary": [{"header_hex": "28043f", "count": 2}],
                    "positive_credit_pattern_summary": [{"pattern": "0x02@14.34", "count": 11}],
                    "nonpositive_credit_pattern_summary": [{"pattern": "0x03@1.0", "count": 4}],
                    "positive_enriched_headers": [{"header_hex": "28043f", "delta_per_target_event": 0.5}],
                    "positive_enriched_credit_patterns": [{"pattern": "0x02@14.34", "delta_per_target_event": 0.8}],
                }
            },
        ]

        with patch(
            "vg.decoder_v2.minion_window_fixture_research._load_truth_matches",
            return_value=matches,
        ), patch(
            "vg.decoder_v2.minion_window_fixture_research.build_minion_window_report",
            side_effect=reports,
        ):
            report = build_minion_window_fixture_report("truth.json")

        self.assertEqual(report["complete_fixture_matches"], 2)
        self.assertEqual(report["global_positive_target_samples"], 22)
        self.assertEqual(report["global_enriched_headers"][0]["header_hex"], "28043f")
        self.assertEqual(report["global_enriched_credit_patterns"][0]["pattern"], "0x02@14.34")


if __name__ == "__main__":
    unittest.main()
