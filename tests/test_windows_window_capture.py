import unittest

from vg.tools.windows_window_capture import build_window_capture_metadata, normalize_window_rect


class TestWindowsWindowCapture(unittest.TestCase):
    def test_normalize_window_rect_accepts_valid_rect(self) -> None:
        self.assertEqual(normalize_window_rect(10, 20, 110, 220), (10, 20, 110, 220))

    def test_normalize_window_rect_rejects_invalid_rect(self) -> None:
        with self.assertRaises(ValueError):
            normalize_window_rect(10, 20, 10, 30)

    def test_build_window_capture_metadata_embeds_dimensions(self) -> None:
        meta = build_window_capture_metadata("Vainglory.exe", "C:/tmp/result.png", (10, 20, 110, 220))
        self.assertEqual(meta["process_name"], "Vainglory.exe")
        self.assertEqual(meta["rect"]["width"], 100)
        self.assertEqual(meta["rect"]["height"], 200)


if __name__ == "__main__":
    unittest.main()
