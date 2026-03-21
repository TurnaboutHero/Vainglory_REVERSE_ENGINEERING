import tempfile
import unittest
from pathlib import Path

from vg.decoder_v2.manifest import parse_replay_manifest


class TestDecoderV2Manifest(unittest.TestCase):
    def test_parse_replay_manifest_extracts_uuid_pair(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "replayManifest.txt"
            path.write_text(
                "8fc12404-6151-11eb-afe2-061b3d1d141d-6037ffb3-f8cd-4722-9bcb-ec9a4a239b0b",
                encoding="utf-8",
            )
            record = parse_replay_manifest(str(path))

        self.assertEqual(record.match_uuid, "8fc12404-6151-11eb-afe2-061b3d1d141d")
        self.assertEqual(record.session_uuid, "6037ffb3-f8cd-4722-9bcb-ec9a4a239b0b")

    def test_parse_replay_manifest_handles_non_matching_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "replayManifest.txt"
            path.write_text("just-a-string", encoding="utf-8")
            record = parse_replay_manifest(str(path))

        self.assertIsNone(record.match_uuid)
        self.assertIsNone(record.session_uuid)


if __name__ == "__main__":
    unittest.main()
