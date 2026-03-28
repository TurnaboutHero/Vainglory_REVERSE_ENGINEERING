import unittest

from vg.tools.windows_minidump import build_dump_metadata, dump_mode_flag


class TestWindowsMinidump(unittest.TestCase):
    def test_dump_mode_flag_supports_known_modes(self) -> None:
        self.assertEqual(dump_mode_flag("normal"), 0)
        self.assertNotEqual(dump_mode_flag("lean"), 0)
        self.assertNotEqual(dump_mode_flag("full"), 0)

    def test_build_dump_metadata_embeds_mode_and_path(self) -> None:
        meta = build_dump_metadata(123, "Vainglory.exe", "C:/tmp/test.dmp", "lean")
        self.assertEqual(meta["pid"], 123)
        self.assertEqual(meta["process_name"], "Vainglory.exe")
        self.assertTrue(str(meta["output_path"]).endswith("test.dmp"))
        self.assertEqual(meta["mode"], "lean")


if __name__ == "__main__":
    unittest.main()
