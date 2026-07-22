"""状態の永続化のテスト（AGENTS.md §6.5）。

同じメンションに二度返信しないこと ── これが崩れると相談者に迷惑がかかる。
"""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from bot import state as state_mod
from bot.misskey import strip_mentions


class StateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "state.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_replied_ids_survive_restart(self):
        state = state_mod.State(self.path)
        state.mark_replied("notif-1")
        state.last_notification_id = "notif-1"
        state.save()

        restarted = state_mod.State(self.path)
        self.assertTrue(restarted.already_replied("notif-1"))
        self.assertFalse(restarted.already_replied("notif-2"))
        self.assertEqual("notif-1", restarted.last_notification_id)

    def test_replied_ids_are_capped(self):
        state = state_mod.State(self.path)
        for index in range(state_mod.MAX_REPLIED_IDS + 50):
            state.mark_replied(f"notif-{index}")
        self.assertEqual(state_mod.MAX_REPLIED_IDS, len(state._data["replied_ids"]))
        self.assertTrue(state.already_replied(f"notif-{state_mod.MAX_REPLIED_IDS + 49}"))

    def test_cooldown(self):
        state = state_mod.State(self.path)
        self.assertFalse(state.cooling_down("user-1", 60))
        state.touch_user("user-1", 60)
        self.assertTrue(state.cooling_down("user-1", 60))
        self.assertFalse(state.cooling_down("user-2", 60))
        self.assertFalse(state.cooling_down("user-1", 0))   # クールダウン無効時

    def test_daily_guard(self):
        state = state_mod.State(self.path)
        self.assertFalse(state.daily_already_posted("2026-07-22"))
        state.mark_daily_posted("2026-07-22")
        self.assertTrue(state.daily_already_posted("2026-07-22"))
        self.assertFalse(state.daily_already_posted("2026-07-23"))

    def test_corrupt_file_does_not_crash(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("{ broken json", encoding="utf-8")
        state = state_mod.State(self.path)
        self.assertIsNone(state.last_notification_id)


class SlugTests(unittest.TestCase):
    def test_japanese_is_kept(self):
        self.assertEqual("恋愛のこと", state_mod.slugify("恋愛のこと"))

    def test_path_separators_are_removed(self):
        slug = state_mod.slugify("../../etc/passwd")
        self.assertNotIn("/", slug)
        self.assertNotIn("..", slug)

    def test_empty_falls_back(self):
        self.assertEqual("reading", state_mod.slugify("   "))


class StripMentionsTests(unittest.TestCase):
    def test_removes_bot_mention(self):
        self.assertEqual("占ってほしい", strip_mentions("@mai@example.tld 占ってほしい"))

    def test_removes_local_mention(self):
        self.assertEqual("今日の運勢を見て", strip_mentions("@mai 今日の運勢を見て"))

    def test_handles_none(self):
        self.assertEqual("", strip_mentions(None))


if __name__ == "__main__":
    unittest.main()
