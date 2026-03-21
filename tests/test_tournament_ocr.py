import tempfile
import unittest
from pathlib import Path

from vg.ocr import tournament_ocr


class TestTournamentOCR(unittest.TestCase):
    def test_build_mapping_includes_png_pairs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            match_dir = Path(temp_dir) / "match1"
            match_dir.mkdir()
            (match_dir / "result.png").touch()
            replay = match_dir / "sample.0.vgr"
            replay.touch()

            pairs = tournament_ocr.build_mapping(Path(temp_dir))

        self.assertEqual(pairs, [(match_dir / "result.png", replay)])

    def test_main_returns_error_when_no_pairs_found(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = tournament_ocr.main([temp_dir])

        self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()
