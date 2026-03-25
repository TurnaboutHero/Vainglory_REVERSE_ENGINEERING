import unittest
from unittest.mock import patch

from vg.decoder_v2.minion_action_cluster_compare import build_minion_action_cluster_compare


class TestMinionActionClusterCompare(unittest.TestCase):
    def test_build_minion_action_cluster_compare_summarizes_target_vs_baseline(self) -> None:
        truth_matches = [
            {"replay_name": "target", "replay_file": "C:/replays/target.0.vgr"},
            {"replay_name": "ref1", "replay_file": "C:/replays/ref1.0.vgr"},
            {"replay_name": "ref2", "replay_file": "C:/replays/ref2.0.vgr"},
        ]

        def fake_stats(replay_file: str, selected_patterns, window_bytes=100):
            if "target" in replay_file:
                return {"0x02@20.0": {"event_count": 100, "cluster_count": 20, "mean_cluster_size": 5.0, "max_cluster_size": 8, "multi_player_cluster_count": 10, "unique_players": 4}}
            if "ref1" in replay_file:
                return {"0x02@20.0": {"event_count": 10, "cluster_count": 5, "mean_cluster_size": 2.0, "max_cluster_size": 3, "multi_player_cluster_count": 2, "unique_players": 3}}
            return {"0x02@20.0": {"event_count": 20, "cluster_count": 10, "mean_cluster_size": 2.0, "max_cluster_size": 4, "multi_player_cluster_count": 4, "unique_players": 3}}

        with patch(
            "vg.decoder_v2.minion_action_cluster_compare.build_minion_outlier_compare",
            return_value={"credit_pattern_rate_deltas": [{"pattern": "0x02@20.0"}]},
        ), patch(
            "vg.decoder_v2.minion_action_cluster_compare._load_truth_matches",
            return_value=truth_matches,
        ), patch(
            "vg.decoder_v2.minion_action_cluster_compare._collect_pattern_cluster_stats",
            side_effect=fake_stats,
        ):
            report = build_minion_action_cluster_compare("truth.json", "target", action_hex="0x02", top_pattern_limit=1)

        row = report["patterns"][0]
        self.assertEqual(row["pattern"], "0x02@20.0")
        self.assertEqual(row["baseline_peer_count"], 2)
        self.assertEqual(row["baseline_mean_event_count"], 15.0)
        self.assertEqual(row["target"]["event_count"], 100)


if __name__ == "__main__":
    unittest.main()
