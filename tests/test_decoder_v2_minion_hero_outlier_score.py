import unittest
from unittest.mock import patch

from vg.decoder_v2.minion_hero_outlier_score import build_minion_hero_outlier_score


class TestMinionHeroOutlierScore(unittest.TestCase):
    def test_build_minion_hero_outlier_score_computes_excess_against_peer_mean(self) -> None:
        compare = {
            "selected_patterns": ["0x02@14.34", "0x00@5.85"],
            "rows": [
                {
                    "player_name": "p1",
                    "hero_name": "Skye",
                    "residual_vs_0e": 8,
                    "same_hero_peer_count": 2,
                    "target_pattern_counts": {"0x02@14.34": 10, "0x00@5.85": 2},
                    "same_hero_peers": [
                        {"pattern_counts": {"0x02@14.34": 4, "0x00@5.85": 0}},
                        {"pattern_counts": {"0x02@14.34": 6, "0x00@5.85": 1}},
                    ],
                }
            ],
        }

        with patch(
            "vg.decoder_v2.minion_hero_outlier_score.build_minion_hero_compare",
            return_value=compare,
        ):
            report = build_minion_hero_outlier_score("truth.json", "target")

        row = report["rows"][0]
        self.assertEqual(row["pattern_scores"][0]["pattern"], "0x02@14.34")
        self.assertEqual(row["pattern_scores"][0]["peer_mean"], 5.0)
        self.assertEqual(row["pattern_scores"][0]["excess_vs_mean"], 5.0)


if __name__ == "__main__":
    unittest.main()
