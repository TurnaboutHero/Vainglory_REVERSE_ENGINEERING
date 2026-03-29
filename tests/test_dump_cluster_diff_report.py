import tempfile
import unittest
from pathlib import Path

from vg.tools.dump_cluster_diff_report import build_dump_cluster_diff_report


class TestDumpClusterDiffReport(unittest.TestCase):
    def test_build_dump_cluster_diff_report_ranks_runtime_windows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            before = Path(tmp) / "before.dmp"
            after = Path(tmp) / "after.dmp"
            before.write_bytes(b"cid18736 cid18739")
            after.write_bytes(b'{"handle":"Temporary Foo"} GameMode_5v5_Practice 8815_DIOR')
            report = build_dump_cluster_diff_report(str(before), str(after), window_size=4096, top_n=5)

        self.assertEqual(report["window_count"], 1)
        top = report["top_windows"][0]
        self.assertGreater(top["delta_class_counts"]["runtime"], 0)
        self.assertGreater(top["score"], 0)


if __name__ == "__main__":
    unittest.main()
