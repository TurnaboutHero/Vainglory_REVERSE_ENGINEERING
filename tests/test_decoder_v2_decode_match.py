import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vg.decoder_v2.decode_match import decode_match, decode_match_debug, main
from vg.decoder_v2.models import (
    AcceptedPlayerFields,
    CompletenessAssessment,
    CompletenessStatus,
    DurationEstimate,
    KDAExtractionResult,
    KDAPlayerSummary,
    ReplaySignalSummary,
    WinnerExtractionResult,
)


def make_assessment(status: CompletenessStatus) -> CompletenessAssessment:
    signals = ReplaySignalSummary(
        replay_name="match",
        replay_file="match.0.vgr",
        frame_count=100,
        max_frame_index=99,
        crystal_ts=1000.0 if status == CompletenessStatus.COMPLETE_CONFIRMED else None,
        max_kill_ts=990.0,
        max_player_death_ts=1008.0 if status == CompletenessStatus.COMPLETE_CONFIRMED else 473.4,
        max_death_header_ts=1008.0 if status == CompletenessStatus.COMPLETE_CONFIRMED else 846.3,
        max_item_ts=995.0,
    )
    return CompletenessAssessment(
        status=status,
        reason=status.value,
        signals=signals,
    )


class TestDecoderV2DecodeMatch(unittest.TestCase):
    def test_decode_match_withholds_derived_fields_on_incomplete(self) -> None:
        parsed = {
            "replay_name": "match",
            "replay_file": "match.0.vgr",
            "match_info": {
                "mode": "GameMode_HF_Ranked",
                "map_name": "Halcyon Fold",
                "team_size": 3,
            },
            "teams": {
                "left": [{"name": "player1", "team": "left", "entity_id": 1, "hero_name": "Alpha"}],
                "right": [],
            },
        }
        assessment = make_assessment(CompletenessStatus.INCOMPLETE_CONFIRMED)
        duration = DurationEstimate(estimate_seconds=None, source="unknown", assessment=assessment)

        with patch("vg.decoder_v2.decode_match.VGRParser") as parser_cls, patch(
            "vg.decoder_v2.decode_match.decode_winner_from_replay"
        ) as winner_mock, patch(
            "vg.decoder_v2.decode_match.decode_kda_from_replay"
        ) as kda_mock:
            parser_cls.return_value.parse.return_value = parsed
            winner_mock.return_value = WinnerExtractionResult(
                accepted=False,
                reason="winner withheld",
                assessment=assessment,
                duration_estimate=duration,
                winner=None,
                left_kills=None,
                right_kills=None,
            )
            kda_mock.return_value = KDAExtractionResult(
                accepted=False,
                reason="kda withheld",
                assessment=assessment,
                duration_estimate=duration,
                players=(),
            )

            output = decode_match("match.0.vgr")

        self.assertEqual(output.completeness_status, "incomplete_confirmed")
        self.assertIn("winner", output.withheld_fields)
        self.assertIn("kills", output.withheld_fields)
        self.assertEqual(output.players[0].hero_name, "Alpha")
        self.assertIsNone(output.players[0].kills)
        self.assertFalse(output.withheld_fields["winner"].accepted_for_index)

    def test_decode_match_emits_kda_on_complete(self) -> None:
        parsed = {
            "replay_name": "match",
            "replay_file": "match.0.vgr",
            "match_info": {
                "mode": "GameMode_HF_Ranked",
                "map_name": "Halcyon Fold",
                "team_size": 3,
            },
            "teams": {
                "left": [{"name": "player1", "team": "left", "entity_id": 1, "hero_name": "Alpha"}],
                "right": [],
            },
        }
        assessment = make_assessment(CompletenessStatus.COMPLETE_CONFIRMED)
        duration = DurationEstimate(estimate_seconds=1000, source="crystal", assessment=assessment)

        with patch("vg.decoder_v2.decode_match.VGRParser") as parser_cls, patch(
            "vg.decoder_v2.decode_match.decode_winner_from_replay"
        ) as winner_mock, patch(
            "vg.decoder_v2.decode_match.decode_kda_from_replay"
        ) as kda_mock:
            parser_cls.return_value.parse.return_value = parsed
            winner_mock.return_value = WinnerExtractionResult(
                accepted=True,
                reason="winner accepted",
                assessment=assessment,
                duration_estimate=duration,
                winner="left",
                left_kills=1,
                right_kills=0,
            )
            kda_mock.return_value = KDAExtractionResult(
                accepted=True,
                reason="kda accepted",
                assessment=assessment,
                duration_estimate=duration,
                players=(
                    KDAPlayerSummary(
                        player_name="player1",
                        team="left",
                        hero_name="Alpha",
                        kills=1,
                        deaths=0,
                        assists=2,
                        minion_kills=3,
                    ),
                ),
            )

            output = decode_match("match.0.vgr")

        self.assertEqual(output.accepted_fields["winner"].value, "left")
        self.assertTrue(output.accepted_fields["winner"].accepted_for_index)
        self.assertEqual(output.players[0].kills, 1)
        self.assertIn("duration_seconds", output.withheld_fields)
        self.assertEqual(output.schema_version, "decoder_v2.match.v1")

    def test_decode_match_debug_includes_signals_and_minion_candidates(self) -> None:
        assessment = make_assessment(CompletenessStatus.COMPLETE_CONFIRMED)
        duration = DurationEstimate(estimate_seconds=1000, source="crystal", assessment=assessment)

        with patch("vg.decoder_v2.decode_match.decode_match") as safe_mock, patch(
            "vg.decoder_v2.decode_match.decode_winner_from_replay"
        ) as winner_mock, patch(
            "vg.decoder_v2.decode_match.decode_kda_from_replay"
        ) as kda_mock, patch(
            "vg.decoder_v2.decode_match.collect_minion_candidates"
        ) as minion_mock:
            safe_mock.return_value = object_with_to_dict({"safe": True})
            winner_mock.return_value = WinnerExtractionResult(
                accepted=True,
                reason="winner accepted",
                assessment=assessment,
                duration_estimate=duration,
                winner="left",
                left_kills=1,
                right_kills=0,
            )
            kda_mock.return_value = KDAExtractionResult(
                accepted=True,
                reason="kda accepted",
                assessment=assessment,
                duration_estimate=duration,
                players=(),
            )
            minion_mock.return_value = []

            payload = decode_match_debug("match.0.vgr")

        self.assertEqual(payload["schema_version"], "decoder_v2.debug_match.v1")
        self.assertIn("completeness", payload)
        self.assertIn("duration", payload)
        self.assertIn("minion_candidates", payload)

    def test_main_writes_debug_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "vg.decoder_v2.decode_match.decode_match_debug",
            return_value={"schema_version": "decoder_v2.debug_match.v1"},
        ):
            output_path = Path(temp_dir) / "debug.json"
            exit_code = main(["match.0.vgr", "--format", "debug-json", "-o", str(output_path)])
            saved = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(saved["schema_version"], "decoder_v2.debug_match.v1")


def object_with_to_dict(payload):
    class _Obj:
        def to_dict(self):
            return payload

    return _Obj()


if __name__ == "__main__":
    unittest.main()
