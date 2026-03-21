import unittest

from vg.decoder_v2.residual_signal_research import summarize_residual_candidate


class TestResidualSignalResearch(unittest.TestCase):
    def test_summarize_residual_candidate_tracks_positive_signal_metrics(self) -> None:
        rows = [
            {"residual_vs_0e": 0},
            {"residual_vs_0e": 2},
            {"residual_vs_0e": 1},
            {"residual_vs_0e": 0},
        ]
        counts = [0, 2, 1, 1]

        summary = summarize_residual_candidate(rows, counts)

        self.assertEqual(summary["rows"], 4)
        self.assertEqual(summary["positive_residual_rows"], 2)
        self.assertEqual(summary["support_rows"], 3)
        self.assertEqual(summary["support_positive_rows"], 2)
        self.assertEqual(summary["support_zero_or_negative_rows"], 1)
        self.assertAlmostEqual(summary["precision_positive"], 2 / 3)
        self.assertAlmostEqual(summary["recall_positive"], 1.0)
        self.assertAlmostEqual(summary["exact_match_positive_rate"], 1.0)
        self.assertAlmostEqual(summary["mae_to_residual"], 0.25)

    def test_summarize_residual_candidate_handles_empty_support(self) -> None:
        rows = [
            {"residual_vs_0e": 0},
            {"residual_vs_0e": 3},
        ]
        counts = [0, 0]

        summary = summarize_residual_candidate(rows, counts)

        self.assertEqual(summary["support_rows"], 0)
        self.assertEqual(summary["support_positive_rows"], 0)
        self.assertEqual(summary["precision_positive"], 0.0)
        self.assertEqual(summary["recall_positive"], 0.0)
        self.assertEqual(summary["exact_match_positive_rows"], 0)


if __name__ == "__main__":
    unittest.main()
