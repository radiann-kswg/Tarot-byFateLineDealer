import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image, ImageChops

import build_misskey_emoji as builder
import shuffle


class EntryTests(unittest.TestCase):
    def setUp(self):
        self.entries, self.sources = builder.build_entries()

    def test_156_entries_with_unique_names(self):
        self.assertEqual(156, len(self.entries))
        names = [e["emoji"]["name"] for e in self.entries]
        self.assertEqual(156, len(set(names)))

    def test_names_are_misskey_safe(self):
        for e in self.entries:
            name = e["emoji"]["name"]
            self.assertRegex(name, r"^[a-z0-9_]+$", name)

    def test_categories_are_split_by_orientation(self):
        upright = [e for e in self.entries
                   if e["emoji"]["category"] == builder.CATEGORY_UPRIGHT]
        reversed_ = [e for e in self.entries
                     if e["emoji"]["category"] == builder.CATEGORY_REVERSED]
        self.assertEqual(78, len(upright))
        self.assertEqual(78, len(reversed_))

    def test_license_mentions_public_domain_and_mit(self):
        for e in self.entries:
            license_ = e["emoji"]["license"]
            self.assertIn("Public Domain", license_)
            self.assertIn("MIT License", license_)
            self.assertIn("Pamela Colman Smith", license_)
            self.assertIn("equokka", license_)

    def test_reversed_license_states_the_rotation(self):
        for e in self.entries:
            if e["emoji"]["category"] == builder.CATEGORY_REVERSED:
                self.assertIn("180度回転", e["emoji"]["license"])

    def test_aliases_cover_japanese_and_english(self):
        by_name = {e["emoji"]["name"]: e["emoji"] for e in self.entries}
        self.assertIn("愚者", by_name["tarot_m00"]["aliases"])
        self.assertIn("the_fool", by_name["tarot_m00"]["aliases"])
        self.assertIn("愚者逆位置", by_name["tarot_m00_r"]["aliases"])
        self.assertIn("the_fool_reversed", by_name["tarot_m00_r"]["aliases"])
        self.assertIn("ペンタクルのキング", by_name["tarot_p14"]["aliases"])
        self.assertIn("king_of_pentacles", by_name["tarot_p14"]["aliases"])

    def test_every_card_image_exists(self):
        for file_name, (src_path, _) in self.sources.items():
            self.assertTrue(src_path.is_file(), f"{file_name} -> {src_path}")

    def test_english_name_covers_the_whole_deck(self):
        names = {builder.english_name(card) for card in shuffle.build_deck()}
        self.assertEqual(78, len(names))


class RenderTests(unittest.TestCase):
    def test_reversed_image_is_the_upright_rotated_180(self):
        src = builder.PROJECT_ROOT / shuffle.image_path("愚者")
        up = Image.open(io.BytesIO(builder.render_png(src, False))).convert("RGB")
        rev = Image.open(io.BytesIO(builder.render_png(src, True))).convert("RGB")
        self.assertEqual((350, 600), up.size)
        self.assertEqual((350, 600), rev.size)
        self.assertIsNone(ImageChops.difference(up.rotate(180), rev).getbbox())


class ZipTests(unittest.TestCase):
    """zip 全体を組み立てると重いので、構造だけを小さく確かめる。"""

    def test_zip_layout_is_flat_and_consistent(self):
        entries, sources = builder.build_entries()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "t.zip"
            meta = {"metaVersion": 2, "host": "x", "exportedAt": "x", "emojis": entries}
            with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("meta.json", json.dumps(meta, ensure_ascii=False))
                for file_name in sources:
                    zf.writestr(file_name, b"")
                zf.writestr("LICENSE-NOTICE.txt", builder.license_notice())
            with zipfile.ZipFile(out) as zf:
                names = zf.namelist()
                self.assertFalse([n for n in names if "/" in n], "サブフォルダが混ざっている")
                pngs = sorted(n for n in names if n.endswith(".png"))
                self.assertEqual(sorted(e["fileName"] for e in entries), pngs)
                self.assertIn("meta.json", names)
                self.assertIn("LICENSE-NOTICE.txt", names)


if __name__ == "__main__":
    unittest.main()
