import unittest
from unittest.mock import patch

from vg.decoder_v2.minion_same_series_delta import build_minion_same_series_delta


class TestMinionSameSeriesDelta(unittest.TestCase):
    def test_build_minion_same_series_delta_keeps_only_positive_rows(self) -> None:
        compare = {
            "rows": [
                {
                    "player_name": "p1",
                    "hero_name": "Samuel",
                    "residual_vs_0e": 6,
                    "same_series_peer_count": 2,
                    "other_series_peer_count": 1,
                    "pattern_rows": [
                        {"pattern": "0x02@17.4", "target_count": 600, "same_series_mean": 300.0, "other_series_mean": 100.0, "excess_vs_same_series_mean": 300.0, "excess_vs_other_series_mean": 500.0}
                    ],
                },
                {
                    "player_name": "p2",
                    "hero_name": "Kestrel",
                    "residual_vs_0e": 0,
                    "same_series_peer_count": 2,
                    "other_series_peer_count": 1,
                    "pattern_rows": [],
                },
            ]
        }

        with patch(
            "vg.decoder_v2.minion_same_series_delta.build_minion_series_peer_compare",
            return_value=compare,
        ):
            report = build_minion_same_series_delta("truth.json", "target")

        self.assertEqual(len(report["rows"]), 1)
        self.assertEqual(report["rows"][0]["player_name"], "p1")
        self.assertEqual(report["rows"][0]["top_same_series_deltas"][0]["pattern"], "0x02@17.4")


if __name__ == "__main__":
    unittest.main()
