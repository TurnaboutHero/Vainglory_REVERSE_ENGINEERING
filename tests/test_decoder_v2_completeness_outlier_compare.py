import unittest
from unittest.mock import patch

from vg.decoder_v2.completeness_outlier_compare import build_completeness_outlier_compare


class TestCompletenessOutlierCompare(unittest.TestCase):
    def test_build_completeness_outlier_compare_summarizes_reference_cohorts(self) -> None:
        audit = {
            "rows": [
                {
                    "replay_name": "target",
                    "replay_file": "target.0.vgr",
                    "status": "completeness_unknown",
                    "reason": "unknown",
                    "review_flags": ["crystal_player_death_gap_gt_60s", "generic_player_death_gap_gt_60s"],
                    "review_bucket": "conflicting_long_tail_signals",
                    "frame_count": 190,
                    "crystal_ts": 1500.0,
                    "max_player_death_ts": 1700.0,
                    "max_death_header_ts": 1900.0,
                    "max_item_ts": 1860.0,
                },
                {
                    "replay_name": "ref1",
                    "replay_file": "ref1.0.vgr",
                    "status": "complete_confirmed",
                    "reason": "ok",
                    "review_flags": ["crystal_player_death_gap_gt_60s", "generic_player_death_gap_gt_60s"],
                    "review_bucket": "review_ok",
                    "frame_count": 200,
                    "crystal_ts": 1900.0,
                    "max_player_death_ts": 1700.0,
                    "max_death_header_ts": 1910.0,
                    "max_item_ts": 1905.0,
                },
                {
                    "replay_name": "ref2",
                    "replay_file": "ref2.0.vgr",
                    "status": "complete_confirmed",
                    "reason": "ok",
                    "review_flags": ["complete_without_crystal"],
                    "review_bucket": "accepted_without_crystal",
                    "frame_count": 130,
                    "crystal_ts": None,
                    "max_player_death_ts": 1300.0,
                    "max_death_header_ts": 1310.0,
                    "max_item_ts": 1295.0,
                },
            ]
        }

        with patch(
            "vg.decoder_v2.completeness_outlier_compare.build_completeness_audit",
            return_value=audit,
        ):
            report = build_completeness_outlier_compare("C:/replays", "target")

        self.assertEqual(report["target"]["review_bucket"], "conflicting_long_tail_signals")
        self.assertEqual(report["accepted_stale_tail_reference_count"], 1)
        self.assertEqual(report["accepted_without_crystal_reference_count"], 1)
        self.assertIn("crystal_to_header", report["accepted_stale_tail_metric_summary"])


if __name__ == "__main__":
    unittest.main()
