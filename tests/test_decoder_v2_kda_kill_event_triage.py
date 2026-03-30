import unittest
from unittest.mock import patch

from vg.core.kda_detector import CreditRecord, KillEvent
from vg.decoder_v2.kda_kill_event_triage import build_kda_kill_event_triage


class TestKdaKillEventTriage(unittest.TestCase):
    @patch("vg.decoder_v2.kda_kill_event_triage._load_truth_matches")
    @patch("vg.decoder_v2.kda_kill_event_triage.VGRParser")
    @patch("vg.decoder_v2.kda_kill_event_triage.load_frames")
    @patch("vg.decoder_v2.kda_kill_event_triage.KDADetector")
    @patch("vg.decoder_v2.kda_kill_event_triage.build_kda_mismatch_triage")
    def test_build_kda_kill_event_triage_collects_kill_windows(
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
                    "truth": {"kills": 1, "deaths": 0, "assists": 0},
                    "predicted": {"kills": 2, "deaths": 0, "assists": 0},
                    "diff": {"kills": 1, "deaths": 0, "assists": 0},
                }
            ]
        }
        parser = mock_parser_cls.return_value
        parser.parse.return_value = {
            "teams": {
                "left": [{"name": "alice", "entity_id": 0x1234, "hero_name": "Baron"}],
                "right": [{"name": "bob", "entity_id": 0x7856, "hero_name": "Tony"}],
            }
        }
        detector = mock_detector_cls.return_value
        detector.kill_events = [
            KillEvent(
                killer_eid=0x3412,
                timestamp=50.0,
                frame_idx=10,
                file_offset=100,
                credits=[CreditRecord(eid=0x3412, value=1.0)],
            )
        ]
        detector.get_kill_death_pairs.return_value = [
            {"killer_eid": 0x3412, "victim_eid": 0x5678, "kill_ts": 50.0, "dt": 1.5}
        ]
        mock_load_frames.return_value = []

        report = build_kda_kill_event_triage("truth.json")

        event = report["rows"][0]["kill_events"][0]
        self.assertEqual(event["victim_name"], "bob")
        self.assertEqual(event["pair_dt"], 1.5)


if __name__ == "__main__":
    unittest.main()
