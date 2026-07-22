"""正本ローダーのテスト。

ここで守りたいのは「Bot が正本を読んでいること」と「安定部にキャッシュを壊す可変値が
混ざっていないこと」の2点。
"""
from __future__ import annotations

import sys
import unittest

from bot import ssot
from bot.tarot import draw  # procedures/ を sys.path に載せる副作用も兼ねる

import shuffle  # noqa: E402  (bot.tarot の import 後でないと解決できない)


class BuildSystemPromptTests(unittest.TestCase):
    def setUp(self):
        ssot.build_system_prompt.cache_clear()

    def test_contains_every_source(self):
        prompt = ssot.build_system_prompt()
        for label, _relpath in ssot.SYSTEM_SOURCES:
            self.assertIn(label, prompt)

    def test_contains_character_and_principles(self):
        prompt = ssot.build_system_prompt()
        self.assertIn("錦野舞", prompt)          # 正本①が入っている
        self.assertIn("占いの原則", prompt)       # 正本②が入っている
        self.assertIn("ケルト十字", prompt)       # スプレッド資料が入っている

    def test_is_byte_stable(self):
        """安定部は呼ぶたび同じでなければプロンプトキャッシュが効かない。"""
        ssot.build_system_prompt.cache_clear()
        first = ssot.build_system_prompt()
        ssot.build_system_prompt.cache_clear()
        second = ssot.build_system_prompt()
        self.assertEqual(first, second)

    def test_is_verbatim_concatenation_of_sources(self):
        """正本の中身をそのまま載せているか。

        安定部に実行時の値（日時・ユーザー名・UUID）を差し込むとリクエストごとに
        プロンプトキャッシュが失効する。差し込みが無いことを、
        「各正本ファイルの本文が丸ごと含まれている」ことで確かめる。
        （資料の本文に日付の記載例が出てくることはあるので、日付文字列の有無では判定しない）
        """
        prompt = ssot.build_system_prompt()
        for _label, relpath in ssot.SYSTEM_SOURCES:
            with self.subTest(relpath=relpath):
                body = (ssot.PROJECT_ROOT / relpath).read_text(encoding="utf-8").strip()
                self.assertIn(body, prompt)


class TemplateTests(unittest.TestCase):
    def setUp(self):
        ssot.load_templates.cache_clear()

    def test_required_templates_exist(self):
        templates = ssot.load_templates()
        for template_id in ("safety-block", "expert-note", "roleplay-off",
                            "api-error", "unpublished-setting", "cw-reading"):
            with self.subTest(template_id=template_id):
                self.assertIn(template_id, templates)
                self.assertTrue(templates[template_id].strip())

    def test_placeholder_is_substituted(self):
        body = ssot.template("safety-block", support_url="https://example.test/")
        self.assertIn("https://example.test/", body)
        self.assertNotIn("{support_url}", body)

    def test_cw_is_short_enough_for_misskey(self):
        """Misskey の CW は100字まで。長いスプレッド名を入れても収まること。"""
        body = ssot.template("cw-reading", spread="ヘキサグラム")
        self.assertLessEqual(len(body), 100)
        self.assertIn("ヘキサグラム", body)

    def test_unknown_template_raises(self):
        with self.assertRaises(ssot.SsotError):
            ssot.template("no-such-template")


class DeckTests(unittest.TestCase):
    def test_every_card_has_keywords(self):
        index = ssot.deck_index()
        for card in shuffle.build_deck():
            with self.subTest(card=card):
                self.assertIn(card, index)
                upright, reversed_ = index[card]
                self.assertTrue(upright.strip())
                self.assertTrue(reversed_.strip())

    def test_index_holds_the_whole_deck(self):
        self.assertEqual(78, len(ssot.deck_index()))

    def test_entries_cover_the_drawn_cards(self):
        cards = draw("three")
        entries = ssot.deck_entries(cards)
        for card in cards:
            self.assertIn(card["card"], entries)
        self.assertEqual(3, entries.count("今回適用するのは"))


if __name__ == "__main__":
    sys.exit(unittest.main())
