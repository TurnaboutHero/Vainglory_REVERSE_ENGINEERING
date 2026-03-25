import unittest
from unittest.mock import patch

from vg.decoder_v2.minion_action_value_compare import build_minion_action_value_compare


class TestMinionActionValueCompare(unittest.TestCase):
    def test_build_minion_action_value_compare_filters_by_action(self) -> None:
        compare = {
            "selected_patterns": ["0x02@14.34", "0x02@20.0", "0x00@5.85"],
            "rows": [
                {
                    "player_name": "p1",
                    "hero_name": "Skye",
                    "residual_vs_0e": 8,
                    "same_hero_peer_count": 2,
                    "target_pattern_counts": {"0x02@14.34": 10, "0x02@20.0": 20, "0x00@5.85": 3},
                    "same_hero_peers": [
                        {"pattern_counts": {"0x02@14.34": 4, "0x02@20.0": 6, "0x00@5.85": 0}},
                        {"pattern_counts": {"0x02@14.34": 6, "0x02@20.0": 8, "0x00@5.85": 1}},
                    ],
                }
            ],
        }

        with patch(
            "vg.decoder_v2.minion_action_value_compare.build_minion_hero_compare",
            return_value=compare,
        ):
            report = build_minion_action_value_compare("truth.json", "target", action_hex="0x02")

        self.assertEqual(report["selected_patterns"], ["0x02@14.34", "0x02@20.0"])
        self.assertEqual(report["rows"][0]["value_scores"][0]["pattern"], "0x02@20.0")
        self.assertEqual(report["rows"][0]["value_scores"][0]["peer_mean"], 7.0)


if __name__ == "__main__":
    unittest.main()
