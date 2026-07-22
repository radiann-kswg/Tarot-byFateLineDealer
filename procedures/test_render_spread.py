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
