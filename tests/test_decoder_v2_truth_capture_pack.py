import unittest
from unittest.mock import patch

from vg.decoder_v2.truth_capture_pack import build_truth_capture_pack


class TestTruthCapturePack(unittest.TestCase):
    def test_build_truth_capture_pack_joins_queue_and_stubs(self) -> None:
        queue = {
            "rows": [
                {
                    "score": 100,
                    "replay_name": "a",
                    "replay_file": "C:/replays/a.0.vgr",
                    "fixture_directory": "C:/replays/A",
                    "game_mode": "GameMode_5v5_Ranked",
                    "team_size": 5,
                    "completeness_status": "complete_confirmed",
                    "manifest_linked": True,
                    "accepted_fields": ["winner", "kills", "deaths", "assists"],
                },
                {
                    "score": 10,
                    "replay_name": "b",
                    "replay_file": "C:/replays/b.0.vgr",
                    "fixture_directory": "C:/replays/B",
                    "game_mode": "GameMode_HF_Ranked",
                    "team_size": 3,
                    "completeness_status": "completeness_unknown",
                    "manifest_linked": False,
                    "accepted_fields": [],
                },
            ]
        }
        stubs = {
            "stubs": [
                {
                    "replay_name": "a",
                    "replay_file": "C:/replays/a.0.vgr",
                    "match_info": {"game_mode": "GameMode_5v5_Ranked"},
                },
                {
                    "replay_name": "b",
                    "replay_file": "C:/replays/b.0.vgr",
                    "match_info": {"game_mode": "GameMode_HF_Ranked"},
                },
            ]
        }

        with patch(
            "vg.decoder_v2.truth_capture_pack.build_truth_labeling_queue",
            return_value=queue,
        ), patch(
            "vg.decoder_v2.truth_capture_pack.build_truth_stub_report",
            return_value=stubs,
        ):
            report = build_truth_capture_pack("C:/replays", "truth.json", limit=1)

        self.assertEqual(report["generated_items"], 1)
        self.assertEqual(report["items"][0]["queue_entry"]["replay_name"], "a")
        self.assertEqual(report["items"][0]["truth_stub"]["replay_name"], "a")
        self.assertEqual(
            report["items"][0]["capture_track"],
            "validate_5v5_ranked_minion_and_kda_policy",
        )


if __name__ == "__main__":
    unittest.main()
