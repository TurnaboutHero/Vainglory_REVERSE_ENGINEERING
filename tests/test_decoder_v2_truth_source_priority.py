import unittest

from vg.decoder_v2.truth_source_priority import build_truth_source_priority_from_inventory


class TestTruthSourcePriority(unittest.TestCase):
    def test_build_truth_source_priority_from_inventory_prioritizes_manifest_only_when_no_images(self) -> None:
        inventory = {
            "base_path": "C:/replays",
            "truth_path": "truth.json",
            "total_replay_directories": 4,
            "covered_directories": 1,
            "missing_directories": 3,
            "coverage_pct": 25.0,
            "covered": [
                {
                    "directory": "C:/replays/set1/1",
                    "covered_by_truth": True,
                    "has_result_image": True,
                    "has_manifest": True,
                }
            ],
            "missing": [
                {
                    "directory": "C:/replays/set1/2",
                    "covered_by_truth": False,
                    "has_result_image": False,
                    "has_manifest": True,
                },
                {
                    "directory": "C:/replays/set2/1",
                    "covered_by_truth": False,
                    "has_result_image": False,
                    "has_manifest": True,
                },
                {
                    "directory": "C:/replays/set3/1",
                    "covered_by_truth": False,
                    "has_result_image": False,
                    "has_manifest": False,
                },
            ],
        }

        report = build_truth_source_priority_from_inventory(inventory)

        self.assertEqual(report["summary"]["immediately_labelable"], 0)
        self.assertEqual(report["summary"]["manifest_only"], 2)
        self.assertEqual(report["summary"]["raw_only"], 1)
        self.assertEqual(report["recommended_actions"][0]["action"], "capture_or_recover_result_images_for_manifest_only_dirs")
        self.assertEqual(report["recommended_actions"][1]["action"], "recover_bundle_metadata_for_raw_only_dirs")
        self.assertEqual(report["recommended_actions"][2]["action"], "do_not_scale_ocr_yet")


if __name__ == "__main__":
    unittest.main()
