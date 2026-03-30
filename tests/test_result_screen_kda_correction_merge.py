import unittest

from vg.tools.result_screen_kda_correction_merge import build_result_screen_kda_correction_merge


class TestResultScreenKdaCorrectionMerge(unittest.TestCase):
    def test_merge_applies_corrected_kda(self) -> None:
        decoded = {
            "safe_output": {
                "replay_name": "sample",
                "replay_file": "sample.0.vgr",
                "players": [
                    {"name": "a", "kills": 0, "deaths": 0, "assists": 0},
                    {"name": "b", "kills": 1, "deaths": 1, "assists": 1},
                ]
            }
        }
        correction = {
            "player_rows": [
                {"name": "a", "corrected_kda": "12/1/4", "correction_status": "name_bound_unique"},
                {"name": "b", "corrected_kda": None, "correction_status": "unresolved"},
            ]
        }

        merged = build_result_screen_kda_correction_merge(decoded, correction)

        self.assertEqual(merged["replay_name"], "sample")
        self.assertEqual(merged["replay_file"], "sample.0.vgr")
        self.assertEqual(merged["corrected_rows"], 1)
        self.assertEqual(merged["unresolved_rows"], 1)
        self.assertEqual(merged["players"][0]["kills"], 12)
        self.assertEqual(merged["players"][0]["deaths"], 1)
        self.assertEqual(merged["players"][0]["assists"], 4)
        self.assertEqual(merged["players"][0]["kda_correction_status"], "name_bound_unique")
        self.assertEqual(merged["players"][1]["kda_correction_status"], "unresolved")


if __name__ == "__main__":
    unittest.main()
