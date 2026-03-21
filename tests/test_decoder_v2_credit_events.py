import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vg.decoder_v2.credit_events import collect_credit_events_by_entity, iter_credit_events


class TestDecoderV2CreditEvents(unittest.TestCase):
    def test_iter_credit_events_parses_basic_credit_records(self) -> None:
        data = (
            b"\x10\x04\x1D\x00\x00\x12\x34\x3F\x80\x00\x00\x0E"
            b"\x10\x04\x1D\x00\x00\x12\x34\x40\x20\x00\x00\x06"
        )

        with patch("vg.decoder_v2.credit_events.load_frames", return_value=[(7, data)]):
            events = list(iter_credit_events("sample.0.vgr"))

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0].frame_idx, 7)
        self.assertEqual(events[0].entity_id_be, 0x1234)
        self.assertEqual(events[0].action, 0x0E)
        self.assertAlmostEqual(events[0].value, 1.0)
        self.assertTrue(events[0].padding_ok)
        self.assertTrue(events[0].value_is_finite)
        self.assertEqual(events[0].raw_record_hex, data[:12].hex())
        self.assertEqual(events[1].action, 0x06)

    def test_collect_credit_events_by_entity_groups_records(self) -> None:
        data = (
            b"\x10\x04\x1D\x00\x00\x12\x34\x3F\x80\x00\x00\x0E"
            b"\x10\x04\x1D\x00\x00\x12\x34\x40\x20\x00\x00\x06"
            b"\x10\x04\x1D\x00\x00\x56\x78\x3F\x80\x00\x00\x0F"
        )

        with patch("vg.decoder_v2.credit_events.load_frames", return_value=[(0, data)]):
            grouped = collect_credit_events_by_entity("sample.0.vgr")

        self.assertEqual(sorted(grouped.keys()), [0x1234, 0x5678])
        self.assertEqual(len(grouped[0x1234]), 2)
        self.assertEqual(len(grouped[0x5678]), 1)


if __name__ == "__main__":
    unittest.main()
