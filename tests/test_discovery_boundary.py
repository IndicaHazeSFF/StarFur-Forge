"""Regression checks for provider-free, corpus-free test collection."""
import importlib.util
import io
from pathlib import Path
import sys
import types
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


class TestDiscoveryBoundaryTests(unittest.TestCase):
    def test_manual_chunker_import_neither_reads_corpus_nor_prints_prose(self):
        for path in (PROJECT_ROOT / "tests" / "test_chunker.py", PROJECT_ROOT / "test_chunker.py"):
            with self.subTest(path=path.name):
                spec = importlib.util.spec_from_file_location("manual_chunker_import_fixture", path)
                module = importlib.util.module_from_spec(spec)
                with patch("pipeline.chunker.chunk_markdown", side_effect=AssertionError("corpus access forbidden")), patch(
                    "builtins.print", side_effect=AssertionError("import output forbidden")
                ):
                    spec.loader.exec_module(module)
                self.assertTrue(callable(module.main))

    def test_reset_fixture_cleanup_restores_database_setting_after_failure(self):
        from pipeline import db
        from tests.test_reset import ResetTests
        original = db.DB_PATH
        case = ResetTests("test_restore_lists_and_safety_backs_up_current")
        case.setUp()
        try:
            db.DB_PATH = Path("test-owned-unavailable-fixture.sqlite")
            raise RuntimeError("synthetic test failure")
        except RuntimeError:
            pass
        finally:
            case.doCleanups()
        self.assertEqual(original, db.DB_PATH)

    def test_explicit_top_level_discovery_uses_package_identity_not_root_script(self):
        sentinel = types.ModuleType("test_chunker")
        sentinel.__file__ = str(PROJECT_ROOT / "test_chunker.py")
        output = io.StringIO()
        with patch.dict(sys.modules, {"test_chunker": sentinel}), redirect_stdout(output):
            suite = unittest.TestLoader().discover(str(PROJECT_ROOT / "tests"),
                pattern="test_chunker.py", top_level_dir=str(PROJECT_ROOT))
            loaded_path = Path(sys.modules["tests.test_chunker"].__file__).resolve()
        self.assertEqual(0, suite.countTestCases())  # This file is manual, not a unit case.
        self.assertEqual("", output.getvalue())
        self.assertEqual(PROJECT_ROOT / "tests" / "test_chunker.py", loaded_path)


if __name__ == "__main__":
    unittest.main()
