import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vg.decoder_v2.index_export import build_index_ready_export


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


if __name__ == "__main__":
    unittest.main()
