import unittest
from unittest.mock import patch

from vg.decoder_v2.minion_policy_validation import validate_minion_policy


class TestMinionPolicyValidation(unittest.TestCase):
    def test_validate_minion_policy_counts_exact_and_error_rows(self) -> None:
        matches = [
            {
                "replay_name": "a",
                "replay_file": "C:/replays/a.0.vgr",
                "players": {
                    "p1": {"minion_kills": 10},
                    "p2": {"minion_kills": 8},
                },
            }
        ]
        decisions = {
            "p1": type("D", (), {"accepted": True, "baseline_0e": 10, "mixed_total": 0, "mixed_ratio": 0.0, "reason": "ok"})(),
            "p2": type("D", (), {"accepted": True, "baseline_0e": 7, "mixed_total": 1, "mixed_ratio": 0.1, "reason": "ok"})(),
        }

        with patch(
            "vg.decoder_v2.minion_policy_validation._load_truth_matches",
            return_value=matches,
        ), patch(
            "vg.decoder_v2.minion_policy_validation.evaluate_player_minion_policy",
            return_value=decisions,
        ):
            report = validate_minion_policy("truth.json", "nonfinals-baseline-0e")

        self.assertEqual(report["accepted_rows"], 2)
        self.assertEqual(report["accepted_exact"], 1)
        self.assertEqual(report["accepted_error"], 1)
        self.assertAlmostEqual(report["precision"], 0.5)


if __name__ == "__main__":
    unittest.main()
