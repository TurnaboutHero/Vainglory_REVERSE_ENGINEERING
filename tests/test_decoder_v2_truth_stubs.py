import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vg.decoder_v2.truth_stubs import build_truth_stub_for_replay, build_truth_stub_report


class TestDecoderV2TruthStubs(unittest.TestCase):
    def test_build_truth_stub_for_replay_prefills_safe_fields(self) -> None:
        safe = {
            "replay_name": "sample",
            "replay_file": "sample.0.vgr",
            "game_mode": "GameMode_HF_Ranked",
            "map_name": "Halcyon Fold",
            "team_size": 3,
            "completeness_status": "incomplete_confirmed",
            "completeness_reason": "reason",
            "accepted_fields": {"hero": "accepted"},
            "withheld_fields": {"winner": "withheld"},
            "players": [
                {
                    "name": "player1",
                    "team": "left",
                    "hero_name": "Alpha",
                    "entity_id": 1,
                }
            ],
        }

        with patch("vg.decoder_v2.truth_stubs.decode_match") as decode_mock, patch(
            "vg.decoder_v2.truth_stubs.parse_replay_manifest"
        ) as manifest_mock:
            decode_mock.return_value.to_dict.return_value = safe
            manifest_mock.return_value.to_dict.return_value = {"match_uuid": "m", "session_uuid": "s"}
            stub = build_truth_stub_for_replay("sample.0.vgr", "manifest.txt")

        self.assertEqual(stub["players"]["player1"]["hero_name"], "Alpha")
        self.assertIsNone(stub["players"]["player1"]["kills"])
        self.assertEqual(stub["match_info"]["completeness_status"], "incomplete_confirmed")

    def test_build_truth_stub_report_emits_missing_replays(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir) / "replays"
            missing_dir = base / "missing"
            missing_dir.mkdir(parents=True)
            replay = missing_dir / "sample.0.vgr"
            replay.touch()
            truth_path = Path(temp_dir) / "truth.json"
            truth_path.write_text(json.dumps({"matches": []}), encoding="utf-8")

            inventory = {
                "missing": [{"directory": str(missing_dir)}],
            }

            with patch("vg.decoder_v2.truth_stubs.build_truth_inventory", return_value=inventory), patch(
                "vg.decoder_v2.truth_stubs.build_truth_stub_for_replay",
                return_value={"replay_name": "sample"},
            ):
                report = build_truth_stub_report(str(base), str(truth_path))

        self.assertEqual(report["stub_count"], 1)
        self.assertEqual(report["stubs"][0]["replay_name"], "sample")


if __name__ == "__main__":
    unittest.main()
