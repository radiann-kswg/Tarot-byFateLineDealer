import tempfile
import unittest
from pathlib import Path

from PIL import Image

import render_spread
import shuffle


class RenderSpreadTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parent.parent

    def cards_for(self, spread):
        count = shuffle.SPREAD_COUNTS[spread]
        cards = shuffle.build_deck()[:count]
        return [
            {
                "position": position,
                "card": card,
                "orientation": "逆位置" if position % 2 == 0 else "正位置",
                "image": shuffle.image_path(card),
            }
            for position, card in enumerate(cards, 1)
        ]

    def test_all_spreads_render_to_png(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            for spread in shuffle.SPREAD_COUNTS:
                with self.subTest(spread=spread):
                    output = Path(temp_dir) / f"{spread}.png"
                    render_spread.render(
                        self.cards_for(spread), spread, "展開テスト", output, self.root
                    )
                    self.assertTrue(output.is_file())
                    with Image.open(output) as image:
                        self.assertEqual("PNG", image.format)
                        self.assertGreater(image.width, 0)
                        self.assertGreater(image.height, 0)

    def test_attribution_is_burned_into_every_image(self):
        """カード画像の出典表記が画像下部に描かれていること。

        Misskey へは合成画像しか出さないので、出典が画像単体で完結している必要がある
        （AGENTS.md §6.1）。
        """
        self.assertTrue(render_spread.ATTRIBUTION_LINES)
        self.assertIn("Rider", render_spread.ATTRIBUTION_LINES[0])
        self.assertIn("metabismuth/tarot-json", render_spread.ATTRIBUTION_LINES[1])

        footer_band = 16 + len(render_spread.ATTRIBUTION_LINES) * render_spread.ATTRIBUTION_LEADING + 10
        with tempfile.TemporaryDirectory() as temp_dir:
            for spread in ("one", "celtic"):
                with self.subTest(spread=spread):
                    output = Path(temp_dir) / f"{spread}.png"
                    render_spread.render(
                        self.cards_for(spread), spread, "出典テスト", output, self.root
                    )
                    with Image.open(output) as image:
                        band = image.crop((0, image.height - footer_band, image.width, image.height))
                        extrema = band.convert("RGB").getextrema()
                    # どれかのチャンネルで最小≠最大なら、その帯は背景一色ではない＝何か描かれている
                    self.assertTrue(any(low != high for low, high in extrema),
                                    "出典表記の帯が背景一色になっています")

    def test_two_card_layout(self):
        """2枚引きも陣形画像にできること（Misskey 向けの仕様変更）。"""
        self.assertIn("two", shuffle.SPREAD_COUNTS)
        positions = render_spread.layout("two")
        self.assertEqual({1, 2}, set(positions))
        self.assertNotEqual(positions[1][0], positions[2][0])   # 横に並ぶ

    def test_rejects_incomplete_position_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ValueError):
                render_spread.render(
                    self.cards_for("three")[:2],
                    "three",
                    "",
                    Path(temp_dir) / "invalid.png",
                    self.root,
                )


if __name__ == "__main__":
    unittest.main()
