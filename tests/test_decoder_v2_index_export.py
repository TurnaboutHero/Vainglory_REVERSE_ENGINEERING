import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vg.decoder_v2.index_export import build_index_ready_export


class _FakeDecision:
    def __init__(self, accepted: bool, baseline_0e: int):
        self.accepted = accepted
        self.baseline_0e = baseline_0e

    def to_dict(self):
        return {"accepted": self.accepted, "baseline_0e": self.baseline_0e}


class TestDecoderV2IndexExport(unittest.TestCase):
    def test_build_index_ready_export_keeps_only_accepted_fields(self) -> None:
        batch = {
            "total_replays": 1,
            "completeness_summary": {"complete_confirmed": 1},
            "matches": [
                {
                    "replay_name": "sample",
                    "replay_file": "sample.0.vgr",
                    "game_mode": "GameMode_HF_Ranked",
                    "map_name": "Halcyon Fold",
                    "team_size": 3,
                    "completeness_status": "complete_confirmed",
                    "accepted_fields": {
                        "winner": {"accepted_for_index": True, "value": "left"},
                        "kills": {"accepted_for_index": True},
                    },
                    "players": [
                        {
                            "name": "player1",
                            "team": "left",
                            "entity_id": 1,
                            "hero_name": "Alpha",
                            "kills": 1,
                            "deaths": 2,
                            "assists": 3,
                        }
                    ],
                }
            ],
        }

        with patch("vg.decoder_v2.index_export.decode_replay_batch", return_value=batch):
            export = build_index_ready_export(tempfile.gettempdir())

        self.assertEqual(export["matches"][0]["winner"], "left")
        self.assertEqual(export["matches"][0]["players"][0]["kills"], 1)
        self.assertNotIn("withheld_fields", export["matches"][0])

    def test_build_index_ready_export_can_include_nonfinals_minion_policy(self) -> None:
        batch = {
            "total_replays": 1,
            "completeness_summary": {"complete_confirmed": 1},
            "matches": [
                {
                    "replay_name": "sample",
                    "replay_file": r"C:\replays\Semis\1\sample.0.vgr",
                    "game_mode": "GameMode_HF_Ranked",
                    "map_name": "Halcyon Fold",
                    "team_size": 3,
                    "completeness_status": "complete_confirmed",
                    "accepted_fields": {
                        "winner": {"accepted_for_index": True, "value": "left"},
                        "kills": {"accepted_for_index": True},
                    },
                    "players": [
                        {
                            "name": "player1",
                            "team": "left",
                            "entity_id": 1,
                            "hero_name": "Alpha",
                            "kills": 1,
                            "deaths": 2,
                            "assists": 3,
                        }
                    ],
                }
            ],
        }

        with patch("vg.decoder_v2.index_export.decode_replay_batch", return_value=batch), patch(
            "vg.decoder_v2.index_export.evaluate_player_minion_policy",
            return_value={"player1": _FakeDecision(True, 42)},
        ):
            export = build_index_ready_export(tempfile.gettempdir(), minion_policy="nonfinals-baseline-0e")

        self.assertEqual(export["minion_policy"], "nonfinals-baseline-0e")
        self.assertEqual(export["matches"][0]["players"][0]["minion_kills"], 42)
        self.assertTrue(export["matches"][0]["minion_policy"]["accepted_match"])

    def test_build_index_ready_export_keeps_finals_minion_withheld_under_policy(self) -> None:
        batch = {
            "total_replays": 1,
            "completeness_summary": {"complete_confirmed": 1},
            "matches": [
                {
                    "replay_name": "sample",
                    "replay_file": r"C:\replays\SFC vs Law Enforcers (Finals)\2\sample.0.vgr",
                    "game_mode": "GameMode_HF_Ranked",
                    "map_name": "Halcyon Fold",
                    "team_size": 3,
                    "completeness_status": "complete_confirmed",
                    "accepted_fields": {},
                    "players": [
                        {
                            "name": "player1",
                            "team": "left",
                            "entity_id": 1,
                            "hero_name": "Alpha",
                        }
                    ],
                }
            ],
        }

        with patch("vg.decoder_v2.index_export.decode_replay_batch", return_value=batch), patch(
            "vg.decoder_v2.index_export.evaluate_player_minion_policy",
            return_value={"player1": _FakeDecision(False, 42)},
        ):
            export = build_index_ready_export(tempfile.gettempdir(), minion_policy="nonfinals-baseline-0e")

        self.assertNotIn("minion_kills", export["matches"][0]["players"][0])
        self.assertFalse(export["matches"][0]["minion_policy"]["accepted_match"])

    def test_build_index_ready_export_can_partially_accept_finals_players_under_experimental_policy(self) -> None:
        batch = {
            "total_replays": 1,
            "completeness_summary": {"complete_confirmed": 1},
            "matches": [
                {
                    "replay_name": "sample",
                    "replay_file": r"C:\replays\SFC vs Law Enforcers (Finals)\2\sample.0.vgr",
                    "game_mode": "GameMode_HF_Ranked",
                    "map_name": "Halcyon Fold",
                    "team_size": 3,
                    "completeness_status": "complete_confirmed",
                    "accepted_fields": {},
                    "players": [
                        {
                            "name": "player1",
                            "team": "left",
                            "entity_id": 1,
                            "hero_name": "Alpha",
                        },
                        {
                            "name": "player2",
                            "team": "right",
                            "entity_id": 2,
                            "hero_name": "Beta",
                        },
                    ],
                }
            ],
        }

        with patch("vg.decoder_v2.index_export.decode_replay_batch", return_value=batch), patch(
            "vg.decoder_v2.index_export.evaluate_player_minion_policy",
            return_value={
                "player1": _FakeDecision(True, 42),
                "player2": _FakeDecision(False, 99),
            },
        ):
            export = build_index_ready_export(
                tempfile.gettempdir(),
                minion_policy="nonfinals-or-low-mixed-ratio-experimental",
            )

        self.assertFalse(export["matches"][0]["minion_policy"]["accepted_match"])
        self.assertEqual(export["matches"][0]["minion_policy"]["accepted_player_count"], 1)
        self.assertEqual(export["matches"][0]["players"][0]["minion_kills"], 42)
        self.assertNotIn("minion_kills", export["matches"][0]["players"][1])


if __name__ == "__main__":
    unittest.main()
