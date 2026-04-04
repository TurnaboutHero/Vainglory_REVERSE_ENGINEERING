import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vg.decoder_v2.missing_result_data_backlog import build_missing_result_data_backlog


class TestMissingResultDataBacklog(unittest.TestCase):
    def test_manifest_only_replays_rank_ahead_of_raw_only(self) -> None:
        inventory = {
            "base_path": "C:/replays",
            "truth_path": "truth.json",
            "missing": [
                {
                    "directory": "C:/replays/a",
                    "has_manifest": True,
                    "has_result_image": False,
                },
                {
                    "directory": "C:/replays/b",
                    "has_manifest": False,
                    "has_result_image": False,
                },
            ],
        }

        def fake_find_replay_files(directory: str):
            return [Path(directory) / "sample.0.vgr"]

        safe = {
            "replay_name": "sample",
            "game_mode": "GameMode_5v5_Ranked",
            "team_size": 5,
            "completeness_status": "complete_confirmed",
            "accepted_fields": {"winner": {"accepted_for_index": True}},
        }

        with patch("vg.decoder_v2.missing_result_data_backlog.build_truth_inventory", return_value=inventory), patch(
            "vg.decoder_v2.missing_result_data_backlog.build_result_screen_capture_classification",
            return_value={"rows": []},
        ), patch(
            "vg.decoder_v2.missing_result_data_backlog._discover_corrected_exports",
            return_value={},
        ), patch(
            "vg.decoder_v2.missing_result_data_backlog.find_replay_files",
            side_effect=fake_find_replay_files,
        ), patch(
            "vg.decoder_v2.missing_result_data_backlog.decode_match",
        ) as mocked_decode:
            mocked_decode.return_value.to_dict.return_value = safe
            report = build_missing_result_data_backlog("C:/replays", "truth.json")

        self.assertEqual(report["rows"][0]["source_type"], "manifest_only")
        self.assertEqual(report["rows"][1]["source_type"], "raw_only")


if __name__ == "__main__":
    unittest.main()
