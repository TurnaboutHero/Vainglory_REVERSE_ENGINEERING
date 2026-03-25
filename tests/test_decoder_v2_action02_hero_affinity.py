import unittest
from unittest.mock import patch

from vg.decoder_v2.action02_hero_affinity import build_action02_hero_affinity


class TestAction02HeroAffinity(unittest.TestCase):
    def test_build_action02_hero_affinity_summarizes_top_hero_share(self) -> None:
        matches = [
            {"replay_name": "a", "replay_file": "C:/replays/a.0.vgr"},
        ]
        parsed = {
            "teams": {
                "left": [{"name": "p1", "hero_name": "Samuel"}],
                "right": [{"name": "p2", "hero_name": "Kestrel"}],
            }
        }

        with patch(
            "vg.decoder_v2.action02_hero_affinity._load_truth_matches",
            return_value=matches,
        ), patch(
            "vg.decoder_v2.action02_hero_affinity.VGRParser",
        ) as parser_cls, patch(
            "vg.decoder_v2.action02_hero_affinity._load_player_credit_counters",
            return_value={
                "p1": {(0x02, 17.4): 10},
                "p2": {(0x02, 17.4): 2},
            },
        ):
            parser_cls.return_value.parse.return_value = parsed
            report = build_action02_hero_affinity("truth.json")

        row = report["rows"][0]
        self.assertEqual(row["value"], 17.4)
        self.assertEqual(row["top_hero_name"], "Samuel")
        self.assertAlmostEqual(row["top_hero_share"], 10 / 12)


if __name__ == "__main__":
    unittest.main()
