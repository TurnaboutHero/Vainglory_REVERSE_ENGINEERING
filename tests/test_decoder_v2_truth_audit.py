import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vg.decoder_v2.truth_audit import audit_truth


class TestDecoderV2TruthAudit(unittest.TestCase):
    def test_audit_truth_compares_truth_ocr_and_decoder_names(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            truth_path = Path(temp_dir) / "truth.json"
            ocr_path = Path(temp_dir) / "ocr.json"
            match = {
                "replay_name": "sample",
                "replay_file": "sample.0.vgr",
                "result_image": "result.jpg",
                "match_info": {"duration_seconds": 100},
                "players": {
                    "player1": {"hero_name": "Alpha", "minion_kills": 10, "kills": 1, "deaths": 2, "assists": 3}
                },
            }
            truth_path.write_text(json.dumps({"matches": [match]}), encoding="utf-8")
            ocr_path.write_text(json.dumps({"matches": [match]}), encoding="utf-8")

            safe = {
                "completeness_status": "complete_confirmed",
                "accepted_fields": {"hero": {}, "winner": {}},
                "withheld_fields": {"duration_seconds": {}},
                "players": [{"name": "player1", "hero_name": "Alpha"}],
            }

            with patch("vg.decoder_v2.truth_audit.decode_match") as decode_mock:
                decode_mock.return_value.to_dict.return_value = safe
                report = audit_truth(str(truth_path), str(ocr_path))

        self.assertEqual(report["audited_matches"], 1)
        self.assertEqual(report["matches"][0]["players"][0]["truth_name"], "player1")
        self.assertEqual(report["matches"][0]["players"][0]["ocr_name"], "player1")


if __name__ == "__main__":
    unittest.main()
