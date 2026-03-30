import json
import tempfile
import unittest
from pathlib import Path

from vg.tools.result_screen_kda_correction_inventory import build_result_screen_kda_correction_inventory


class TestResultScreenKdaCorrectionInventory(unittest.TestCase):
    def test_inventory_finds_nested_merge_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            nested = Path(tmp) / "a" / "bundle"
            nested.mkdir(parents=True)
            (nested / "result_screen_kda_correction_merge.json").write_text(
                json.dumps(
                    {
                        "replay_name": "sample",
                        "replay_file": "sample.0.vgr",
                        "corrected_rows": 10,
                        "unresolved_rows": 0,
                        "players": [],
                    }
                ),
                encoding="utf-8",
            )

            report = build_result_screen_kda_correction_inventory(tmp)

        self.assertEqual(report["correction_file_count"], 1)
        self.assertEqual(report["entries"][0]["replay_name"], "sample")
        self.assertEqual(report["preferred_correction_count"], 1)

    def test_inventory_prefers_merge_payload_for_same_replay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "target_replay_corrected_kda_rows.json").write_text(
                json.dumps(
                    {
                        "replay_name": "sample",
                        "replay_file": "sample.0.vgr",
                        "corrected_rows": 8,
                        "unresolved_rows": 2,
                        "players": [],
                    }
                ),
                encoding="utf-8",
            )
            nested = base / "probe" / "bundle"
            nested.mkdir(parents=True)
            (nested / "result_screen_kda_correction_merge.json").write_text(
                json.dumps(
                    {
                        "replay_name": "sample",
                        "replay_file": "sample.0.vgr",
                        "corrected_rows": 10,
                        "unresolved_rows": 0,
                        "players": [],
                    }
                ),
                encoding="utf-8",
            )

            report = build_result_screen_kda_correction_inventory(tmp)

        self.assertEqual(report["preferred_correction_count"], 1)
        self.assertEqual(report["preferred_entries"][0]["name"], "result_screen_kda_correction_merge.json")

    def test_inventory_prefers_autobundle_auto_over_plain_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            plain = base / "probe" / "bundle"
            plain.mkdir(parents=True)
            (plain / "result_screen_kda_correction_merge.json").write_text(
                json.dumps(
                    {
                        "replay_name": "sample",
                        "replay_file": "sample.0.vgr",
                        "corrected_rows": 10,
                        "unresolved_rows": 0,
                        "players": [],
                    }
                ),
                encoding="utf-8",
            )
            auto = base / "probe" / "autobundle_auto"
            auto.mkdir(parents=True)
            (auto / "result_screen_kda_correction_merge.json").write_text(
                json.dumps(
                    {
                        "replay_name": "sample",
                        "replay_file": "sample.0.vgr",
                        "corrected_rows": 10,
                        "unresolved_rows": 0,
                        "players": [],
                    }
                ),
                encoding="utf-8",
            )

            report = build_result_screen_kda_correction_inventory(tmp)

        self.assertEqual(report["preferred_entries"][0]["path"], str((auto / "result_screen_kda_correction_merge.json").resolve()))


if __name__ == "__main__":
    unittest.main()
