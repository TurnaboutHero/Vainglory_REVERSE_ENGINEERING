import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vg.decoder_v2.kda_mismatch_triage import build_kda_mismatch_triage


class TestKdaMismatchTriage(unittest.TestCase):
    @patch("vg.decoder_v2.kda_mismatch_triage.load_frames")
    @patch("vg.decoder_v2.kda_mismatch_triage.VGRParser")
    @patch("vg.decoder_v2.kda_mismatch_triage._load_truth_matches")
    @patch("vg.decoder_v2.kda_mismatch_triage._resolve_truth_player_name")
    @patch("vg.decoder_v2.kda_mismatch_triage.KDADetector")
    def test_build_kda_mismatch_triage_reports_player_mismatch(
        self,
        mock_detector_cls,
        mock_resolve_name,
        mock_load_truth,
        mock_parser_cls,
        mock_load_frames,
    ) -> None:
        mock_load_truth.return_value = [
            {
                "replay_name": "r1",
                "replay_file": "C:/replays/1/r1.0.vgr",
                "match_info": {"duration_seconds": 100},
                "players": {"alice": {"kills": 1, "deaths": 2, "assists": 3}},
            }
        ]
        mock_resolve_name.return_value = "alice"
        parser = mock_parser_cls.return_value
        parser.parse.return_value = {
            "teams": {
                "left": [{"name": "alice", "entity_id": 0x1234, "hero_name": "Baron"}],
                "right": [],
            }
        }
        detector = mock_detector_cls.return_value
        detector.get_results.return_value = {0x3412: type("R", (), {"kills": 2, "deaths": 2, "assists": 1})()}
        mock_load_frames.return_value = []

        report = build_kda_mismatch_triage("truth.json")

        self.assertEqual(report["mismatch_count"], 1)
        row = report["rows"][0]
        self.assertEqual(row["diff"]["kills"], 1)
        self.assertEqual(row["diff"]["assists"], -2)


if __name__ == "__main__":
    unittest.main()
