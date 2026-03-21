import unittest
from unittest.mock import patch

from vg.core.hero_matcher import HeroCandidate
from vg.core.replay_extractor import ReplayExtractor


class TestReplayExtractor(unittest.TestCase):
    def test_extract_uses_current_hero_matcher_api(self) -> None:
        parsed = {
            "replay_name": "replay",
            "replay_file": "replay.0.vgr",
            "match_info": {
                "mode": "GameMode_HF_Ranked",
                "mode_friendly": "3v3 Ranked (Halcyon Fold)",
                "map_name": "Halcyon Fold",
                "team_size": 3,
                "total_frames": 42,
            },
            "teams": {
                "left": [
                    {
                        "name": "player1",
                        "team": "left",
                        "position": 0,
                        "entity_id": 111,
                        "hero_name": "Unknown",
                        "hero_id": None,
                    }
                ],
                "right": [],
            },
        }

        with patch("vg.core.replay_extractor.VGRParser") as parser_cls, patch(
            "vg.core.replay_extractor.HeroMatcher"
        ) as matcher_cls, patch.object(
            ReplayExtractor, "_read_all_frames", return_value=b"frame-bytes"
        ):
            parser_cls.return_value.parse.return_value = parsed
            matcher_cls.return_value.detect_heroes.return_value = [
                HeroCandidate(hero_id=999, hero_name="Alpha", confidence=1.0, source="binary")
            ]

            match = ReplayExtractor("replay.0.vgr").extract()

        self.assertEqual(match.left_team[0].hero_name, "Alpha")
        self.assertEqual(match.left_team[0].hero_id, 999)
        self.assertEqual(match.left_team[0].hero_source, "binary")


if __name__ == "__main__":
    unittest.main()
