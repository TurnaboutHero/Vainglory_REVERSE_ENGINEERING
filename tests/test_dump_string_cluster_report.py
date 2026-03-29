import tempfile
import unittest
from pathlib import Path

from vg.tools.dump_string_cluster_report import build_dump_string_cluster_report, classify_string_value


class TestDumpStringClusterReport(unittest.TestCase):
    def test_classify_string_value_detects_runtime_and_handle(self) -> None:
        self.assertEqual(classify_string_value('{"handle":"Temporary Foo"}'), "runtime")
        self.assertEqual(classify_string_value("8815_DIOR"), "handle")
        self.assertEqual(classify_string_value("cid18736"), "glyph")
        self.assertEqual(classify_string_value("south-korea"), "locale")

    def test_build_dump_string_cluster_report_groups_strings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dump = Path(tmp) / "sample.dmp"
            dump.write_bytes(
                b'{"handle":"Temporary Foo"}\x00\x008815_DIOR\x00\x00GameMode_5v5_Practice\x00\x00'
                + (b"A" * 4096)
                + (b"\x00" * 64)
                + b"cid18736....cid18739....cid18740...."
            )
            report = build_dump_string_cluster_report(str(dump), window_size=4096, min_strings=1, top_n=10)

        self.assertGreaterEqual(report["cluster_count"], 2)
        self.assertEqual(report["top_clusters"][0]["class_counts"]["runtime"], 2)
        self.assertEqual(report["top_clusters"][0]["class_counts"]["handle"], 1)


if __name__ == "__main__":
    unittest.main()
