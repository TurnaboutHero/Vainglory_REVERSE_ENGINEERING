import unittest

from vg.decoder_v2.registry import DECODER_FIELD_STATUSES, EVENT_HEADER_CLAIMS, OFFSET_CLAIMS


class TestDecoderV2Registry(unittest.TestCase):
    def test_registry_contains_core_player_block_claims(self) -> None:
        ids = {claim.claim_id for claim in OFFSET_CLAIMS}
        self.assertIn("player_block.entity_id", ids)
        self.assertIn("player_block.hero_id", ids)
        self.assertIn("player_block.team_byte", ids)

    def test_registry_contains_core_event_claims(self) -> None:
        ids = {claim.claim_id for claim in EVENT_HEADER_CLAIMS}
        self.assertIn("event.kill", ids)
        self.assertIn("event.death", ids)
        self.assertIn("event.credit", ids)

    def test_decoder_field_status_tracks_duration_as_approximate(self) -> None:
        statuses = {item.field_name: item.status.value for item in DECODER_FIELD_STATUSES}
        self.assertEqual(statuses["duration_seconds"], "partial")


if __name__ == "__main__":
    unittest.main()
