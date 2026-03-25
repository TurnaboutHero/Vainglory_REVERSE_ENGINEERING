import unittest
from pathlib import Path
from unittest.mock import patch

from vg.decoder_v2.completeness_audit import build_completeness_audit
from vg.decoder_v2.models import CompletenessAssessment, CompletenessStatus, ReplaySignalSummary


class TestCompletenessAudit(unittest.TestCase):
    def test_build_completeness_audit_collects_review_flags(self) -> None:
        replays = [Path("a.0.vgr"), Path("b.0.vgr")]
        signals_a = ReplaySignalSummary(
            replay_name="a",
            replay_file="a.0.vgr",
            frame_count=150,
            max_frame_index=149,
            crystal_ts=None,
            max_kill_ts=1480.0,
            max_player_death_ts=1486.0,
            max_death_header_ts=1486.0,
            max_item_ts=1470.0,
        )
        signals_b = ReplaySignalSummary(
            replay_name="b",
            replay_file="b.0.vgr",
            frame_count=130,
            max_frame_index=129,
            crystal_ts=1000.0,
            max_kill_ts=900.0,
            max_player_death_ts=1100.0,
            max_death_header_ts=1190.0,
            max_item_ts=1180.0,
        )
        assessments = [
            CompletenessAssessment(
                status=CompletenessStatus.COMPLETE_CONFIRMED,
                reason="complete",
                signals=signals_a,
            ),
            CompletenessAssessment(
                status=CompletenessStatus.COMPLETENESS_UNKNOWN,
                reason="unknown",
                signals=signals_b,
            ),
        ]

        with patch("vg.decoder_v2.completeness_audit.find_replays", return_value=replays), patch(
            "vg.decoder_v2.completeness_audit.extract_replay_signals",
            side_effect=[signals_a, signals_b],
        ), patch(
            "vg.decoder_v2.completeness_audit.assess_completeness",
            side_effect=assessments,
        ):
            report = build_completeness_audit("C:/replays")

        self.assertEqual(report["total_replays"], 2)
        self.assertEqual(report["status_summary"]["complete_confirmed"], 1)
        self.assertEqual(report["status_summary"]["completeness_unknown"], 1)
        self.assertEqual(report["review_bucket_summary"]["accepted_without_crystal"], 1)
        self.assertEqual(report["review_bucket_summary"]["conflicting_long_tail_signals"], 1)
        self.assertTrue(any("complete_without_crystal" in row["review_flags"] for row in report["review_queue"]))
        self.assertTrue(any("unknown_long_replay" in row["review_flags"] for row in report["review_queue"]))


if __name__ == "__main__":
    unittest.main()
