import unittest
from unittest.mock import patch

from vg.decoder_v2.minion_policy_cross_validation import build_minion_policy_cross_validation


class TestMinionPolicyCrossValidation(unittest.TestCase):
    def test_cross_validation_reports_failed_holdout_for_overfit_rule(self) -> None:
        profile = {
            "rows": [
                {
                    "series": "Law Enforcers (Finals)",
                    "replay_name": "finals-2",
                    "baseline_0e": 7,
                    "residual_vs_0e": 1,
                    "mixed_ratio": 0.0,
                    "solo_ratio": 0.0,
                },
                {
                    "series": "Law Enforcers (Finals)",
                    "replay_name": "finals-1",
                    "baseline_0e": 150,
                    "residual_vs_0e": 0,
                    "mixed_ratio": 0.0,
                    "solo_ratio": 0.0,
                },
                {
                    "series": "Semis",
                    "replay_name": "semi-1",
                    "baseline_0e": 150,
                    "residual_vs_0e": 0,
                    "mixed_ratio": 2.0,
                    "solo_ratio": 2.0,
                },
                {
                    "series": "Maitun",
                    "replay_name": "maitun-1",
                    "baseline_0e": 150,
                    "residual_vs_0e": 0,
                    "mixed_ratio": 2.0,
                    "solo_ratio": 2.0,
                },
            ]
        }

        with patch(
            "vg.decoder_v2.minion_policy_cross_validation.build_minion_ratio_profile",
            return_value=profile,
        ):
            report = build_minion_policy_cross_validation("truth.json")

        self.assertEqual(report["fixed_policy_reference"][0]["policy"], "accept_nonfinals_only")
        self.assertEqual(report["leave_one_series_out"]["summary"]["folds"], 3)
        self.assertGreaterEqual(report["leave_one_series_out"]["summary"]["failed_folds"], 1)
        self.assertGreaterEqual(report["leave_one_replay_out"]["summary"]["failed_folds"], 1)


if __name__ == "__main__":
    unittest.main()
