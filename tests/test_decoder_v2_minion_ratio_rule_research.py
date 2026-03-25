import unittest
from unittest.mock import patch

from vg.decoder_v2.minion_ratio_rule_research import build_minion_ratio_rule_research


class TestMinionRatioRuleResearch(unittest.TestCase):
    def test_build_minion_ratio_rule_research_scores_metric_thresholds(self) -> None:
        profile = {
            "rows": [
                {"residual_vs_0e": 2, "solo_ratio": 2.0, "mixed_ratio": 0.5, "0x02@17.4_ratio": 1.5},
                {"residual_vs_0e": 0, "solo_ratio": 0.2, "mixed_ratio": 0.6, "0x02@17.4_ratio": 0.1},
                {"residual_vs_0e": 0, "solo_ratio": 0.1, "mixed_ratio": 0.7, "0x02@17.4_ratio": 0.0},
            ]
        }

        with patch(
            "vg.decoder_v2.minion_ratio_rule_research.build_minion_ratio_profile",
            return_value=profile,
        ):
            report = build_minion_ratio_rule_research("truth.json")

        self.assertEqual(report["rows"][0]["metric"], "solo_ratio")
        self.assertEqual(report["rows"][0]["best_threshold_rule"]["fp"], 0)


if __name__ == "__main__":
    unittest.main()
