"""メンション応答の分岐のテスト。

Claude API と Misskey API は差し替えて、外部通信なしで通す。
確かめたいのは「どの相談に、どう応じるか」の判断の部分。
"""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from bot import main as main_mod
from bot import reading as reading_mod
from bot import state as state_mod, tarot
from bot.config import Config
from bot.reading import Reading, ReadingError


def make_config(state_path: Path, cooldown: int = 60) -> Config:
    return Config(
        misskey_host="https://example.test",
        misskey_token="token",
        misskey_visibility="home",
        anthropic_api_key="key",
        anthropic_model="claude-opus-4-8",
        anthropic_effort="medium",
        anthropic_max_tokens=8000,
        poll_interval=30,
        user_cooldown=cooldown,
        max_body_chars=1200,
        support_url="https://example.test/support",
        save_readings=False,
        state_path=state_path,
        request_timeout=30,
    )


def notification(text: str, notification_id: str = "notif-1", user_id: str = "user-1") -> dict:
    return {
        "id": notification_id,
        "type": "mention",
        "user": {"id": user_id, "username": "someone"},
        "note": {"id": f"note-{notification_id}", "text": text},
    }


class FakeMisskey:
    """投稿しないダミー。live=True の経路も外部通信なしで確かめられる。"""

    def __init__(self):
        self.uploaded: list[Path] = []
        self.notes: list[dict] = []

    def upload(self, path: Path, comment: str | None = None) -> str:
        self.uploaded.append(path)
        return f"file-{len(self.uploaded)}"

    def create_note(self, text, reply_id=None, file_ids=None, cw=None) -> dict:
        self.notes.append({"text": text, "replyId": reply_id, "fileIds": file_ids})
        return {"id": f"note-created-{len(self.notes)}"}


class HandleNotificationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.config = make_config(root / "state.json")
        self.state = state_mod.State(self.config.state_path)
        self.client = FakeMisskey()

        # 陣形画像は本物を生成するが、一時ディレクトリに書く
        self._original_image_dir = tarot.IMAGE_DIR
        tarot.IMAGE_DIR = root / "images"

        # Claude API は呼ばない
        self._original_generate = reading_mod.generate
        self.generate_calls: list[dict] = []

        def fake_generate(config, theme, spread, reason, cards, sensitive):
            self.generate_calls.append({
                "theme": theme, "spread": spread, "reason": reason,
                "cards": cards, "sensitive": sensitive,
            })
            return Reading(text=f"（{spread} の読み解き）", input_tokens=100, output_tokens=50,
                           cache_read_tokens=0, cache_write_tokens=100)

        reading_mod.generate = fake_generate

    def tearDown(self):
        tarot.IMAGE_DIR = self._original_image_dir
        reading_mod.generate = self._original_generate
        self._tmp.cleanup()

    def handle(self, notif, live=True):
        return main_mod.handle_notification(self.config, self.client, self.state, notif, live)

    def test_normal_consultation_posts_a_reading_with_one_image(self):
        self.assertTrue(self.handle(notification("@mai 恋愛のことで悩んでいます")))
        self.assertEqual(1, len(self.client.notes))
        note = self.client.notes[0]
        self.assertEqual("note-notif-1", note["replyId"])
        # 添付は合成画像1枚だけ（AGENTS.md §6.1）
        self.assertEqual(1, len(note["fileIds"]))
        self.assertEqual(1, len(self.client.uploaded))
        self.assertTrue(self.client.uploaded[0].is_file())
        # メンション記法は相談文から外れている
        self.assertNotIn("@mai", self.generate_calls[0]["theme"])

    def test_self_harm_is_answered_without_a_reading(self):
        self.assertTrue(self.handle(notification("死にたい")))
        self.assertEqual([], self.generate_calls, "占ってはいけない相談で読み解きが走っている")
        note = self.client.notes[0]
        self.assertIsNone(note["fileIds"], "占わない分岐で画像を添付している")
        self.assertIn(self.config.support_url, note["text"])

    def test_roleplay_off_switches_mode(self):
        self.assertTrue(self.handle(notification("ロールプレイをやめてください")))
        self.assertEqual([], self.generate_calls)
        self.assertIn("通常モード", self.client.notes[0]["text"])

    def test_sensitive_topic_is_flagged_to_the_model(self):
        self.handle(notification("手術を受けるか迷っています"))
        self.assertTrue(self.generate_calls[0]["sensitive"])

    def test_already_replied_is_skipped(self):
        self.state.mark_replied("notif-1")
        self.assertFalse(self.handle(notification("占って")))
        self.assertEqual([], self.client.notes)

    def test_cooldown_is_respected(self):
        self.assertTrue(self.handle(notification("占って", "notif-1")))
        self.assertFalse(self.handle(notification("もう一回", "notif-2")))
        self.assertEqual(1, len(self.client.notes))

    def test_other_user_is_not_blocked_by_the_cooldown(self):
        self.handle(notification("占って", "notif-1", user_id="user-1"))
        self.assertTrue(self.handle(notification("私も占って", "notif-2", user_id="user-2")))
        self.assertEqual(2, len(self.client.notes))

    def test_dry_run_does_not_post_or_record(self):
        self.assertTrue(self.handle(notification("占って"), live=False))
        self.assertEqual([], self.client.notes)
        self.assertEqual([], self.client.uploaded)
        self.assertFalse(self.state.already_replied("notif-1"))

    def test_empty_text_still_gets_a_reading(self):
        self.handle(notification("@mai"))
        self.assertEqual(main_mod.EMPTY_THEME, self.generate_calls[0]["theme"])

    def test_note_without_id_is_skipped(self):
        notif = notification("占って")
        notif["note"] = {}
        self.assertFalse(self.handle(notif))
        self.assertEqual([], self.client.notes)


class RunOnceTests(unittest.TestCase):
    """初回起動のバックログ抑止（過去のメンション全部に返信しないこと）。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.config = make_config(Path(self._tmp.name) / "state.json")
        self.state = state_mod.State(self.config.state_path)

    def tearDown(self):
        self._tmp.cleanup()

    def test_first_run_skips_the_backlog(self):
        class Client(FakeMisskey):
            def notifications(self, since_id, limit=20, mark_as_read=True):
                return [notification("占って", f"notif-{i}") for i in range(1, 4)]

        client = Client()
        handled = main_mod.run_once(self.config, client, self.state, live=True,
                                    limit=10, catch_up=False)
        self.assertEqual(0, handled)
        self.assertEqual([], client.notes)
        # 次回からは sinceId で絞れるよう、最新IDだけ覚えておく
        self.assertEqual("notif-3", self.state.last_notification_id)


class ClampTests(unittest.TestCase):
    def test_short_text_is_untouched(self):
        self.assertEqual("みじかい本文", main_mod.clamp("みじかい本文", 100))

    def test_long_text_is_cut_at_a_sentence_boundary(self):
        text = "一文目です。" * 40
        clamped = main_mod.clamp(text, 100)
        self.assertLessEqual(len(clamped), 100)
        self.assertTrue(clamped.endswith("。"))

    def test_text_without_a_boundary_gets_an_ellipsis(self):
        clamped = main_mod.clamp("あ" * 300, 100)
        self.assertLessEqual(len(clamped), 101)
        self.assertTrue(clamped.endswith("…"))


class ReadingErrorTests(unittest.TestCase):
    def test_retryable_flag(self):
        self.assertTrue(ReadingError("一時的", retryable=True).retryable)
        self.assertFalse(ReadingError("恒久的").retryable)


if __name__ == "__main__":
    unittest.main()
