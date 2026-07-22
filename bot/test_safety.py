"""スクリーニングのテスト（AGENTS.md §6.2）。

大事なのは「取りこぼしより誤検知を選ぶ」ことと、
カード名や日常表現で過剰に反応しないこと。
"""
from __future__ import annotations

import unittest

from bot import safety


class BlockTests(unittest.TestCase):
    def test_self_harm_blocks_the_reading(self):
        for text in ("もう死にたい", "消えたい気持ちが止まらない", "自殺を考えてる",
                     "生きるのがつらいです"):
            with self.subTest(text=text):
                verdict = safety.screen(text)
                self.assertEqual("block", verdict.action)
                self.assertEqual("safety-block", verdict.template)

    def test_card_names_do_not_block(self):
        """「死神」「塔」はカード名。ここで止めてしまっては占いにならない。"""
        for text in ("死神のカードが出たときの意味を知りたい",
                     "塔のカードって怖いイメージがある",
                     "死ぬほど楽しみにしてる"):
            with self.subTest(text=text):
                self.assertEqual("read", safety.screen(text).action)


class RoleplayOffTests(unittest.TestCase):
    def test_explicit_stop_switches_mode(self):
        for text in ("ロールプレイをやめて", "なりきりをやめてください", "通常モードで答えて"):
            with self.subTest(text=text):
                verdict = safety.screen(text)
                self.assertEqual("roleplay_off", verdict.action)
                self.assertEqual("roleplay-off", verdict.template)

    def test_self_harm_takes_priority(self):
        """安全性の判定は他のどれよりも先に来る。"""
        verdict = safety.screen("ロールプレイをやめて。もう死にたい")
        self.assertEqual("block", verdict.action)


class SensitiveTests(unittest.TestCase):
    def test_serious_topics_are_flagged(self):
        for text in ("手術を受けるか迷っています", "離婚調停をどうするか",
                     "この投資をすべきか", "借金の返済が苦しい"):
            with self.subTest(text=text):
                verdict = safety.screen(text)
                self.assertEqual("read", verdict.action)
                self.assertTrue(verdict.sensitive)

    def test_ordinary_consultation_is_not_flagged(self):
        verdict = safety.screen("今日はどんな一日になりそう？")
        self.assertEqual("read", verdict.action)
        self.assertFalse(verdict.sensitive)

    def test_empty_text_is_readable(self):
        verdict = safety.screen("")
        self.assertEqual("read", verdict.action)
        self.assertFalse(verdict.sensitive)


if __name__ == "__main__":
    unittest.main()
