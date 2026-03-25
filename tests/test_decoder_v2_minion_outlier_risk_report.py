import unittest
from unittest.mock import patch

from vg.decoder_v2.minion_outlier_risk_report import build_minion_outlier_risk_report


class TestMinionOutlierRiskReport(unittest.TestCase):
    def test_build_minion_outlier_risk_report_scores_solo_subfamily_excess(self) -> None:
        matches = [
            {
                "replay_name": "a",
                "replay_file": "C:/replays/a.0.vgr",
                "players": {"p1": {"minion_kills": 10}},
            },
            {
                "replay_name": "b",
                "replay_file": "C:/replays/b.0.vgr",
                "players": {"q1": {"minion_kills": 8}},
            },
        ]

        def fake_heroes(path: str):
            if path.endswith("a.0.vgr"):
                return {"p1": "Skye"}
            return {"q1": "Skye"}

        def fake_counters(path: str):
            if path.endswith("a.0.vgr"):
                return {"p1": {(0x0E, 1.0): 6, (0x02, 17.4): 10}}
            return {"q1": {(0x0E, 1.0): 8, (0x02, 17.4): 2}}

        with patch(
            "vg.decoder_v2.minion_outlier_risk_report._load_truth_matches",
            return_value=matches,
        ), patch(
            "vg.decoder_v2.minion_outlier_risk_report._load_player_heroes",
            side_effect=fake_heroes,
        ), patch(
            "vg.decoder_v2.minion_outlier_risk_report._load_player_credit_counters",
            side_effect=fake_counters,
        ):
            report = build_minion_outlier_risk_report("truth.json")

        top = report["top_rows_by_solo_excess"][0]
        self.assertEqual(len(report["all_rows"]), 2)
        self.assertEqual(top["player_name"], "p1")
        self.assertEqual(top["solo_excess_vs_peer_mean"], 8.0)


if __name__ == "__main__":
    unittest.main()
