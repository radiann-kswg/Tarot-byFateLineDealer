"""抽選・スプレッド選択・陣形画像のテスト。"""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from PIL import Image

from bot import tarot

import shuffle  # noqa: E402  (bot.tarot が procedures/ を sys.path に載せる)


class ChooseSpreadTests(unittest.TestCase):
    def test_explicit_keywords_win(self):
        cases = {
            "ケルト十字でお願い": "celtic",
            "ヘキサグラムで見て": "hexagram",
            "3枚引きがいい": "three",
            "2枚でいいよ": "two",
            "1枚だけ引いて": "one",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                spread, reason = tarot.choose_spread(text)
                self.assertEqual(expected, spread)
                self.assertEqual("相談者の指定", reason)

    def test_explicit_keyword_beats_theme(self):
        """指定があれば、相談内容のテーマより指定を優先する。"""
        spread, reason = tarot.choose_spread("恋愛のことだけど、ケルト十字でお願い")
        self.assertEqual("celtic", spread)
        self.assertEqual("相談者の指定", reason)

    def test_theme_heuristics(self):
        cases = {
            "今日のひとことをください": "one",
            "転職するか迷ってる": "celtic",
            "好きな人の気持ちが知りたい": "hexagram",
            "AかBかどっちを選ぶべき": "two",
            "最近なんとなく気分が晴れない": "three",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                spread, reason = tarot.choose_spread(text)
                self.assertEqual(expected, spread)
                self.assertTrue(reason.startswith("舞の判断"))


class DrawTests(unittest.TestCase):
    def test_counts_match_the_spread(self):
        for spread, count in shuffle.SPREAD_COUNTS.items():
            with self.subTest(spread=spread):
                cards = tarot.draw(spread)
                self.assertEqual(count, len(cards))
                self.assertEqual(list(range(1, count + 1)),
                                 [c["position"] for c in cards])

    def test_no_duplicate_cards(self):
        cards = tarot.draw("celtic")
        self.assertEqual(10, len({c["card"] for c in cards}))

    def test_images_exist(self):
        for card in tarot.draw("celtic"):
            self.assertTrue((tarot.PROJECT_ROOT / card["image"]).is_file(), card["card"])

    def test_unknown_spread_raises(self):
        with self.assertRaises(tarot.TarotError):
            tarot.draw("nonexistent")


class RenderTests(unittest.TestCase):
    def setUp(self):
        self._original_dir = tarot.IMAGE_DIR
        self._tmp = tempfile.TemporaryDirectory()
        tarot.IMAGE_DIR = Path(self._tmp.name)

    def tearDown(self):
        tarot.IMAGE_DIR = self._original_dir
        self._tmp.cleanup()

    def test_every_spread_renders(self):
        """Bot は枚数によらず合成画像を通す（AGENTS.md §6.1）。"""
        for spread in shuffle.SPREAD_COUNTS:
            with self.subTest(spread=spread):
                cards = tarot.draw(spread)
                path = tarot.render(cards, spread, "動作確認", f"test-{spread}")
                self.assertTrue(path.is_file())
                with Image.open(path) as image:
                    self.assertEqual("PNG", image.format)

    def test_long_theme_is_trimmed_in_title(self):
        title = tarot._title("one", "あ" * 100)
        self.assertLessEqual(len(title), tarot.MAX_TITLE_THEME + 20)
        self.assertIn("…", title)


class LabelTests(unittest.TestCase):
    def test_every_spread_has_a_label(self):
        self.assertEqual(set(shuffle.SPREAD_COUNTS), set(tarot.SPREAD_LABELS))


if __name__ == "__main__":
    unittest.main()
