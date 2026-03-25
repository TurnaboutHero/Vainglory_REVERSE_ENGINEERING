import unittest

from vg.decoder_v2.completeness import _scan_max_timestamp, assess_completeness
from vg.decoder_v2.duration import estimate_duration_from_signals
from vg.decoder_v2.models import CompletenessStatus, ReplaySignalSummary


class TestDecoderV2Completeness(unittest.TestCase):
    def test_scan_max_timestamp_does_not_cross_frame_boundaries(self) -> None:
        frame_a = b"\x00\x08\x04"
        frame_b = b"\x31\x00\x00\x07\xd0\x00\x00\x44\xc5\x40\x00"

        value = _scan_max_timestamp(
            [(0, frame_a), (1, frame_b)],
            b"\x08\x04\x31",
            9,
            guards=((3, b"\x00\x00"), (7, b"\x00\x00")),
        )

        self.assertIsNone(value)

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

    def test_complete_confirmed_from_medium_no_crystal_consistent_tails(self) -> None:
        signals = ReplaySignalSummary(
            replay_name="match",
            replay_file="match.0.vgr",
            frame_count=103,
            max_frame_index=102,
            crystal_ts=None,
            max_kill_ts=1010.0,
            max_player_death_ts=1021.1,
            max_death_header_ts=1026.2,
            max_item_ts=1020.4,
        )

        assessment = assess_completeness(signals)

        self.assertEqual(assessment.status, CompletenessStatus.COMPLETE_CONFIRMED)

    def test_complete_confirmed_from_long_no_crystal_item_within_75s(self) -> None:
        signals = ReplaySignalSummary(
            replay_name="match",
            replay_file="match.0.vgr",
            frame_count=135,
            max_frame_index=134,
            crystal_ts=None,
            max_kill_ts=1333.1,
            max_player_death_ts=1334.9,
            max_death_header_ts=1339.3,
            max_item_ts=1267.5,
        )

        assessment = assess_completeness(signals)

        self.assertEqual(assessment.status, CompletenessStatus.COMPLETE_CONFIRMED)

    def test_complete_confirmed_from_no_crystal_stale_player_death(self) -> None:
        signals = ReplaySignalSummary(
            replay_name="match",
            replay_file="match.0.vgr",
            frame_count=129,
            max_frame_index=128,
            crystal_ts=None,
            max_kill_ts=1172.2,
            max_player_death_ts=1174.0,
            max_death_header_ts=1276.4,
            max_item_ts=1222.0,
        )

        assessment = assess_completeness(signals)

        self.assertEqual(assessment.status, CompletenessStatus.COMPLETE_CONFIRMED)

    def test_complete_confirmed_from_stale_player_death_tail(self) -> None:
        signals = ReplaySignalSummary(
            replay_name="match",
            replay_file="match.0.vgr",
            frame_count=193,
            max_frame_index=192,
            crystal_ts=1907.6,
            max_kill_ts=1700.0,
            max_player_death_ts=1713.1,
            max_death_header_ts=1915.9,
            max_item_ts=1907.4,
        )

        assessment = assess_completeness(signals)

        self.assertEqual(assessment.status, CompletenessStatus.COMPLETE_CONFIRMED)

    def test_complete_confirmed_from_slightly_early_crystal(self) -> None:
        signals = ReplaySignalSummary(
            replay_name="match",
            replay_file="match.0.vgr",
            frame_count=98,
            max_frame_index=97,
            crystal_ts=923.6,
            max_kill_ts=963.8,
            max_player_death_ts=967.5,
            max_death_header_ts=967.5,
            max_item_ts=968.1,
        )

        assessment = assess_completeness(signals)

        self.assertEqual(assessment.status, CompletenessStatus.COMPLETE_CONFIRMED)

    def test_complete_confirmed_from_short_replay_crystal_lag(self) -> None:
        signals = ReplaySignalSummary(
            replay_name="match",
            replay_file="match.0.vgr",
            frame_count=81,
            max_frame_index=80,
            crystal_ts=657.9,
            max_kill_ts=758.8,
            max_player_death_ts=760.6,
            max_death_header_ts=777.2,
            max_item_ts=801.8,
        )

        assessment = assess_completeness(signals)

        self.assertEqual(assessment.status, CompletenessStatus.COMPLETE_CONFIRMED)

    def test_complete_confirmed_from_stale_crystal_against_aligned_header_item_tail(self) -> None:
        signals = ReplaySignalSummary(
            replay_name="match",
            replay_file="match.0.vgr",
            frame_count=192,
            max_frame_index=191,
            crystal_ts=1577.4,
            max_kill_ts=1769.1,
            max_player_death_ts=1770.9,
            max_death_header_ts=1909.5,
            max_item_ts=1861.9,
        )

        assessment = assess_completeness(signals)

        self.assertEqual(assessment.status, CompletenessStatus.COMPLETE_CONFIRMED)

    def test_tiny_replay_is_incomplete_confirmed(self) -> None:
        signals = ReplaySignalSummary(
            replay_name="match",
            replay_file="match.0.vgr",
            frame_count=7,
            max_frame_index=6,
            crystal_ts=None,
            max_kill_ts=None,
            max_player_death_ts=None,
            max_death_header_ts=64.3,
            max_item_ts=30.7,
        )

        assessment = assess_completeness(signals)

        self.assertEqual(assessment.status, CompletenessStatus.INCOMPLETE_CONFIRMED)


if __name__ == "__main__":
    unittest.main()
