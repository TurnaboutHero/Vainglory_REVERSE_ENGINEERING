import unittest
from unittest.mock import patch

from vg.decoder_v2.action02_subfamily_summary import build_action02_subfamily_summary


class TestAction02SubfamilySummary(unittest.TestCase):
    def test_build_action02_subfamily_summary_labels_shared_vs_solo(self) -> None:
        sharing = {
            "rows": [
                {"value": 20.0, "match_count": 10, "event_count": 1000, "shared_cluster_rate": 0.05},
                {"value": 17.4, "match_count": 5, "event_count": 500, "shared_cluster_rate": 0.0},
            ]
        }
        context = {
            "rows": [
                {"value": 20.0, "top_same_frame_patterns": [{"pattern": "0x06@3.0"}, {"pattern": "0x08@0.6"}, {"pattern": "0x03@1.0"}]},
                {"value": 17.4, "top_same_frame_patterns": [{"pattern": "0x06@3.0"}, {"pattern": "0x08@0.6"}, {"pattern": "0x03@1.0"}]},
            ]
        }

        with patch(
            "vg.decoder_v2.action02_subfamily_summary.build_action02_sharing_profile",
            return_value=sharing,
        ), patch(
            "vg.decoder_v2.action02_subfamily_summary.build_action02_value_context_profile",
            return_value=context,
        ):
            report = build_action02_subfamily_summary("truth.json")

        labels = {row["value"]: row["subfamily_label"] for row in report["rows"]}
        self.assertEqual(labels[20.0], "shared_reward_candidate")
        self.assertEqual(labels[17.4], "solo_reward_candidate")


if __name__ == "__main__":
    unittest.main()
