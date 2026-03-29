import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vg.decoder_v2.local_minion_baseline_audit import build_local_minion_baseline_audit


class TestLocalMinionBaselineAudit(unittest.TestCase):
    @patch("vg.decoder_v2.local_minion_baseline_audit.collect_player_minion_policy_context")
    @patch("vg.decoder_v2.local_minion_baseline_audit.decode_replay_batch")
    def test_build_local_minion_baseline_audit_computes_target_percentiles(self, mock_batch, mock_context) -> None:
        mock_batch.return_value = {
            "matches": [
                {
                    "replay_name": "target",
                    "replay_file": str(Path("C:/replays/series1/m1.0.vgr")),
                    "completeness_status": "complete_confirmed",
                    "players": [
                        {"name": "p1", "hero_name": "Baron", "team": "left"},
                        {"name": "p2", "hero_name": "Vox", "team": "right"},
                    ],
                },
                {
                    "replay_name": "other",
                    "replay_file": str(Path("C:/replays/series2/m2.0.vgr")),
                    "completeness_status": "complete_confirmed",
                    "players": [
                        {"name": "p3", "hero_name": "Baron", "team": "left"},
                        {"name": "p4", "hero_name": "Vox", "team": "right"},
                    ],
                },
            ]
        }
        mock_context.side_effect = [
            {"p1": {"baseline_0e": 100, "mixed_total": 0, "mixed_ratio": 0.0}, "p2": {"baseline_0e": 40, "mixed_total": 0, "mixed_ratio": 0.0}},
            {"p3": {"baseline_0e": 50, "mixed_total": 0, "mixed_ratio": 0.0}, "p4": {"baseline_0e": 60, "mixed_total": 0, "mixed_ratio": 0.0}},
        ]

        report = build_local_minion_baseline_audit("C:/replays", "target")

        rows = {row["player_name"]: row for row in report["target_rows"]}
        self.assertEqual(rows["p1"]["hero_pool_count"], 2)
        self.assertEqual(rows["p1"]["hero_pool_percentile"], 1.0)
        self.assertEqual(rows["p2"]["hero_pool_percentile"], 0.5)


if __name__ == "__main__":
    unittest.main()
