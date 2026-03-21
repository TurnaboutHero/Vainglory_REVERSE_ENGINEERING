import unittest
from unittest.mock import patch

from vg.decoder_v2.player_events import collect_player_events_by_entity, iter_player_events


class TestDecoderV2PlayerEvents(unittest.TestCase):
    def test_iter_player_events_parses_fixed_records(self) -> None:
        # [entity_le][00 00][action][payload 32B]
        payload = bytes(range(32))
        data = b"\x34\x12\x00\x00\x04" + payload

        with patch(
            "vg.decoder_v2.player_events._load_player_entities_le",
            return_value={0x1234: "player1"},
        ), patch(
            "vg.decoder_v2.player_events.load_frames",
            return_value=[(3, data)],
        ):
            events = list(iter_player_events("sample.0.vgr"))

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].frame_idx, 3)
        self.assertEqual(events[0].entity_id_le, 0x1234)
        self.assertEqual(events[0].action, 0x04)
        self.assertEqual(events[0].payload_hex, payload.hex())

    def test_collect_player_events_by_entity_groups_records(self) -> None:
        payload = bytes(range(32))
        data = (
            b"\x34\x12\x00\x00\x04" + payload +
            b"\x34\x12\x00\x00\x07" + payload +
            b"\x78\x56\x00\x00\x04" + payload
        )

        with patch(
            "vg.decoder_v2.player_events._load_player_entities_le",
            return_value={0x1234: "player1", 0x5678: "player2"},
        ), patch(
            "vg.decoder_v2.player_events.load_frames",
            return_value=[(0, data)],
        ):
            grouped = collect_player_events_by_entity("sample.0.vgr")

        self.assertEqual(len(grouped[0x1234]), 2)
        self.assertEqual(len(grouped[0x5678]), 1)


if __name__ == "__main__":
    unittest.main()
