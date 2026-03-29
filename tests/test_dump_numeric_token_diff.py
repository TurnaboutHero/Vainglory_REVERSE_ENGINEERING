import tempfile
import unittest
from pathlib import Path

from vg.tools.dump_numeric_token_diff import build_dump_numeric_token_diff, classify_numeric_window


class TestDumpNumericTokenDiff(unittest.TestCase):
    def test_classify_numeric_window_detects_known_noise_classes(self) -> None:
        self.assertEqual(classify_numeric_window(["HTTP/1.1 200 OK", "Content-Length: 937"]), "http_network")
        self.assertEqual(classify_numeric_window(["uvec4 subgroupBallot(bool v)", "mat4 spvInverse"]), "shader_codegen")
        self.assertEqual(classify_numeric_window(["Src0.Type", "grf<8;1>", "Src1.RegFile"]), "isa_table")
        self.assertEqual(classify_numeric_window(['"skinKey":"Adagio_DefaultSkin"', '"imageName":"foo.jpg"']), "config_blob")
        self.assertEqual(classify_numeric_window(["api-ms-win-core-file-l1-2-2", "CRYPTBASE.DLL"]), "import_table")

    def test_build_dump_numeric_token_diff_reports_window_growth(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            before = Path(tmp) / "before.dmp"
            after = Path(tmp) / "after.dmp"
            before.write_bytes(b"alpha 1 beta")
            after.write_bytes(b"alpha 1 beta 12 3/4 99")
            report = build_dump_numeric_token_diff(str(before), str(after), window_size=4096, top_n=5)

        self.assertEqual(report["window_count"], 1)
        top = report["top_windows"][0]
        self.assertEqual(top["before_count"], 1)
        self.assertEqual(top["after_count"], 4)
        self.assertIn("3/4", top["after_samples"])


if __name__ == "__main__":
    unittest.main()
