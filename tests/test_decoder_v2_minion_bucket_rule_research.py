import unittest
from unittest.mock import patch

from vg.decoder_v2.minion_bucket_rule_research import build_minion_bucket_rule_research


class TestMinionBucketRuleResearch(unittest.TestCase):
    def test_build_minion_bucket_rule_research_finds_separating_threshold(self) -> None:
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
                return {"p1": "Samuel"}
            return {"q1": "Samuel"}

        def fake_counters(path: str):
            if path.endswith("a.0.vgr"):
                return {"p1": {(0x0E, 1.0): 6, (0x02, 17.4): 10}}
            return {"q1": {(0x0E, 1.0): 8, (0x02, 17.4): 2}}

        with patch(
            "vg.decoder_v2.minion_bucket_rule_research._load_truth_matches",
            return_value=matches,
        ), patch(
            "vg.decoder_v2.minion_bucket_rule_research._load_player_heroes",
            side_effect=fake_heroes,
        ), patch(
            "vg.decoder_v2.minion_bucket_rule_research._load_player_credit_counters",
            side_effect=fake_counters,
        ):
            report = build_minion_bucket_rule_research("truth.json")

        top = report["rows"][0]
        self.assertEqual(top["hero_name"], "Samuel")
        self.assertEqual(top["pattern"], "0x02@17.4")
        self.assertEqual(top["best_threshold_rule"]["fp"], 0)


if __name__ == "__main__":
    unittest.main()
