import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vg.decoder_v2.action4_research import build_action4_report


class TestDecoderV2Action4Research(unittest.TestCase):
    def test_build_action4_report_collects_payload_patterns(self) -> None:
        truth_payload = {
            "matches": [
                {
                    "replay_name": "sample",
                    "replay_file": "sample.0.vgr",
                    "players": {"player1": {"minion_kills": 5}},
                }
            ]
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            truth_path = Path(temp_dir) / "truth.json"
            truth_path.write_text(json.dumps(truth_payload), encoding="utf-8")

            parsed = {
                "teams": {
                    "left": [{"name": "player1", "entity_id": 0x1234}],
                    "right": [],
                }
            }

            with patch("vg.decoder_v2.action4_research.iter_credit_events", return_value=[
                type("Credit", (), {"frame_idx": 1, "entity_id_be": 0x3412, "action": 0x04, "value": 190.91, "raw_record_hex": "00", "file_offset": 10})(),
                type("Credit", (), {"frame_idx": 2, "entity_id_be": 0x3412, "action": 0x04, "value": 190.91, "raw_record_hex": "11", "file_offset": 20})(),
            ]), patch("vg.core.vgr_parser.VGRParser") as parser_cls:
                parser_cls.return_value.parse.return_value = parsed
                report = build_action4_report("sample.0.vgr", str(truth_path))

        self.assertEqual(report["rows"][0]["player_name"], "player1")
        self.assertEqual(report["rows"][0]["action4_total"], 2)


if __name__ == "__main__":
    unittest.main()
