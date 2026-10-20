"""Owned SQLite transactions, without live data or garbage-collection reliance."""
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from pipeline import db


class DatabaseConnectionLifecycleTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        setting = patch.object(db, "DB_PATH", Path(directory.name) / "fixture.sqlite")
        setting.start()
        self.addCleanup(setting.stop)

    def assert_closed(self, connection):
        with self.assertRaises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")

    def test_transaction_commits_then_closes_retained_handle(self):
        with db.transaction() as connection:
            connection.execute("CREATE TABLE lifecycle_probe (value TEXT)")
            connection.execute("INSERT INTO lifecycle_probe VALUES ('committed')")
        self.assert_closed(connection)
        with db.transaction() as reader:
            self.assertEqual("committed", reader.execute("SELECT value FROM lifecycle_probe").fetchone()[0])
        self.assert_closed(reader)

    def test_transaction_rolls_back_then_closes_on_body_failure(self):
        with db.transaction() as setup:
            setup.execute("CREATE TABLE lifecycle_probe (value TEXT)")
        with self.assertRaisesRegex(RuntimeError, "synthetic"):
            with db.transaction() as connection:
                connection.execute("INSERT INTO lifecycle_probe VALUES ('discarded')")
                raise RuntimeError("synthetic body failure")
        self.assert_closed(connection)
        with db.transaction() as reader:
            self.assertEqual(0, reader.execute("SELECT COUNT(*) FROM lifecycle_probe").fetchone()[0])

    def test_enter_or_commit_failure_still_closes(self):
        for phase in ("__enter__", "__exit__"):
            with self.subTest(phase=phase):
                connection = MagicMock(spec=sqlite3.Connection)
                getattr(connection, phase).side_effect = sqlite3.OperationalError("synthetic transaction failure")
                with patch.object(db, "connect", return_value=connection):
                    with self.assertRaises(sqlite3.OperationalError):
                        with db.transaction():
                            pass
                connection.close.assert_called_once_with()

    def test_initialization_failure_closes_before_returning_any_handle(self):
        connection = sqlite3.connect(":memory:")
        self.addCleanup(connection.close)
        with patch.object(db.sqlite3, "connect", return_value=connection), patch.object(
            db, "ensure_memory_domains_schema", side_effect=RuntimeError("synthetic schema failure")
        ):
            with self.assertRaisesRegex(RuntimeError, "synthetic"):
                db.connect()
        self.assert_closed(connection)

    def test_owned_crud_closes_all_handles_but_rows_remain_usable(self):
        opened = []
        raw_connect = db.connect

        def track():
            connection = raw_connect()
            opened.append(connection)
            self.addCleanup(connection.close)
            return connection

        with patch.object(db, "connect", side_effect=track):
            memory_id = db.create_assistant_memory("Fixture", "preference", "Synthetic preference")
            record = db.get_assistant_memory(memory_id)
            records = db.list_assistant_memories()
        self.assertEqual("Synthetic preference", record["summary"])
        self.assertEqual(1, len(records))
        self.assertEqual(3, len(opened))
        for connection in opened:
            self.assert_closed(connection)

    def test_raw_connect_remains_caller_owned_for_compatibility(self):
        connection = db.connect()
        try:
            with connection:
                connection.execute("SELECT 1")
            self.assertEqual(1, connection.execute("SELECT 1").fetchone()[0])
        finally:
            connection.close()
        self.assert_closed(connection)
