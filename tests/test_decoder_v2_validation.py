import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vg.decoder_v2.validation import build_foundation_report, validate_player_block_claims


class TestDecoderV2Validation(unittest.TestCase):
    def test_validate_player_block_claims_on_synthetic_truth(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            replay_path = Path(temp_dir) / "sample.0.vgr"
            block = bytearray(0xE2)
            block[0:3] = b"\xDA\x03\xEE"
            block[3:3 + len("PlayerOne")] = b"PlayerOne"
            block[0xA5:0xA7] = (57093).to_bytes(2, "little")
            block[0xA9:0xAB] = (0xB801).to_bytes(2, "little")
            block[0xAB:0xAF] = bytes.fromhex("11223344")
            block[0xD5] = 1
            replay_path.write_bytes(bytes(block))

            truth_path = Path(temp_dir) / "truth.json"
            truth_path.write_text(
                json.dumps(
                    {
                        "matches": [
                            {
                                "replay_name": "sample",
                                "replay_file": str(replay_path),
                                "players": {
                                    "PlayerOne": {
                                        "hero_name": "Inara",
                                    }
                                },
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            summary = validate_player_block_claims(str(truth_path))

        self.assertEqual(summary.matches_total, 1)
        self.assertEqual(summary.records_total, 1)
        self.assertEqual(summary.hero_matches, 1)
        self.assertEqual(summary.hero_total, 1)

    def test_build_foundation_report_embeds_decoder_validation(self) -> None:
        with patch("vg.decoder_v2.validation.run_validation", return_value={"winner": {"correct": 1, "total": 1}}):
            with patch("vg.decoder_v2.validation.validate_player_block_claims") as mock_validate:
                mock_validate.return_value.to_dict.return_value = {"matches_total": 1}
                report = build_foundation_report("vg/output/tournament_truth.json")

        self.assertIn("offset_claims", report)
        self.assertIn("event_header_claims", report)
        self.assertIn("current_decoder_validation", report)
        self.assertEqual(report["current_decoder_validation"]["winner"]["correct"], 1)


if __name__ == "__main__":
    unittest.main()
