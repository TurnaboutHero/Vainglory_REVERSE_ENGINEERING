import unittest

from vg.core.kda_detector import KillEvent
from vg.decoder_v2.kda_phantom_kill_rule_research import _should_drop_phantom_kill


class TestKdaPhantomKillRuleResearch(unittest.TestCase):
    def test_should_drop_only_late_victim_none_kills(self) -> None:
        late_none = KillEvent(killer_eid=1, timestamp=112.5)
        self.assertTrue(_should_drop_phantom_kill(late_none, duration=100, threshold=10, victim_eid=None))

        self.assertFalse(_should_drop_phantom_kill(late_none, duration=100, threshold=20, victim_eid=None))
        self.assertFalse(_should_drop_phantom_kill(late_none, duration=100, threshold=10, victim_eid=2))


if __name__ == "__main__":
    unittest.main()
