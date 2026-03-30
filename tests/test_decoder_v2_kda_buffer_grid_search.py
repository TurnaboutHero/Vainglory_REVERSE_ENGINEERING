import unittest
from unittest.mock import patch

from vg.decoder_v2.kda_buffer_grid_search import build_kda_buffer_grid_search


class TestKDABufferGridSearch(unittest.TestCase):
    @patch("vg.decoder_v2.kda_buffer_grid_search.build_kda_postgame_audit")
    def test_build_kda_buffer_grid_search_sorts_best_config_first(self, mock_audit) -> None:
        mock_audit.return_value = {
            "buffer_config_summary": {
                "k3_d10": {
                    "kill_buffer": 3,
                    "death_buffer": 10,
                    "complete_only": {
                        "kills": {"pct": 94.0},
                        "deaths": {"pct": 95.0},
                        "assists": {"pct": 91.0},
                        "combined_kda": {"pct": 93.0, "correct": 279, "total": 300},
                    },
                },
                "k20_d8": {
                    "kill_buffer": 20,
                    "death_buffer": 8,
                    "complete_only": {
                        "kills": {"pct": 98.0},
                        "deaths": {"pct": 97.0},
                        "assists": {"pct": 97.0},
                        "combined_kda": {"pct": 97.3, "correct": 292, "total": 300},
                    },
                },
            }
        }

        report = build_kda_buffer_grid_search("truth.json", kill_buffers=[3, 20], death_buffers=[8, 10])

        self.assertEqual(report["best_config"]["config_key"], "k20_d8")
        self.assertEqual(report["rows"][0]["config_key"], "k20_d8")


if __name__ == "__main__":
    unittest.main()
