import unittest
from vg.core.kda_detector import CreditRecord, KillEvent, KDADetector
from vg.decoder_v2.assist_rule_research import AssistRule, _count_assists_for_rule


class TestAssistRuleResearch(unittest.TestCase):
    def test_count_assists_for_rule_allows_gold_only_when_configured(self) -> None:
        detector = KDADetector({1, 2})
        detector._kill_events = [
            KillEvent(
                killer_eid=1,
                timestamp=10.0,
                credits=[CreditRecord(eid=2, value=7.5)],
            )
        ]
        assists = _count_assists_for_rule(
            detector,
            {1: "left", 2: "left"},
            [1, 2],
            game_duration=100,
            kill_buffer=3,
            rule=AssistRule("gold_only", False, 1, 5.0),
        )
        self.assertEqual(assists[2], 1)


if __name__ == "__main__":
    unittest.main()
