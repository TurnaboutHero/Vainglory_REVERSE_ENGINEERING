import unittest
from unittest.mock import patch

from vg.decoder_v2.truth_labeling_queue import build_truth_labeling_queue


class TestTruthLabelingQueue(unittest.TestCase):
    def test_labeling_queue_prioritizes_complete_5v5_ranked_manifest_linked_stubs(self) -> None:
        stub_report = {
            "stubs": [
                {
                    "replay_name": "a",
                    "replay_file": "C:/replays/a.0.vgr",
                    "manifest": {"match_uuid": "a"},
                    "match_info": {
                        "game_mode": "GameMode_5v5_Ranked",
                        "team_size": 5,
                        "completeness_status": "complete_confirmed",
                    },
                    "accepted_fields": {"winner": "left", "kills": "accepted"},
                },
                {
                    "replay_name": "b",
                    "replay_file": "C:/replays/b.0.vgr",
                    "manifest": None,
                    "match_info": {
                        "game_mode": "GameMode_HF_Ranked",
                        "team_size": 3,
                        "completeness_status": "completeness_unknown",
                    },
                    "accepted_fields": {},
                },
            ]
        }

        with patch(
            "vg.decoder_v2.truth_labeling_queue.build_truth_stub_report",
            return_value=stub_report,
        ):
            report = build_truth_labeling_queue("C:/replays", "truth.json")

        self.assertEqual(report["queue_size"], 2)
        self.assertEqual(report["top_candidates"][0]["replay_name"], "a")
        self.assertIn("complete_confirmed", report["top_candidates"][0]["priority_tags"])
        self.assertTrue(report["top_candidates"][0]["manifest_linked"])


if __name__ == "__main__":
    unittest.main()
