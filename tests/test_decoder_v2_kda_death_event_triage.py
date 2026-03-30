import unittest
from unittest.mock import patch

from vg.core.kda_detector import DeathEvent
from vg.decoder_v2.kda_death_event_triage import build_kda_death_event_triage


class TestKdaDeathEventTriage(unittest.TestCase):
    @patch("vg.decoder_v2.kda_death_event_triage._load_truth_matches")
    @patch("vg.decoder_v2.kda_death_event_triage.VGRParser")
    @patch("vg.decoder_v2.kda_death_event_triage.load_frames")
    @patch("vg.decoder_v2.kda_death_event_triage.KDADetector")
    @patch("vg.decoder_v2.kda_death_event_triage.build_kda_mismatch_triage")
    def test_build_kda_death_event_triage_collects_player_death_events(
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
                    "truth": {"kills": 0, "deaths": 1, "assists": 0},
                    "predicted": {"kills": 0, "deaths": 2, "assists": 0},
                    "diff": {"kills": 0, "deaths": 1, "assists": 0},
                }
            ]
        }
        parser = mock_parser_cls.return_value
        parser.parse.return_value = {
            "teams": {
                "left": [{"name": "alice", "entity_id": 0x1234, "hero_name": "Baron"}],
                "right": [],
            }
        }
        detector = mock_detector_cls.return_value
        detector.death_events = [
            DeathEvent(victim_eid=0x3412, timestamp=95.0, frame_idx=10, file_offset=100),
            DeathEvent(victim_eid=0x3412, timestamp=104.0, frame_idx=11, file_offset=200),
        ]
        mock_load_frames.return_value = []

        report = build_kda_death_event_triage("truth.json")

        events = report["rows"][0]["death_events"]
        self.assertEqual(len(events), 2)
        self.assertEqual(events[1]["delta_after_duration"], 4.0)


if __name__ == "__main__":
    unittest.main()
