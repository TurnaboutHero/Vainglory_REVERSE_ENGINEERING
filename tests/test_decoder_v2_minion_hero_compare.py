import unittest
from unittest.mock import patch

from vg.decoder_v2.minion_hero_compare import build_minion_hero_compare


class TestMinionHeroCompare(unittest.TestCase):
    def test_build_minion_hero_compare_tracks_same_hero_peers(self) -> None:
        matches = [
            {
                "replay_name": "target",
                "replay_file": "C:/replays/target/target.0.vgr",
                "players": {"p1": {"minion_kills": 10}},
            },
            {
                "replay_name": "ref",
                "replay_file": "C:/replays/ref/ref.0.vgr",
                "players": {"q1": {"minion_kills": 8}},
            },
        ]

        def fake_heroes(path: str):
            if "target" in path:
                return {"p1": "Skye"}
            return {"q1": "Skye"}

        def fake_counters(path: str):
            if "target" in path:
                return {"p1": {(0x0E, 1.0): 6, (0x02, 14.34): 4}}
            return {"q1": {(0x0E, 1.0): 8, (0x02, 14.34): 0}}

        with patch(
            "vg.decoder_v2.minion_hero_compare._load_truth_matches",
            return_value=matches,
        ), patch(
            "vg.decoder_v2.minion_hero_compare.build_minion_outlier_compare",
            return_value={"credit_pattern_rate_deltas": [{"pattern": "0x02@14.34"}]},
        ), patch(
            "vg.decoder_v2.minion_hero_compare._load_player_heroes",
            side_effect=fake_heroes,
        ), patch(
            "vg.decoder_v2.minion_hero_compare._load_player_credit_counters",
            side_effect=fake_counters,
        ):
            report = build_minion_hero_compare("truth.json", "target", top_pattern_limit=1)

        self.assertEqual(report["selected_patterns"], ["0x02@14.34"])
        self.assertEqual(report["rows"][0]["player_name"], "p1")
        self.assertEqual(report["rows"][0]["hero_name"], "Skye")
        self.assertEqual(report["rows"][0]["same_hero_peer_count"], 1)
        self.assertEqual(report["rows"][0]["same_hero_peers"][0]["pattern_counts"]["0x02@14.34"], 0)


if __name__ == "__main__":
    unittest.main()
