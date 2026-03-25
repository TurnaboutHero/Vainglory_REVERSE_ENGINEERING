import unittest
from unittest.mock import patch

from vg.decoder_v2.minion_series_profile import build_minion_series_profile


class TestMinionSeriesProfile(unittest.TestCase):
    def test_build_minion_series_profile_groups_rows_by_series(self) -> None:
        risk = {
            "all_rows": [
                {
                    "fixture_directory": r"C:\replays\SeriesA\1",
                    "residual_vs_0e": 2,
                    "solo_subfamily_total": 100,
                    "mixed_subfamily_total": 20,
                    "solo_excess_vs_peer_mean": 50.0,
                    "mixed_excess_vs_peer_mean": 5.0,
                },
                {
                    "fixture_directory": r"C:\replays\SeriesA\2",
                    "residual_vs_0e": 0,
                    "solo_subfamily_total": 50,
                    "mixed_subfamily_total": 10,
                    "solo_excess_vs_peer_mean": 10.0,
                    "mixed_excess_vs_peer_mean": 1.0,
                },
                {
                    "fixture_directory": r"C:\replays\SeriesB\1",
                    "residual_vs_0e": 0,
                    "solo_subfamily_total": 10,
                    "mixed_subfamily_total": 5,
                    "solo_excess_vs_peer_mean": 0.0,
                    "mixed_excess_vs_peer_mean": 0.0,
                },
            ]
        }

        with patch(
            "vg.decoder_v2.minion_series_profile.build_minion_outlier_risk_report",
            return_value=risk,
        ):
            report = build_minion_series_profile("truth.json")

        self.assertEqual(report["rows"][0]["series"], r"C:\replays\SeriesA")
        self.assertEqual(report["rows"][0]["positive_residual_rows"], 1)
        self.assertEqual(report["rows"][0]["player_rows"], 2)


if __name__ == "__main__":
    unittest.main()
