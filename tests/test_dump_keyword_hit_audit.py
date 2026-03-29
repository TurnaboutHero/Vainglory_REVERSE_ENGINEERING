import unittest

from vg.tools.dump_keyword_hit_audit import classify_keyword_context


class TestDumpKeywordHitAudit(unittest.TestCase):
    def test_classify_glyph_table_context(self) -> None:
        context = "cid18736 cid18739 cid18740 uni61C8 uni61CB uni61CD"
        self.assertEqual(classify_keyword_context(context), "glyph_table")

    def test_classify_locale_context(self) -> None:
        context = "english french japanese koreana south-korea schinese"
        self.assertEqual(classify_keyword_context(context), "locale_table")

    def test_classify_runtime_context(self) -> None:
        context = '{"handle":"Temporary Jaymoney15","entitlement_ranked":true,"GameMode_5v5_Practice"}'
        self.assertEqual(classify_keyword_context(context), "runtime_state")

    def test_classify_config_context(self) -> None:
        context = '\\"imageName\\": \\"foo.jpg\\", \\"skinKey\\": \\"bar\\", experiment_friend_auto_favorite_1'
        self.assertEqual(classify_keyword_context(context), "config_or_proto")

    def test_classify_asset_noise_context(self) -> None:
        context = "EXE.ORTSA UANORTSA EDIORDNA ROTAMINA YLAMONA DREHTONA"
        self.assertEqual(classify_keyword_context(context), "asset_or_table_noise")


if __name__ == "__main__":
    unittest.main()
