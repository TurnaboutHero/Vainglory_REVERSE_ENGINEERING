import unittest
from unittest.mock import patch

from vg.decoder_v2.minion_policy_candidates import build_minion_policy_candidates


class TestMinionPolicyCandidates(unittest.TestCase):
    def test_build_minion_policy_candidates_ranks_nonfinals_policy(self) -> None:
        profile = {
            "rows": [
                {"series": "Finals", "residual_vs_0e": 2, "solo_ratio": 2.0, "mixed_ratio": 1.0, "0x02@20.0_ratio": 0.8},
                {"series": "Semis", "residual_vs_0e": 0, "solo_ratio": 0.2, "mixed_ratio": 0.1, "0x02@20.0_ratio": 0.0},
                {"series": "Semis", "residual_vs_0e": 0, "solo_ratio": 0.3, "mixed_ratio": 0.2, "0x02@20.0_ratio": 0.0},
            ]
        }

        with patch(
            "vg.decoder_v2.minion_policy_candidates.build_minion_ratio_profile",
            return_value=profile,
        ):
            report = build_minion_policy_candidates("truth.json")

        self.assertEqual(report["top_policies"][0]["accepted_error"], 0)


if __name__ == "__main__":
    unittest.main()
