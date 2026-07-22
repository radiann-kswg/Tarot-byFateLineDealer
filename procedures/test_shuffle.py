import unittest

import shuffle


class ShuffleTests(unittest.TestCase):
    def test_deck_contains_78_unique_cards(self):
        deck = shuffle.build_deck()
        self.assertEqual(78, len(deck))
        self.assertEqual(78, len(set(deck)))

    def test_draw_has_no_duplicates(self):
        cards = [card for card, _ in shuffle.draw(10)]
        self.assertEqual(10, len(set(cards)))

    def test_every_card_has_an_existing_image(self):
        project_root = shuffle.Path(__file__).resolve().parent.parent
        for card in shuffle.build_deck():
            self.assertTrue((project_root / shuffle.image_path(card)).is_file(), card)

    def test_upright_only(self):
        self.assertTrue(all(orientation == "正位置" for _, orientation in shuffle.draw(78, True)))

    def test_spread_counts(self):
        self.assertEqual(
            {"one": 1, "two": 2, "three": 3, "hexagram": 7, "celtic": 10},
            shuffle.SPREAD_COUNTS,
        )


if __name__ == "__main__":
    unittest.main()
