import unittest
from unittest.mock import patch

from vg.decoder_v2.kda_postgame_audit import build_kda_postgame_audit


class _DummySummary:
    def __init__(self, payload):
        self._payload = payload

    def to_dict(self):
        return self._payload


class TestKdaPostgameAudit(unittest.TestCase):
    def test_build_kda_postgame_audit_summarizes_buffers_and_late_events(self) -> None:
        matches = [{"replay_name": "a"}, {"replay_name": "b"}]
        summary = _DummySummary(
            {
                "matches_total": 2,
                "records_total": 20,
                "team_bytes_seen": {"1": 10, "2": 10},
                "entity_nonzero_records": 20,
                "hero_matches": 20,
                "hero_total": 20,
            }
        )
        row_a = {
            "replay_name": "a",
            "fixture_directory": "1",
            "replay_file": "a.0.vgr",
            "duration_truth": 1000,
            "is_incomplete_fixture": False,
            "matched_players": 10,
            "late_kills": [
                {"player_name": "p1", "timestamp": 1004.0, "delta_after_duration": 4.0, "frame_idx": 100},
            ],
            "late_deaths": [
                {"player_name": "p2", "timestamp": 1002.0, "delta_after_duration": 2.0, "frame_idx": 100},
                {"player_name": "p3", "timestamp": 1012.0, "delta_after_duration": 12.0, "frame_idx": 101},
            ],
            "config_results": {
                "k3_d10": {
                    "kills_correct": 10,
                    "kills_total": 10,
                    "deaths_correct": 10,
                    "deaths_total": 10,
                    "assists_correct": 9,
                    "assists_total": 10,
                },
                "k3_d0": {
                    "kills_correct": 10,
                    "kills_total": 10,
                    "deaths_correct": 9,
                    "deaths_total": 10,
                    "assists_correct": 9,
                    "assists_total": 10,
                },
            },
        }
        row_b = {
            "replay_name": "b",
            "fixture_directory": "5 (Incomplete)",
            "replay_file": "b.0.vgr",
            "duration_truth": 1200,
            "is_incomplete_fixture": True,
            "matched_players": 10,
            "late_kills": [],
            "late_deaths": [],
            "config_results": {
                "k3_d10": {
                    "kills_correct": 6,
                    "kills_total": 10,
                    "deaths_correct": 5,
                    "deaths_total": 10,
                    "assists_correct": 5,
                    "assists_total": 10,
                },
                "k3_d0": {
                    "kills_correct": 6,
                    "kills_total": 10,
                    "deaths_correct": 4,
                    "deaths_total": 10,
                    "assists_correct": 5,
                    "assists_total": 10,
                },
            },
        }

        with patch(
            "vg.decoder_v2.kda_postgame_audit._load_truth_matches",
            return_value=matches,
        ), patch(
            "vg.decoder_v2.kda_postgame_audit.validate_player_block_claims",
            return_value=summary,
        ), patch(
            "vg.decoder_v2.kda_postgame_audit._build_match_audit",
            side_effect=[row_a, row_b],
        ):
            report = build_kda_postgame_audit("truth.json", buffer_configs=((3, 10), (3, 0)))

        self.assertEqual(report["team_grouping_validation"]["team_bytes_seen"], {"1": 10, "2": 10})
        self.assertEqual(report["late_event_summary"]["kills_after_duration"], 1)
        self.assertEqual(report["late_event_summary"]["kills_after_duration_plus_3"], 1)
        self.assertEqual(report["late_event_summary"]["deaths_after_duration"], 2)
        self.assertEqual(report["late_event_summary"]["deaths_after_duration_plus_3"], 1)
        self.assertEqual(report["late_event_summary"]["deaths_after_duration_plus_10"], 1)
        self.assertEqual(report["buffer_config_summary"]["k3_d10"]["all_matches"]["kills"]["correct"], 16)
        self.assertEqual(report["buffer_config_summary"]["k3_d10"]["complete_only"]["deaths"]["correct"], 10)
        self.assertEqual(report["buffer_config_summary"]["k3_d0"]["all_matches"]["deaths"]["correct"], 13)


if __name__ == "__main__":
    unittest.main()
