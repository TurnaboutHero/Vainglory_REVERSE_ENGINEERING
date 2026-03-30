import unittest

from vg.core.kda_detector import CreditRecord, DeathEvent, KDADetector, KillEvent


class TestKdaDetectorTailFiltering(unittest.TestCase):
    def test_default_buffers_keep_real_late_kills_and_short_tail_deaths(self) -> None:
        detector = KDADetector(valid_entity_ids={1, 2, 3})
        detector._kill_events = [
            KillEvent(
                killer_eid=1,
                timestamp=101.0,
                frame_idx=10,
                credits=[
                    CreditRecord(eid=1, value=1.0),
                    CreditRecord(eid=2, value=50.0),
                    CreditRecord(eid=2, value=1.0),
                ],
            ),
            KillEvent(
                killer_eid=1,
                timestamp=104.0,
                frame_idx=11,
                credits=[
                    CreditRecord(eid=1, value=1.0),
                    CreditRecord(eid=2, value=50.0),
                    CreditRecord(eid=2, value=1.0),
                ],
            ),
            KillEvent(
                killer_eid=1,
                timestamp=121.0,
                frame_idx=12,
                credits=[
                    CreditRecord(eid=1, value=1.0),
                    CreditRecord(eid=2, value=50.0),
                    CreditRecord(eid=2, value=1.0),
                ],
            ),
        ]
        detector._death_events = [
            DeathEvent(victim_eid=3, timestamp=102.0, frame_idx=10),
            DeathEvent(victim_eid=3, timestamp=111.0, frame_idx=11),
        ]

        results = detector.get_results(
            game_duration=100.0,
            team_map={1: "left", 2: "left", 3: "right"},
        )

        self.assertEqual(results[1].kills, 2)
        self.assertEqual(results[2].assists, 2)
        self.assertEqual(results[3].deaths, 1)

    def test_default_death_buffer_drops_later_tail_without_rescue(self) -> None:
        detector = KDADetector(valid_entity_ids={1})
        detector._kill_events = []
        detector._death_events = [
            DeathEvent(victim_eid=1, timestamp=104.5, frame_idx=10),
        ]

        results = detector.get_results(game_duration=100.0)

        self.assertEqual(results[1].deaths, 0)

    def test_zero_death_buffer_drops_short_tail_death(self) -> None:
        detector = KDADetector(valid_entity_ids={1})
        detector._death_events = [
            DeathEvent(victim_eid=1, timestamp=100.5, frame_idx=10),
        ]

        results = detector.get_results(game_duration=100.0, death_buffer=0.0)

        self.assertEqual(results[1].deaths, 0)

    def test_late_death_rescue_keeps_death_when_near_opposing_late_kill(self) -> None:
        detector = KDADetector(valid_entity_ids={1, 2})
        detector._kill_events = [
            KillEvent(killer_eid=2, timestamp=116.0, frame_idx=20, credits=[]),
        ]
        detector._death_events = [
            DeathEvent(victim_eid=1, timestamp=116.5, frame_idx=20),
        ]

        results = detector.get_results(
            game_duration=100.0,
            team_map={1: "left", 2: "right"},
        )

        self.assertEqual(results[1].deaths, 1)



if __name__ == "__main__":
    unittest.main()
