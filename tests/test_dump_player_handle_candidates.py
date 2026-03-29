import tempfile
import unittest
from pathlib import Path

from vg.tools.dump_player_handle_candidates import build_player_handle_candidates


class TestDumpPlayerHandleCandidates(unittest.TestCase):
    def test_build_player_handle_candidates_filters_noise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dump = Path(tmp) / "sample.dmp"
            dump.write_bytes(
                b"2600_IcyBang abc 8815_DIOR card_Vox_Skin_Pirate_T1 GameMode_5v5_Ranked"
            )
            report = build_player_handle_candidates(str(dump))

        values = [row["candidate"] for row in report["candidates"]]
        self.assertIn("2600_IcyBang", values)
        self.assertIn("8815_DIOR", values)
        self.assertNotIn("card_Vox_Skin_Pirate_T1", values)

    def test_build_player_handle_candidates_can_require_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dump = Path(tmp) / "sample.dmp"
            dump.write_bytes(b"2600_IcyBang 8815_DIOR 8815_Sui")
            report = build_player_handle_candidates(str(dump), required_prefix="8815_")

        values = [row["candidate"] for row in report["candidates"]]
        self.assertEqual(values, ["8815_DIOR", "8815_Sui"])


if __name__ == "__main__":
    unittest.main()
