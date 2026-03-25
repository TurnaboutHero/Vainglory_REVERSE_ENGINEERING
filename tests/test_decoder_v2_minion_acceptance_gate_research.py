import unittest
from unittest.mock import patch

from vg.decoder_v2.minion_acceptance_gate_research import build_minion_acceptance_gate_research


class TestMinionAcceptanceGateResearch(unittest.TestCase):
    def test_build_minion_acceptance_gate_research_scores_simple_metric_gate(self) -> None:
        profile = {
            "rows": [
                {"series": "Finals", "residual_vs_0e": 0, "solo_ratio": 0.1, "mixed_ratio": 0.1, "0x02@17.4_ratio": 0.0},
                {"series": "Finals", "residual_vs_0e": 2, "solo_ratio": 2.0, "mixed_ratio": 0.1, "0x02@17.4_ratio": 1.5},
                {"series": "Semis", "residual_vs_0e": 0, "solo_ratio": 0.2, "mixed_ratio": 0.2, "0x02@17.4_ratio": 0.0},
            ]
        }

        with patch(
            "vg.decoder_v2.minion_acceptance_gate_research.build_minion_ratio_profile",
            return_value=profile,
        ):
            report = build_minion_acceptance_gate_research("truth.json")

        self.assertEqual(report["row_count"], 3)
        self.assertEqual(report["metric_gates"][0]["best_gate"]["accepted_error"], 0)


if __name__ == "__main__":
    unittest.main()
