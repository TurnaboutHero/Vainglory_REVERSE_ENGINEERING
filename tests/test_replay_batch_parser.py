import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vg.tools.replay_batch_parser import parse_replay


class TestReplayBatchParser(unittest.TestCase):
    def test_parse_replay_uses_map_name_from_match_info(self) -> None:
        parsed = {
            "game_mode": "GameMode_HF_Ranked",
            "match_info": {"map_name": "Halcyon Fold"},
            "teams": {
                "left": [{"name": "player1", "hero_name": "Alpha", "hero_id": 1, "entity_id": 10}],
                "right": [],
            },
        }

        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "vg.tools.replay_batch_parser.VGRParser"
        ) as parser_cls:
            parser_cls.return_value.parse.return_value = parsed
            result = parse_replay(Path(temp_dir) / "sample.0.vgr")

        self.assertEqual(result["map_name"], "Halcyon Fold")
        self.assertEqual(result["map_mode"], "Halcyon Fold")


if __name__ == "__main__":
    unittest.main()
