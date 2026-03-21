import importlib
import unittest

import vg.core.vgr_parser as vgr_parser


class TestVGRParserImports(unittest.TestCase):
    def test_truth_loader_is_available_in_package_mode(self) -> None:
        reloaded = importlib.reload(vgr_parser)
        self.assertTrue(reloaded.TRUTH_AVAILABLE)
        self.assertTrue(callable(reloaded.load_truth_data))


if __name__ == "__main__":
    unittest.main()
