import unittest
from unittest.mock import patch

from vg.decoder_v2.minion_action_self_vs_team import build_minion_action_self_vs_team
from vg.decoder_v2.models import CreditEventRecord


class TestMinionActionSelfVsTeam(unittest.TestCase):
    def test_build_minion_action_self_vs_team_counts_self_and_teammate_links(self) -> None:
        truth_payload = {
            "matches": [
                {
                    "replay_name": "target",
                    "replay_file": "target.0.vgr",
                    "players": {},
                }
            ]
        }
        parsed = {
            "teams": {
                "left": [{"name": "p1", "entity_id": 0x1234}, {"name": "p2", "entity_id": 0x1235}],
                "right": [{"name": "p3", "entity_id": 0x1236}],
            }
        }
        events = [
            CreditEventRecord(frame_idx=10, entity_id_be=0x3412, action=0x02, value=20.0, file_offset=10, raw_record_hex="", padding_ok=True, value_is_finite=True),
            CreditEventRecord(frame_idx=10, entity_id_be=0x3412, action=0x0E, value=1.0, file_offset=20, raw_record_hex="", padding_ok=True, value_is_finite=True),
            CreditEventRecord(frame_idx=10, entity_id_be=0x3512, action=0x0F, value=1.0, file_offset=30, raw_record_hex="", padding_ok=True, value_is_finite=True),
            CreditEventRecord(frame_idx=10, entity_id_be=0x3612, action=0x0E, value=1.0, file_offset=40, raw_record_hex="", padding_ok=True, value_is_finite=True),
        ]

        with patch(
            "vg.decoder_v2.minion_action_self_vs_team.build_minion_outlier_compare",
            return_value={"credit_pattern_rate_deltas": [{"pattern": "0x02@20.0"}]},
        ), patch(
            "pathlib.Path.read_text",
            return_value='{"matches":[{"replay_name":"target","replay_file":"target.0.vgr","players":{}}]}',
        ), patch(
            "vg.decoder_v2.minion_action_self_vs_team.VGRParser",
        ) as parser_cls, patch(
            "vg.decoder_v2.minion_action_self_vs_team.iter_credit_events",
            return_value=events,
        ):
            parser_cls.return_value.parse.return_value = parsed
            report = build_minion_action_self_vs_team("truth.json", "target", action_hex="0x02", top_pattern_limit=1)

        row = report["rows"][0]
        self.assertEqual(row["self_0e_count"], 1)
        self.assertEqual(row["teammate_0f_count"], 1)
        self.assertEqual(row["opponent_0e_count"], 1)
        self.assertEqual(row["self_presence_count"], 1)
        self.assertEqual(row["teammate_presence_count"], 1)
        self.assertEqual(row["opponent_presence_count"], 1)


if __name__ == "__main__":
    unittest.main()
