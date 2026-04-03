import unittest

from vg.decoder_v2.kda_result_capture_backlog import build_kda_result_capture_backlog


class TestKdaResultCaptureBacklog(unittest.TestCase):
    def test_backlog_prioritizes_truth_residuals(self) -> None:
        readiness = {
            "rows": [
                {
                    "replay_name": "sample",
                    "has_result_dump": False,
                    "has_bundle": False,
                    "has_corrected_export": False,
                    "decoded_payload_path": "debug.json",
                    "status": "missing_result_dump",
                }
            ]
        }
        mismatch = {
            "rows": [
                {
                    "replay_name": "sample",
                    "fixture_directory": "1",
                    "replay_file": r"C:\replays\SFC vs Law Enforcers (Finals)\1\sample.0.vgr",
                    "player_name": "player1",
                    "diff": {"kills": 1, "deaths": 0, "assists": 0},
                }
            ]
        }

        report = build_kda_result_capture_backlog(readiness, mismatch)

        self.assertEqual(report["rows"][0]["priority"], 1)
        self.assertTrue(report["rows"][0]["reason"][0].startswith("truth_residual"))


if __name__ == "__main__":
    unittest.main()
