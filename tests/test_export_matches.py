import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vg.core.export_matches import decode_batch, export_csv, export_single
from vg.core.unified_decoder import DecodedMatch, DecodedPlayer


def make_match() -> DecodedMatch:
    player = DecodedPlayer(
        name="player1",
        team="left",
        hero_name="Alpha",
        hero_id=1,
        entity_id=100,
    )
    player.truth_kills = 5

    return DecodedMatch(
        replay_name="replay",
        replay_path="replay.0.vgr",
        game_mode="GameMode_HF_Ranked",
        map_name="Halcyon Fold",
        team_size=3,
        left_team=[player],
        right_team=[],
    )


class TestExportMatches(unittest.TestCase):
    def test_export_csv_accepts_heterogeneous_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "rows.csv"
            export_csv([{"a": 1}, {"a": 2, "b": 3}], output_path)

            with open(output_path, newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                self.assertEqual(reader.fieldnames, ["a", "b"])
                rows = list(reader)

        self.assertEqual(rows[1]["b"], "3")

    def test_export_single_respects_csv_only(self) -> None:
        match = make_match()

        with tempfile.TemporaryDirectory() as temp_dir:
            replay_path = Path(temp_dir) / "replay.0.vgr"
            replay_path.touch()

            json_path, csv_path = export_single(
                replay_path,
                match,
                output=temp_dir,
                csv_only=True,
            )

            self.assertIsNone(json_path)
            self.assertTrue(csv_path.exists())
            self.assertFalse((Path(temp_dir) / "replay.0_decoded.json").exists())

    def test_decode_batch_respects_csv_only(self) -> None:
        match = make_match()

        with tempfile.TemporaryDirectory() as temp_dir:
            replay_dir = Path(temp_dir) / "replays"
            replay_dir.mkdir()
            (replay_dir / "sample.0.vgr").touch()
            output_dir = Path(temp_dir) / "out"

            with patch("vg.core.export_matches.decode_single", return_value=match):
                matches = decode_batch(
                    str(replay_dir),
                    output_dir=str(output_dir),
                    csv_only=True,
                )

            self.assertEqual(len(matches), 1)
            self.assertTrue((output_dir / "all_matches.csv").exists())
            self.assertTrue((output_dir / "match_summary.csv").exists())
            self.assertFalse((output_dir / "match_1.json").exists())
            self.assertFalse((output_dir / "all_matches.json").exists())


if __name__ == "__main__":
    unittest.main()
