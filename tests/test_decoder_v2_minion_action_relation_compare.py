import unittest
from unittest.mock import patch

from vg.decoder_v2.minion_action_relation_compare import build_minion_action_relation_compare


class TestMinionActionRelationCompare(unittest.TestCase):
    def test_build_minion_action_relation_compare_merges_peer_relation_means(self) -> None:
        compare = {
            "selected_patterns": ["0x02@20.0"],
            "rows": [
                {
                    "player_name": "p1",
                    "hero_name": "Kestrel",
                    "residual_vs_0e": 4,
                    "same_hero_peers": [
                        {"fixture_directory": "C:/replays/Finals/1", "replay_name": "peer1", "player_name": "p1"},
                        {"fixture_directory": "C:/replays/Semis/1", "replay_name": "peer2", "player_name": "p1"},
                    ],
                }
            ],
        }

        reports = {
            "target": {
                "p1": [{"pattern": "0x02@20.0", "self_presence_rate": 0.4, "teammate_presence_rate": 0.6, "opponent_presence_rate": 0.8}]
            },
            "peer1": {
                "p1": [{"pattern": "0x02@20.0", "self_presence_rate": 0.2, "teammate_presence_rate": 0.3, "opponent_presence_rate": 0.4}]
            },
            "peer2": {
                "p1": [{"pattern": "0x02@20.0", "self_presence_rate": 0.1, "teammate_presence_rate": 0.2, "opponent_presence_rate": 0.5}]
            },
        }

        def fake_self_vs_team_per_player(replay_file, selected_patterns):
            if replay_file.endswith("target.0.vgr"):
                return reports["target"]
            if replay_file.endswith("peer1.0.vgr"):
                return reports["peer1"]
            return reports["peer2"]

        with patch(
            "vg.decoder_v2.minion_action_relation_compare.build_minion_hero_compare",
            return_value=compare,
        ), patch(
            "pathlib.Path.read_text",
            return_value='{"matches":[{"replay_name":"target","replay_file":"C:/replays/Finals/2/target.0.vgr"},{"replay_name":"peer1","replay_file":"C:/replays/Finals/1/peer1.0.vgr"},{"replay_name":"peer2","replay_file":"C:/replays/Semis/1/peer2.0.vgr"}]}',
        ), patch(
            "vg.decoder_v2.minion_action_relation_compare.build_minion_action_self_vs_team_per_player",
            side_effect=fake_self_vs_team_per_player,
        ):
            report = build_minion_action_relation_compare("truth.json", "target")

        row = report["rows"][0]["pattern_rows"][0]
        self.assertEqual(row["same_series_self_presence_mean"], 0.2)
        self.assertEqual(row["other_series_self_presence_mean"], 0.1)
        self.assertEqual(row["target_opponent_presence_rate"], 0.8)


if __name__ == "__main__":
    unittest.main()
