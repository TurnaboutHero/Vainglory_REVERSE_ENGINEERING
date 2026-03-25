import unittest
from unittest.mock import patch

from vg.decoder_v2.minion_policy_stability_audit import build_minion_policy_stability_audit


class TestMinionPolicyStabilityAudit(unittest.TestCase):
    def test_stability_audit_groups_rows_by_policy_series_and_replay(self) -> None:
        matches = [
            {
                "replay_name": "semi-1",
                "replay_file": "C:/Tournament_Replays/Semis/1/replay.0.vgr",
                "players": {
                    "p1": {"minion_kills": 10},
                    "p2": {"minion_kills": 8},
                },
            },
            {
                "replay_name": "finals-2",
                "replay_file": "C:/Tournament_Replays/Law Enforcers (Finals)/2/replay.0.vgr",
                "players": {
                    "p3": {"minion_kills": 6},
                },
            },
        ]

        def fake_evaluate(policy: str, replay_file: str, completeness_status: str):
            if "Semis" in replay_file:
                return {
                    "p1": type("D", (), {"accepted": policy != "none", "baseline_0e": 10, "mixed_total": 0, "mixed_ratio": 0.0, "reason": "ok"})(),
                    "p2": type("D", (), {"accepted": False, "baseline_0e": 8, "mixed_total": 0, "mixed_ratio": 0.0, "reason": "hold"})(),
                }
            return {
                "p3": type("D", (), {"accepted": policy == "nonfinals-or-low-mixed-ratio-experimental", "baseline_0e": 7, "mixed_total": 0, "mixed_ratio": 0.0, "reason": "exp"})(),
            }

        with patch(
            "vg.decoder_v2.minion_policy_stability_audit._load_truth_matches",
            return_value=matches,
        ), patch(
            "vg.decoder_v2.minion_policy_stability_audit.evaluate_player_minion_policy",
            side_effect=fake_evaluate,
        ):
            report = build_minion_policy_stability_audit("truth.json")

        self.assertEqual(report["recommended_default"], "none")
        self.assertEqual(report["policies"]["none"]["overall"]["accepted_rows"], 0)
        self.assertEqual(report["policies"]["nonfinals-baseline-0e"]["overall"]["accepted_rows"], 1)
        self.assertEqual(report["policies"]["nonfinals-baseline-0e"]["complete_only"]["accepted_rows"], 1)
        self.assertEqual(report["policies"]["nonfinals-baseline-0e"]["incomplete_only"]["accepted_rows"], 0)
        self.assertEqual(report["policies"]["nonfinals-or-low-mixed-ratio-experimental"]["overall"]["accepted_rows"], 2)
        self.assertEqual(len(report["policies"]["nonfinals-or-low-mixed-ratio-experimental"]["by_series"]), 2)


if __name__ == "__main__":
    unittest.main()
