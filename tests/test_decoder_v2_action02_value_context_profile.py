import unittest
from unittest.mock import patch

from vg.decoder_v2.action02_value_context_profile import build_action02_value_context_profile
from vg.decoder_v2.models import CreditEventRecord


class TestAction02ValueContextProfile(unittest.TestCase):
    def test_build_action02_value_context_profile_counts_same_frame_patterns(self) -> None:
        matches = [{"replay_name": "a", "replay_file": "a.0.vgr"}]
        events = [
            CreditEventRecord(frame_idx=10, entity_id_be=0x3412, action=0x02, value=20.0, file_offset=10, raw_record_hex="", padding_ok=True, value_is_finite=True),
            CreditEventRecord(frame_idx=10, entity_id_be=0x3412, action=0x06, value=3.0, file_offset=20, raw_record_hex="", padding_ok=True, value_is_finite=True),
            CreditEventRecord(frame_idx=10, entity_id_be=0x3412, action=0x08, value=0.6, file_offset=30, raw_record_hex="", padding_ok=True, value_is_finite=True),
        ]

        with patch(
            "vg.decoder_v2.action02_value_context_profile._load_truth_matches",
            return_value=matches,
        ), patch(
            "vg.decoder_v2.action02_value_context_profile._player_entities",
            return_value={0x3412},
        ), patch(
            "vg.decoder_v2.action02_value_context_profile.iter_credit_events",
            return_value=events,
        ):
            report = build_action02_value_context_profile("truth.json")

        row = report["rows"][0]
        self.assertEqual(row["value"], 20.0)
        patterns = {item["pattern"]: item["count"] for item in row["top_same_frame_patterns"]}
        self.assertEqual(patterns["0x06@3.0"], 1)
        self.assertEqual(patterns["0x08@0.6"], 1)


if __name__ == "__main__":
    unittest.main()
