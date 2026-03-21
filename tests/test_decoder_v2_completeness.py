import unittest

from vg.decoder_v2.completeness import assess_completeness
from vg.decoder_v2.duration import estimate_duration_from_signals
from vg.decoder_v2.models import CompletenessStatus, ReplaySignalSummary


class TestDecoderV2Completeness(unittest.TestCase):
    def test_complete_confirmed_from_crystal_and_death_alignment(self) -> None:
        signals = ReplaySignalSummary(
            replay_name="match",
            replay_file="match.0.vgr",
            frame_count=120,
            max_frame_index=119,
            crystal_ts=1000.0,
            max_kill_ts=990.0,
            max_player_death_ts=1008.0,
            max_death_header_ts=1008.0,
            max_item_ts=995.0,
        )

        assessment = assess_completeness(signals)

        self.assertEqual(assessment.status, CompletenessStatus.COMPLETE_CONFIRMED)

    def test_incomplete_confirmed_from_short_tail_gap_pattern(self) -> None:
        signals = ReplaySignalSummary(
            replay_name="match",
            replay_file="match.0.vgr",
            frame_count=85,
            max_frame_index=84,
            crystal_ts=None,
            max_kill_ts=471.5,
            max_player_death_ts=473.4,
            max_death_header_ts=846.3,
            max_item_ts=849.9,
        )

        assessment = assess_completeness(signals)
        duration = estimate_duration_from_signals(signals)

        self.assertEqual(assessment.status, CompletenessStatus.INCOMPLETE_CONFIRMED)
        self.assertIsNone(duration.estimate_seconds)
        self.assertEqual(duration.source, "unknown")

    def test_duration_prefers_crystal_when_consistent(self) -> None:
        signals = ReplaySignalSummary(
            replay_name="match",
            replay_file="match.0.vgr",
            frame_count=120,
            max_frame_index=119,
            crystal_ts=1029.2,
            max_kill_ts=1014.1,
            max_player_death_ts=1039.6,
            max_death_header_ts=1039.6,
            max_item_ts=1036.7,
        )

        duration = estimate_duration_from_signals(signals)

        self.assertEqual(duration.source, "crystal")
        self.assertEqual(duration.estimate_seconds, 1029)

    def test_duration_falls_back_to_max_death(self) -> None:
        signals = ReplaySignalSummary(
            replay_name="match",
            replay_file="match.0.vgr",
            frame_count=149,
            max_frame_index=148,
            crystal_ts=1221.3,
            max_kill_ts=1484.4,
            max_player_death_ts=1486.2,
            max_death_header_ts=1486.2,
            max_item_ts=1467.8,
        )

        duration = estimate_duration_from_signals(signals)

        self.assertEqual(duration.source, "max_death")
        self.assertEqual(duration.estimate_seconds, 1486)

    def test_complete_confirmed_from_long_tail_without_reliable_crystal(self) -> None:
        signals = ReplaySignalSummary(
            replay_name="match",
            replay_file="match.0.vgr",
            frame_count=149,
            max_frame_index=148,
            crystal_ts=1221.3,
            max_kill_ts=1484.4,
            max_player_death_ts=1486.2,
            max_death_header_ts=1486.2,
            max_item_ts=1467.8,
        )

        assessment = assess_completeness(signals)

        self.assertEqual(assessment.status, CompletenessStatus.COMPLETE_CONFIRMED)

    def test_complete_confirmed_from_consistent_late_tails(self) -> None:
        signals = ReplaySignalSummary(
            replay_name="match",
            replay_file="match.0.vgr",
            frame_count=119,
            max_frame_index=118,
            crystal_ts=1091.7,
            max_kill_ts=1156.0,
            max_player_death_ts=1157.9,
            max_death_header_ts=1184.0,
            max_item_ts=1181.9,
        )

        assessment = assess_completeness(signals)

        self.assertEqual(assessment.status, CompletenessStatus.COMPLETE_CONFIRMED)


if __name__ == "__main__":
    unittest.main()
