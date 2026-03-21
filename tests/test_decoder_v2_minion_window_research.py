import unittest
from unittest.mock import patch

from vg.decoder_v2.minion_window_research import build_minion_window_report
from vg.decoder_v2.models import CreditEventRecord


class TestMinionWindowResearch(unittest.TestCase):
    def test_build_minion_window_report_counts_neighbor_headers_and_patterns(self) -> None:
        parsed = {
            "replay_name": "sample",
            "teams": {
                "left": [{"name": "player1", "entity_id": 0x1234}],
                "right": [],
            },
        }
        frame = (
            b"\x00" * 12
            + b"\x18\x04\x3E"
            + b"\x00" * 9
            + b"\x10\x04\x1D\x00\x00\x34\x12\x3F\x80\x00\x00\x0E"
            + b"\x00" * 3
            + b"\x10\x04\x1D\x00\x00\x34\x12\x40\x40\x00\x00\x06"
            + b"\x00" * 16
        )
        events = [
            CreditEventRecord(
                frame_idx=10,
                entity_id_be=0x3412,
                action=0x0E,
                value=1.0,
                file_offset=24,
                raw_record_hex="",
                padding_ok=True,
                value_is_finite=True,
            ),
            CreditEventRecord(
                frame_idx=10,
                entity_id_be=0x3412,
                action=0x06,
                value=3.0,
                file_offset=39,
                raw_record_hex="",
                padding_ok=True,
                value_is_finite=True,
            ),
        ]

        with patch("vg.decoder_v2.minion_window_research.VGRParser") as parser_cls, patch(
            "vg.decoder_v2.minion_window_research.load_frames",
            return_value=[(10, frame)],
        ), patch(
            "vg.decoder_v2.minion_window_research.iter_credit_events",
            return_value=events,
        ):
            parser_cls.return_value.parse.return_value = parsed
            report = build_minion_window_report("sample.0.vgr", byte_window=32)

        self.assertEqual(report["aggregate"]["players"], 1)
        player = report["players"][0]
        self.assertEqual(player["player_name"], "player1")
        self.assertEqual(player["target_0e_samples"], 1)
        self.assertEqual(player["target_0f_samples"], 0)
        self.assertEqual(player["top_neighbor_headers"][0]["header_hex"], "10041d")
        patterns = {item["pattern"]: item["count"] for item in player["top_same_frame_credit_patterns"]}
        self.assertEqual(patterns["0x06@3.0"], 1)


if __name__ == "__main__":
    unittest.main()
