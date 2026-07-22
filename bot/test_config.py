"""設定読み込みのテスト。

`.env` の置き場所でつまずいたことがあるので、探索順は必ず検査する。
"""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from bot import config as config_mod


class FindEnvFileTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "bot").mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_finds_env_at_the_repository_root(self):
        (self.root / ".env").write_text("X=1", encoding="utf-8")
        self.assertEqual(self.root / ".env", config_mod.find_env_file(self.root))

    def test_finds_env_next_to_the_template(self):
        """bot/.env.example の隣に置くのが自然なので、bot/.env も拾う。"""
        (self.root / "bot" / ".env").write_text("X=1", encoding="utf-8")
        self.assertEqual(self.root / "bot" / ".env", config_mod.find_env_file(self.root))

    def test_repository_root_wins(self):
        (self.root / ".env").write_text("X=1", encoding="utf-8")
        (self.root / "bot" / ".env").write_text("X=2", encoding="utf-8")
        self.assertEqual(self.root / ".env", config_mod.find_env_file(self.root))

    def test_returns_none_when_absent(self):
        self.assertIsNone(config_mod.find_env_file(self.root))

    def test_candidates_cover_both_locations(self):
        self.assertEqual((".env", "bot/.env"), config_mod.ENV_CANDIDATES)


class ValidationTests(unittest.TestCase):
    def test_visibility_and_effort_choices(self):
        self.assertIn("home", config_mod.VISIBILITIES)
        self.assertIn("medium", config_mod.EFFORTS)
        self.assertIn("xhigh", config_mod.EFFORTS)


if __name__ == "__main__":
    unittest.main()
