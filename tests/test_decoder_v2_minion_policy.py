import unittest

from vg.decoder_v2.minion_policy import (
    MINION_POLICY_NONE,
    MINION_POLICY_NONFINALS_BASELINE_0E,
    MINION_POLICY_NONFINALS_OR_LOW_MIXED_RATIO_EXPERIMENTAL,
    evaluate_minion_policy,
    evaluate_player_minion_policy,
)


class TestMinionPolicy(unittest.TestCase):
    def test_none_policy_always_withholds(self) -> None:
        accepted, reason = evaluate_minion_policy(
            MINION_POLICY_NONE,
            r"C:\replays\Semis\1\sample.0.vgr",
            "complete_confirmed",
        )

        self.assertFalse(accepted)
        self.assertIn("disabled", reason)

    def test_nonfinals_policy_accepts_complete_nonfinals(self) -> None:
        accepted, reason = evaluate_minion_policy(
            MINION_POLICY_NONFINALS_BASELINE_0E,
            r"C:\replays\Semis\1\sample.0.vgr",
            "complete_confirmed",
        )

        self.assertTrue(accepted)
        self.assertIn("accepted", reason)

    def test_nonfinals_policy_withholds_finals(self) -> None:
        accepted, reason = evaluate_minion_policy(
            MINION_POLICY_NONFINALS_BASELINE_0E,
            r"C:\replays\SFC vs Law Enforcers (Finals)\2\sample.0.vgr",
            "complete_confirmed",
        )

        self.assertFalse(accepted)
        self.assertIn("Finals-series", reason)

    def test_nonfinals_policy_withholds_incomplete(self) -> None:
        accepted, reason = evaluate_minion_policy(
            MINION_POLICY_NONFINALS_BASELINE_0E,
            r"C:\replays\Semis\1\sample.0.vgr",
            "incomplete_confirmed",
        )

        self.assertFalse(accepted)
        self.assertIn("completeness", reason)

    def test_experimental_policy_requests_player_level_finals_decisions(self) -> None:
        accepted, reason = evaluate_minion_policy(
            MINION_POLICY_NONFINALS_OR_LOW_MIXED_RATIO_EXPERIMENTAL,
            r"C:\replays\SFC vs Law Enforcers (Finals)\2\sample.0.vgr",
            "complete_confirmed",
        )

        self.assertFalse(accepted)
        self.assertIn("player-level", reason)

    def test_experimental_policy_accepts_low_mixed_ratio_finals_player(self) -> None:
        with unittest.mock.patch(
            "vg.decoder_v2.minion_policy.collect_player_minion_policy_context",
            return_value={
                "player1": {"baseline_0e": 100, "mixed_total": 10, "mixed_ratio": 0.1},
                "player2": {"baseline_0e": 100, "mixed_total": 20, "mixed_ratio": 0.2},
            },
        ):
            decisions = evaluate_player_minion_policy(
                MINION_POLICY_NONFINALS_OR_LOW_MIXED_RATIO_EXPERIMENTAL,
                r"C:\replays\SFC vs Law Enforcers (Finals)\2\sample.0.vgr",
                "complete_confirmed",
            )

        self.assertTrue(decisions["player1"].accepted)
        self.assertFalse(decisions["player2"].accepted)


if __name__ == "__main__":
    unittest.main()
