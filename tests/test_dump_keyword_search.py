import tempfile
import unittest
from pathlib import Path

from vg.tools.dump_keyword_search import search_dump_keywords


class TestDumpKeywordSearch(unittest.TestCase):
    def test_search_dump_keywords_finds_ascii_and_utf16(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dump_path = Path(tmp) / "sample.dmp"
            payload = b"Temporary ashasha" + "플레이".encode("utf-16-le")
            dump_path.write_bytes(payload)
            report = search_dump_keywords(str(dump_path), ["Temporary ashasha", "플레이"])

        keyword_rows = {row["keyword"]: row["matches"] for row in report["keywords"]}
        self.assertGreater(keyword_rows["Temporary ashasha"]["ascii"]["count"], 0)
        self.assertGreater(keyword_rows["플레이"]["utf16le"]["count"], 0)


if __name__ == "__main__":
    unittest.main()
