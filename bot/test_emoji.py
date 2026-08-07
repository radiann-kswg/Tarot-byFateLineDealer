import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot import emoji as emoji_mod          # noqa: E402
from bot import ssot, tarot                 # noqa: E402
from bot.tarot import shuffle               # noqa: E402


class EmojiIndexTests(unittest.TestCase):
    def test_index_has_156_entries(self):
        index = emoji_mod.emoji_index()
        self.assertEqual(156, len(index))

    def test_index_covers_every_card_in_both_orientations(self):
        index = emoji_mod.emoji_index()
        for card in shuffle.build_deck():
            self.assertEqual((card, "正位置"), index[emoji_mod.build_emoji_name(card, False)])
            self.assertEqual((card, "逆位置"), index[emoji_mod.build_emoji_name(card, True)])

    def test_names_match_the_builder_convention(self):
        self.assertEqual("tarot_m00", emoji_mod.build_emoji_name("愚者", False))
        self.assertEqual("tarot_m00_r", emoji_mod.build_emoji_name("愚者", True))
        self.assertEqual("tarot_p14", emoji_mod.build_emoji_name("ペンタクルのキング", False))

    def test_naming_rule_comes_from_the_builder_not_a_copy(self):
        """絵文字名の規則を Bot 側で二重定義しないこと（AGENTS.md §5）。"""
        import build_misskey_emoji
        self.assertIs(build_misskey_emoji.emoji_name, emoji_mod.build_emoji_name)
        self.assertEqual(build_misskey_emoji.NAME_PREFIX, emoji_mod.NAME_PREFIX)
        self.assertEqual(build_misskey_emoji.REVERSED_SUFFIX, emoji_mod.REVERSED_SUFFIX)


class ExtractTests(unittest.TestCase):
    def test_extracts_cards_in_order_with_orientation(self):
        cards, unknown = emoji_mod.extract_cards(":tarot_m00: と :tarot_w03_r: だよ")
        self.assertEqual([], unknown)
        self.assertEqual([("愚者", "正位置", 1), ("ワンドの3", "逆位置", 2)],
                         [(c["card"], c["orientation"], c["position"]) for c in cards])

    def test_accepts_remote_emoji_notation(self):
        cards, unknown = emoji_mod.extract_cards(":tarot_m00@example.com: :tarot_m01@.:")
        self.assertEqual([], unknown)
        self.assertEqual(["愚者", "魔術師"], [c["card"] for c in cards])

    def test_reports_unknown_tarot_emoji(self):
        cards, unknown = emoji_mod.extract_cards("これ :tarot_zzz: なに？")
        self.assertEqual([], cards)
        self.assertEqual([":tarot_zzz:"], unknown)

    def test_ignores_unrelated_emoji(self):
        cards, unknown = emoji_mod.extract_cards(":blobcat: :tarot_m00: :party_parrot:")
        self.assertEqual([], unknown)
        self.assertEqual(["愚者"], [c["card"] for c in cards])

    def test_image_path_comes_from_shuffle(self):
        cards, _ = emoji_mod.extract_cards(":tarot_m00:")
        self.assertEqual(shuffle.image_path("愚者"), cards[0]["image"])


class ModeTests(unittest.TestCase):
    def test_imagery_wins_over_meaning(self):
        self.assertEqual("imagery",
                         emoji_mod.choose_mode("この絵は何が描かれてるの？意味も知りたい", 1))

    def test_meaning(self):
        self.assertEqual("meaning", emoji_mod.choose_mode("このカードの意味を教えて", 1))

    def test_brought(self):
        self.assertEqual("brought", emoji_mod.choose_mode("引いてみたんだけど、どう思う？", 3))

    def test_default_is_meaning_for_one_card(self):
        self.assertEqual("meaning", emoji_mod.choose_mode("これ", 1))

    def test_default_is_brought_for_many_cards(self):
        self.assertEqual("brought", emoji_mod.choose_mode("これ", 3))


    def test_drawing_it_yourself_beats_generic_request_words(self):
        """「引いてみたけど…教えて」を解説へ落とさない（レビュー指摘）。"""
        for text in (
            "自分で引いたけど、この展開どう思うか教えて",
            "引いてみたので読み解き方を教えてください",
            "自分で引いた3枚、意味を読んでほしい",
            "転職の背景を知りたくて引いてみた",
            "彼の気持ちが知りたくて引いた。象徴的な並びだと思う",
        ):
            self.assertEqual("brought", emoji_mod.choose_mode(text, 3), text)

    def test_imagery_words_are_about_the_picture_only(self):
        """「背景」「象徴」だけで図像解説に倒れないこと。"""
        self.assertNotEqual("imagery", emoji_mod.choose_mode("転職の背景が気になる", 1))
        self.assertNotEqual("imagery", emoji_mod.choose_mode("象徴的な並びだね", 3))
        self.assertEqual("imagery", emoji_mod.choose_mode("この絵は何が描かれてるの", 1))


class WantsDrawTests(unittest.TestCase):
    def test_asking_mai_to_draw(self):
        self.assertTrue(emoji_mod.wants_fresh_draw("舞が引いてくれる？"))
        self.assertTrue(emoji_mod.wants_fresh_draw("占ってほしいな"))

    def test_user_drew_it_themselves_is_not_a_draw_request(self):
        """「引いてみた」を「引いて（ほしい）」と取り違えないこと。"""
        self.assertFalse(emoji_mod.wants_fresh_draw("引いてみたんだけど"))
        self.assertFalse(emoji_mod.wants_fresh_draw("自分で引いてみたよ"))


class InferSpreadTests(unittest.TestCase):
    def test_count_based_inference(self):
        self.assertEqual("one", emoji_mod.infer_spread("これ", 1)[0])
        self.assertEqual("three", emoji_mod.infer_spread("これ", 3)[0])
        self.assertEqual("hexagram", emoji_mod.infer_spread("これ", 7)[0])
        self.assertEqual("celtic", emoji_mod.infer_spread("これ", 10)[0])

    def test_explicit_name_wins_when_the_count_agrees(self):
        spread, reason = emoji_mod.infer_spread("ケルト十字で引いたよ", 10)
        self.assertEqual("celtic", spread)
        self.assertEqual("相談者の指定", reason)

    def test_name_and_count_disagree_asks_instead_of_guessing(self):
        """型の名前と枚数が噛み合わないときは尋ねる（AGENTS.md §4-7）。"""
        spread, reason = emoji_mod.infer_spread("ケルト十字で引いたよ", 4)
        self.assertIsNone(spread)
        self.assertIn("噛み合わない", reason)

    def test_asks_when_the_shape_cannot_be_decided(self):
        spread, _ = emoji_mod.infer_spread("これ見て", 5)
        self.assertIsNone(spread)

    def test_role_mention_means_read_as_a_line(self):
        spread, _ = emoji_mod.infer_spread("1枚目は過去で、順に読んでね", 4)
        self.assertEqual(emoji_mod.LINE_SPREAD, spread)

    def test_ordinary_consultation_words_are_not_position_roles(self):
        """「気持ち」「未来」だけで『役割の説明』とみなさない（レビュー指摘）。"""
        for text in ("この人の気持ちを知りたい", "未来が不安", "結果が出るのが怖い",
                     "過去の恋人のことで悩んでる"):
            self.assertFalse(emoji_mod.mentions_roles(text), text)
            self.assertIsNone(emoji_mod.infer_spread(text, 5)[0], text)

    def test_count_map_follows_shuffle(self):
        """枚数の正本は shuffle.SPREAD_COUNTS。手書きの逆写像を持たない。"""
        for spread, count in shuffle.SPREAD_COUNTS.items():
            self.assertEqual(spread, emoji_mod.infer_spread("これ", count)[0])

    def test_position_wording_is_not_a_spread_name(self):
        """「1枚目」を「1枚（ワンオラクル）」の指定と取り違えないこと。"""
        self.assertFalse(emoji_mod._mentions_keyword("1枚目は過去", "1枚"))
        self.assertTrue(emoji_mod._mentions_keyword("1枚で引いて", "1枚"))


class ParseTests(unittest.TestCase):
    def test_no_cards_means_no_mode(self):
        parsed = emoji_mod.parse("今日の運勢を占って")
        self.assertFalse(parsed.has_cards)
        self.assertIsNone(parsed.mode)

    def test_cards_and_a_draw_request_can_coexist(self):
        parsed = emoji_mod.parse(":tarot_m00: が出たけど、舞にも引いてほしい")
        self.assertTrue(parsed.has_cards)
        self.assertTrue(parsed.wants_draw)


class ValidateTests(unittest.TestCase):
    def test_accepts_parsed_cards(self):
        parsed = emoji_mod.parse(":tarot_m00: :tarot_s14_r:")
        tarot.validate_cards(parsed.cards)      # 例外が出なければよい

    def test_rejects_empty(self):
        with self.assertRaises(tarot.TarotError):
            tarot.validate_cards([])

    def test_rejects_unknown_card(self):
        with self.assertRaises(tarot.TarotError):
            tarot.validate_cards([{"position": 1, "card": "存在しない札",
                                   "orientation": "正位置", "image": "assets/cards-rws/m00.jpg"}])

    def test_rejects_gap_in_positions(self):
        parsed = emoji_mod.parse(":tarot_m00: :tarot_m01:")
        parsed.cards[1]["position"] = 3
        with self.assertRaises(tarot.TarotError):
            tarot.validate_cards(parsed.cards)


class ImageryTests(unittest.TestCase):
    def test_every_card_has_an_imagery_entry(self):
        index = ssot.imagery_index()
        for card in shuffle.build_deck():
            self.assertIn(card, index, card)

    def test_imagery_has_no_divination_keywords(self):
        """図像資料に占いの意味を書かない（AGENTS.md §3・役割の分離）。"""
        for name, body in ssot.imagery_index().items():
            self.assertNotIn("正位置キーワード", body, name)
            self.assertNotIn("逆位置キーワード", body, name)

    def test_entries_render_for_the_requested_cards_only(self):
        parsed = emoji_mod.parse(":tarot_m00: :tarot_m18:")
        text = ssot.imagery_entries(parsed.cards)
        self.assertIn("1. 愚者（正位置）", text)
        self.assertIn("2. 月（正位置）", text)
        self.assertNotIn("魔術師", text)

    def test_missing_entry_is_stated_not_hidden(self):
        text = ssot.imagery_entries([{"position": 1, "card": "存在しない札",
                                      "orientation": "正位置", "image": "x"}])
        self.assertIn("資料なし", text)


class TemplateTests(unittest.TestCase):
    def test_new_templates_exist(self):
        templates = ssot.load_templates()
        self.assertIn("spread-unclear", templates)
        self.assertIn("emoji-unknown", templates)

    def test_spread_unclear_fills_the_count(self):
        body = ssot.template("spread-unclear", count="5")
        self.assertIn("5枚", body)
        self.assertNotIn("{count}", body)


if __name__ == "__main__":
    unittest.main()
