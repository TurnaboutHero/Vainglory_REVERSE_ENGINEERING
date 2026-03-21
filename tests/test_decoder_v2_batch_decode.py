import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vg.decoder_v2.batch_decode import decode_replay_batch, find_replays


class TestDecoderV2BatchDecode(unittest.TestCase):
    def test_find_replays_skips_macosx_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            good = base / "a" / "sample.0.vgr"
            bad = base / "__MACOSX" / "bad.0.vgr"
            good.parent.mkdir(parents=True)
            bad.parent.mkdir(parents=True)
            good.touch()
            bad.touch()

            replays = find_replays(str(base))

        self.assertEqual(replays, [good])

    def test_decode_replay_batch_summarizes_acceptance(self) -> None:
        payload = {
            "completeness_status": "complete_confirmed",
            "accepted_fields": {"hero": "accepted", "winner": "left"},
            "withheld_fields": {"duration_seconds": "withheld"},
        }

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "vg.decoder_v2.batch_decode.find_replays",
            return_value=[Path(temp_dir) / "one.0.vgr", Path(temp_dir) / "two.0.vgr"],
        ), patch(
            "vg.decoder_v2.batch_decode.decode_match"
        ) as decode_match_mock:
            decode_match_mock.return_value.to_dict.return_value = payload
            report = decode_replay_batch(temp_dir)

        self.assertEqual(report["total_replays"], 2)
        self.assertEqual(report["completeness_summary"]["complete_confirmed"], 2)
        self.assertEqual(report["accepted_field_summary"]["hero"], 2)
        self.assertEqual(report["withheld_field_summary"]["duration_seconds"], 2)


if __name__ == "__main__":
    unittest.main()
