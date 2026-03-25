import unittest
from unittest.mock import patch

from vg.decoder_v2.minion_series_peer_compare import build_minion_series_peer_compare


class TestMinionSeriesPeerCompare(unittest.TestCase):
    def test_build_minion_series_peer_compare_splits_same_vs_other_series(self) -> None:
        truth_payload = {
            "matches": [
                {"replay_name": "target", "replay_file": "C:/replays/Finals/2/target.0.vgr"},
            ]
        }
        compare = {
            "selected_patterns": ["0x02@20.0"],
            "rows": [
                {
                    "player_name": "p1",
                    "hero_name": "Kestrel",
                    "residual_vs_0e": 4,
                    "target_pattern_counts": {"0x02@20.0": 100},
                    "same_hero_peers": [
                        {"fixture_directory": "C:/replays/Finals/1", "pattern_counts": {"0x02@20.0": 30}},
                        {"fixture_directory": "C:/replays/Semis/1", "pattern_counts": {"0x02@20.0": 10}},
                    ],
                }
            ],
        }

        with patch("pathlib.Path.read_text", return_value='{"matches":[{"replay_name":"target","replay_file":"C:/replays/Finals/2/target.0.vgr"}]}'), patch(
            "vg.decoder_v2.minion_series_peer_compare.build_minion_hero_compare",
            return_value=compare,
        ):
            report = build_minion_series_peer_compare("truth.json", "target")

        row = report["rows"][0]["pattern_rows"][0]
        self.assertEqual(row["same_series_mean"], 30.0)
        self.assertEqual(row["other_series_mean"], 10.0)
        self.assertEqual(row["excess_vs_same_series_mean"], 70.0)


if __name__ == "__main__":
    unittest.main()
