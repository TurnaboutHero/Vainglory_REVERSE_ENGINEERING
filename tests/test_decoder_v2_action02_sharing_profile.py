import unittest
from unittest.mock import patch

from vg.decoder_v2.action02_sharing_profile import build_action02_sharing_profile


class TestAction02SharingProfile(unittest.TestCase):
    def test_build_action02_sharing_profile_aggregates_value_rows(self) -> None:
        matches = [
            {"replay_name": "a", "replay_file": "C:/replays/a.0.vgr"},
            {"replay_name": "b", "replay_file": "C:/replays/b.0.vgr"},
        ]

        def fake_rows(replay_file: str, window_bytes=100):
            if replay_file.endswith("a.0.vgr"):
                return {20.0: {"event_count": 10, "cluster_count": 5, "multi_player_cluster_count": 2, "solo_cluster_count": 3, "unique_players": 4}}
            return {20.0: {"event_count": 4, "cluster_count": 4, "multi_player_cluster_count": 0, "solo_cluster_count": 4, "unique_players": 2}}

        with patch(
            "vg.decoder_v2.action02_sharing_profile._load_truth_matches",
            return_value=matches,
        ), patch(
            "vg.decoder_v2.action02_sharing_profile._cluster_action02_events",
            side_effect=fake_rows,
        ):
            report = build_action02_sharing_profile("truth.json")

        row = report["rows"][0]
        self.assertEqual(row["value"], 20.0)
        self.assertEqual(row["match_count"], 2)
        self.assertEqual(row["event_count"], 14)
        self.assertAlmostEqual(row["shared_cluster_rate"], 2 / 9)


if __name__ == "__main__":
    unittest.main()
