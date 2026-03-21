import unittest

from vg.decoder_v2.player_blocks import parse_player_blocks


class TestDecoderV2PlayerBlocks(unittest.TestCase):
    def test_parse_player_blocks_extracts_known_offsets(self) -> None:
        block = bytearray(0xE2)
        block[0:3] = b"\xDA\x03\xEE"
        block[3:3 + len("PlayerOne")] = b"PlayerOne"
        block[0xA5:0xA7] = (57093).to_bytes(2, "little")
        block[0xA9:0xAB] = (0xB801).to_bytes(2, "little")
        block[0xAB:0xAF] = bytes.fromhex("11223344")
        block[0xD5] = 1

        records = parse_player_blocks(bytes(block))

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.name, "PlayerOne")
        self.assertEqual(record.entity_id_le, 57093)
        self.assertEqual(record.hero_id_le, 0xB801)
        self.assertEqual(record.hero_hash_hex, "11223344")
        self.assertEqual(record.team_byte, 1)


if __name__ == "__main__":
    unittest.main()
