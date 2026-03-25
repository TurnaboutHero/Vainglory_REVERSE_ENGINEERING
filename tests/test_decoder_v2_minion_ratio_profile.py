import unittest
from unittest.mock import patch

from vg.decoder_v2.minion_ratio_profile import build_minion_ratio_profile


class TestMinionRatioProfile(unittest.TestCase):
    def test_build_minion_ratio_profile_summarizes_positive_vs_zero_classes(self) -> None:
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

        def fake_counters(path: str):
            if path.endswith("a.0.vgr"):
                return {"p1": {(0x0E, 1.0): 6, (0x02, 17.4): 12}}
            return {"q1": {(0x0E, 1.0): 8, (0x02, 17.4): 2}}

        with patch(
            "vg.decoder_v2.minion_ratio_profile._load_truth_matches",
            return_value=matches,
        ), patch(
            "vg.decoder_v2.minion_ratio_profile._load_player_credit_counters",
            side_effect=fake_counters,
        ):
            report = build_minion_ratio_profile("truth.json")

        summary = {row["metric"]: row for row in report["summary"]}
        self.assertAlmostEqual(summary["0x02@17.4_ratio"]["positive_mean"], 2.0)
        self.assertAlmostEqual(summary["0x02@17.4_ratio"]["zero_mean"], 0.25)


if __name__ == "__main__":
    unittest.main()
