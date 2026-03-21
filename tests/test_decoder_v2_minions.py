import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vg.decoder_v2.minions import collect_minion_candidates
from vg.decoder_v2.models import CreditEventRecord


class TestDecoderV2Minions(unittest.TestCase):
    def test_collect_minion_candidates_counts_credit_variants(self) -> None:
        parsed = {
            "teams": {
                "left": [{"name": "player1", "entity_id": 0x1234}],
                "right": [],
            }
        }
        # Header + padding + eid(BE) + value + action
        data = (
            b"\x10\x04\x1D\x00\x00\x34\x12\x3F\x80\x00\x00\x0E"
            b"\x10\x04\x1D\x00\x00\x34\x12\x3F\x80\x00\x00\x0F"
            b"\x10\x04\x1D\x00\x00\x34\x12\x00\x00\x00\x01\x0D"
        )

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "vg.decoder_v2.minions.VGRParser"
        ) as parser_cls, patch(
            "vg.decoder_v2.minions.iter_credit_events",
            return_value=[
                CreditEventRecord(frame_idx=0, entity_id_be=0x3412, action=0x0E, value=1.0, file_offset=0, raw_record_hex="", padding_ok=True, value_is_finite=True),
                CreditEventRecord(frame_idx=0, entity_id_be=0x3412, action=0x0F, value=1.0, file_offset=12, raw_record_hex="", padding_ok=True, value_is_finite=True),
                CreditEventRecord(frame_idx=0, entity_id_be=0x3412, action=0x0D, value=0.0, file_offset=24, raw_record_hex="", padding_ok=True, value_is_finite=True),
            ],
        ):
            replay_path = Path(temp_dir) / "sample.0.vgr"
            replay_path.touch()
            parser_cls.return_value.parse.return_value = parsed

            rows = collect_minion_candidates(str(replay_path))

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.player_name, "player1")
        self.assertEqual(row.action_0e_value_1, 1)
        self.assertEqual(row.action_0f_value_1, 1)
        self.assertEqual(row.action_0d_total, 1)


if __name__ == "__main__":
    unittest.main()
