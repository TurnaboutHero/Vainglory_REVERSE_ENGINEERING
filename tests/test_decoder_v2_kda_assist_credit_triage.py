import unittest
from unittest.mock import patch

from vg.core.kda_detector import CreditRecord, KillEvent
from vg.decoder_v2.kda_assist_credit_triage import build_kda_assist_credit_triage


class TestKdaAssistCreditTriage(unittest.TestCase):
    @patch("vg.decoder_v2.kda_assist_credit_triage._load_truth_matches")
    @patch("vg.decoder_v2.kda_assist_credit_triage.VGRParser")
    @patch("vg.decoder_v2.kda_assist_credit_triage.load_frames")
    @patch("vg.decoder_v2.kda_assist_credit_triage.KDADetector")
    @patch("vg.decoder_v2.kda_assist_credit_triage.build_kda_mismatch_triage")
    def test_build_kda_assist_credit_triage_collects_credit_windows(
        self,
        mock_mismatch,
        mock_detector_cls,
        mock_load_frames,
        mock_parser_cls,
        mock_load_truth,
    ) -> None:
        mock_load_truth.return_value = [
            {
                "replay_file": "C:/replays/r1.0.vgr",
                "match_info": {"duration_seconds": 100},
            }
        ]
        mock_mismatch.return_value = {
            "rows": [
                {
                    "replay_name": "r1",
                    "replay_file": "C:/replays/r1.0.vgr",
                    "player_name": "alice",
                    "entity_id_be": 0x3412,
                    "hero_name": "Baron",
                    "team": "left",
                    "diff": {"kills": 0, "deaths": 0, "assists": -1},
                }
            ]
        }
        parser = mock_parser_cls.return_value
        parser.parse.return_value = {
            "match_info": {"duration_seconds": 100},
            "teams": {
                "left": [{"name": "alice", "entity_id": 0x1234, "hero_name": "Baron"}],
                "right": [{"name": "bob", "entity_id": 0x5678, "hero_name": "Tony"}],
            },
        }
        detector = mock_detector_cls.return_value
        detector.kill_events = [
            KillEvent(
                killer_eid=0x5678,
                timestamp=50.0,
                frame_idx=10,
                file_offset=100,
                credits=[
                    CreditRecord(eid=0x3412, value=1.0),
                    CreditRecord(eid=0x3412, value=25.0),
                ],
            )
        ]
        mock_load_frames.return_value = []

        report = build_kda_assist_credit_triage("truth.json")

        window = report["rows"][0]["kill_windows"][0]
        self.assertEqual(window["player_credit_values"], [1.0, 25.0])
        self.assertFalse(window["same_team_as_killer"])


if __name__ == "__main__":
    unittest.main()
