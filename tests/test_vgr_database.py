import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vg.core.vgr_database import VGDatabase


def make_parsed_replay(replay_name: str) -> dict:
    return {
        "replay_name": replay_name,
        "parsed_at": "2026-03-21T12:00:00",
        "match_info": {
            "mode": "GameMode_HF_Ranked",
            "total_frames": 42,
            "duration_seconds": 123,
            "winner": "right",
        },
        "teams": {
            "left": [
                {
                    "name": "left_player",
                    "uuid": "left-uuid",
                    "team": "left",
                    "team_id": 1,
                    "hero_name": "Unknown",
                    "items": [],
                }
            ],
            "right": [
                {
                    "name": "right_player",
                    "uuid": "right-uuid",
                    "team": "right",
                    "team_id": 2,
                    "hero_name": "Unknown",
                    "items": [],
                }
            ],
        },
    }


class TestVGDatabase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.db = VGDatabase(str(self.db_path))
        self.db.connect()
        self.db.create_tables()
        self.addCleanup(self.db.close)

    def test_import_replay_uses_parser_fields_and_skips_duplicates(self) -> None:
        parsed = make_parsed_replay("sample-replay")

        with patch("vg.core.vgr_database.VGRParser") as parser_cls:
            parser_cls.return_value.parse.return_value = parsed

            self.assertTrue(self.db.import_replay("sample-replay.0.vgr"))
            self.assertFalse(self.db.import_replay("sample-replay.0.vgr"))

        cursor = self.db.conn.cursor()
        match_row = cursor.execute(
            "SELECT replay_name, duration, winning_team FROM matches"
        ).fetchone()
        self.assertEqual(match_row["replay_name"], "sample-replay")
        self.assertEqual(match_row["duration"], 123)
        self.assertEqual(match_row["winning_team"], 2)

        player_count = cursor.execute(
            "SELECT COUNT(*) FROM match_players"
        ).fetchone()[0]
        self.assertEqual(player_count, 2)

    def test_module_cli_init_runs(self) -> None:
        cli_db_path = Path(self.temp_dir.name) / "cli.db"
        repo_root = Path(__file__).resolve().parents[1]

        completed = subprocess.run(
            [sys.executable, "-m", "vg.core.vgr_database", "init", "--db", str(cli_db_path)],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        self.assertTrue(cli_db_path.exists())


if __name__ == "__main__":
    unittest.main()
