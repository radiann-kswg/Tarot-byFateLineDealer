#!/usr/bin/env python3
"""タロット78枚 × 正逆 = 156個の Misskey カスタム絵文字インポート用 zip を作る。

カード名とカード画像の対応は `shuffle.py` を正本として読み込む（ここでは複製しない）。
英語カード名だけは絵文字のエイリアス用に本ファイルで定義する。

出力される zip は Misskey のインポート形式（zip 直下に meta.json と画像が並ぶ）。
権利表記は絵文字ごとの `license` フィールドと、同梱の LICENSE-NOTICE.txt に入る。

使い方:
    # 既定（フルカラーPNG・元サイズ 350x600）
    python3 procedures/build_misskey_emoji.py

    # ファイルサイズを抑えたいとき（256色パレットPNGへ減色）
    python3 procedures/build_misskey_emoji.py --palette 256 \
        --out exports/misskey-emoji/misskey-emoji-tarot-rws-156_lite256.zip
"""
import argparse
import datetime as dt
import io
import json
import zipfile
from pathlib import Path

from PIL import Image

import shuffle

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CARDS_DIR = PROJECT_ROOT / "assets" / "cards-rws"
DEFAULT_OUT = PROJECT_ROOT / "exports" / "misskey-emoji" / "misskey-emoji-tarot-rws-156.zip"

# --- 絵文字エイリアス用の英語カード名 ------------------------------------------
# 日本語名は shuffle.py が正本。ここは英語表記だけを持つ。
MAJOR_EN = [
    "The Fool", "The Magician", "The High Priestess", "The Empress", "The Emperor",
    "The Hierophant", "The Lovers", "The Chariot", "Strength", "The Hermit",
    "Wheel of Fortune", "Justice", "The Hanged Man", "Death", "Temperance",
    "The Devil", "The Tower", "The Star", "The Moon", "The Sun",
    "Judgement", "The World",
]
SUIT_EN = {"ワンド": "Wands", "カップ": "Cups", "ソード": "Swords", "ペンタクル": "Pentacles"}
RANK_EN = {
    "エース": "Ace", "2": "Two", "3": "Three", "4": "Four", "5": "Five",
    "6": "Six", "7": "Seven", "8": "Eight", "9": "Nine", "10": "Ten",
    "ペイジ": "Page", "ナイト": "Knight", "クイーン": "Queen", "キング": "King",
}

# --- 絵文字のメタ情報 ----------------------------------------------------------
NAME_PREFIX = "tarot_"
REVERSED_SUFFIX = "_r"
CATEGORY_UPRIGHT = "タロットカード(RWS)/正位置"
CATEGORY_REVERSED = "タロットカード(RWS)/逆位置"

# 原画の権利状態と、画像データ取得元（MIT）の双方を明記する。
_LICENSE_BASE = (
    "Public Domain（原画）／MIT（画像データ配布元）｜"
    "原画：Pamela Colman Smith 画・Arthur Edward Waite 監修 "
    "\"Rider–Waite–Smith Tarot\"（1909年、William Rider & Son 刊、英国）。"
    "著作権保護期間満了によりパブリックドメイン"
    "（米国：1929年以前の刊行物／日本・英国等：画家 Pamela Colman Smith は1951年没）。｜"
    "画像データ取得元：https://github.com/metabismuth/tarot-json"
    "（MIT License, Copyright (c) 2019 equokka）｜加工："
)
LICENSE_UPRIGHT = _LICENSE_BASE + "JPEG から PNG へ変換（画像内容の改変なし）。"
LICENSE_REVERSED = _LICENSE_BASE + "JPEG から PNG へ変換のうえ、逆位置表現として原画像を180度回転。"

LICENSE_NOTICE = """\
Rider–Waite–Smith タロット カスタム絵文字セット（156個）
=========================================================

■ 収録内容
  タロット78枚 × 正位置／逆位置 = 156個の PNG 画像（350×600px）と、
  Misskey インポート用の meta.json。

■ 原画の権利状態：パブリックドメイン
  作品名   : Rider–Waite–Smith Tarot（Rider–Waite Tarot / Waite–Smith Tarot）
  画       : Pamela Colman Smith（1878–1951）
  監修     : Arthur Edward Waite（1857–1942）
  初版刊行 : 1909年、William Rider & Son（英国ロンドン）

  ・米国：1929年以前に刊行された著作物のため、著作権保護期間は満了している。
  ・日本・英国など「著作者の死後70年」を保護期間とする国：
    画家 Pamela Colman Smith は1951年没であり、保護期間は満了している。
  ・上記は本セット収録の「1909年初版に基づく線画・彩色」に対する記述であり、
    現代の再彩色版・リマスター版・市販デッキの画像には適用されない。

■ 画像データの取得元
  https://github.com/metabismuth/tarot-json
  ライセンス : MIT License
  Copyright (c) 2019 equokka
  （MIT ライセンス全文は本セット同梱の SOURCE-LICENSE-MIT.txt を参照）

  ※ MIT ライセンスは「取得元リポジトリが配布するデータ一式」に対するものであり、
    パブリックドメインである原画そのものの権利状態を変更するものではない。
    再配布にあたり著作権表示とライセンス全文を保持する条件を満たすため、
    上記の表示と全文を同梱している。

■ 本セットでの加工
{modifications}

■ 使い方（Misskey）
  コントロールパネル → カスタム絵文字 → インポート から、この zip を
  そのままアップロードする。絵文字名は tarot_m00（正位置）／tarot_m00_r（逆位置）の形式。
  カテゴリは「タロットカード(RWS)/正位置」「タロットカード(RWS)/逆位置」。
  ライセンス欄には上記の要約が各絵文字ごとに記録されている。

■ 出典表示のお願い（法的義務ではないが推奨）
  原画はパブリックドメインのため出典表示の義務はないが、
  絵柄の由来が分かるよう、可能であれば
  「Rider–Waite–Smith Tarot (1909), art by Pamela Colman Smith — Public Domain」
  と添えていただけると親切です。
"""


def emoji_name(card, reversed_=False):
    """カード名 → Misskey の絵文字名。**この規則の正本はこの関数。**

    Bot 側（`bot/emoji.py`）はこの関数を import して使う。規則を二重に持たないこと。
    """
    base = Path(shuffle.image_path(card)).stem      # 例: m00 / w01
    return NAME_PREFIX + base + (REVERSED_SUFFIX if reversed_ else "")


def english_name(card):
    """shuffle.py のカード名（日本語）に対応する英語カード名を返す。"""
    if card in shuffle.MAJOR:
        return MAJOR_EN[shuffle.MAJOR.index(card)]
    suit, rank = card.split("の", 1)
    return f"{RANK_EN[rank]} of {SUIT_EN[suit]}"


def slug(text):
    return text.lower().replace(" ", "_")


def build_entries(palette=0):
    """(meta.json の emojis エントリ, {画像ファイル名: 元画像パス}) を返す。"""
    entries = []
    sources = {}
    for card in shuffle.build_deck():
        en = english_name(card)
        for reversed_ in (False, True):
            name = emoji_name(card, reversed_)
            file_name = f"{name}.png"
            orient = "逆位置" if reversed_ else "正位置"
            aliases = list(dict.fromkeys([
                f"{card}{orient}",
                card,
                slug(en) + ("_reversed" if reversed_ else ""),
                slug(en),
                orient,
                "タロット",
                "tarot",
            ]))
            license_ = LICENSE_REVERSED if reversed_ else LICENSE_UPRIGHT
            if palette:
                license_ += f"ファイルサイズ削減のため{palette}色に減色。"
            entries.append({
                "downloaded": True,
                "fileName": file_name,
                "emoji": {
                    "name": name,
                    "category": CATEGORY_REVERSED if reversed_ else CATEGORY_UPRIGHT,
                    "aliases": aliases,
                    "license": license_,
                    "isSensitive": False,
                    "localOnly": False,
                    "roleIdsThatCanBeUsedThisEmojiAsReaction": [],
                },
            })
            sources[file_name] = (PROJECT_ROOT / shuffle.image_path(card), reversed_)
    return entries, sources


def render_png(src_path, reversed_, palette=0):
    img = Image.open(src_path).convert("RGB")
    if reversed_:
        img = img.rotate(180)
    if palette:
        img = img.quantize(colors=palette, method=Image.MEDIANCUT,
                           dither=Image.FLOYDSTEINBERG)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def license_notice(palette=0):
    lines = [
        "  ・JPEG から PNG へ変換（画素内容の改変なし、可逆）。",
        "  ・逆位置（*_r）の画像は、原画像を180度回転したもの。",
    ]
    if palette:
        lines.append(f"  ・ファイルサイズ削減のため、{palette}色のパレット画像に減色している"
                     "（ディザリングあり）。")
    return LICENSE_NOTICE.format(modifications="\n".join(lines))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cards-dir", type=Path, default=DEFAULT_CARDS_DIR,
                    help="カード画像のディレクトリ（既定: assets/cards-rws）")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT,
                    help="出力する zip のパス")
    ap.add_argument("--host", default="localhost",
                    help="meta.json に書く host（インポート時には使われない）")
    ap.add_argument("--palette", type=int, default=0, metavar="N",
                    help="PNG を N 色のパレット画像に減色する（0=減色しない）")
    args = ap.parse_args()

    now = dt.datetime.now(dt.timezone.utc)
    entries, sources = build_entries(args.palette)

    names = [e["emoji"]["name"] for e in entries]
    if len(names) != 156 or len(set(names)) != 156:
        raise SystemExit(f"絵文字が156個ちょうどになっていません: {len(names)}件 / 重複を除いて{len(set(names))}件")

    meta = {
        "metaVersion": 2,
        "host": args.host,
        "exportedAt": now.isoformat().replace("+00:00", "Z"),
        "emojis": entries,
    }

    mit_path = args.cards_dir / "SOURCE-LICENSE.txt"
    if not mit_path.is_file():
        raise SystemExit(f"取得元の MIT ライセンス全文が見つかりません: {mit_path}")
    mit = mit_path.read_text(encoding="utf-8")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.out, "w", zipfile.ZIP_DEFLATED) as zf:
        def write(name, data):
            if isinstance(data, str):
                data = data.encode("utf-8")
            info = zipfile.ZipInfo(name, date_time=now.timetuple()[:6])
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, data)

        write("meta.json", json.dumps(meta, ensure_ascii=False, indent=2))
        for file_name in sorted(sources):
            src_path, reversed_ = sources[file_name]
            if not src_path.is_file():
                raise SystemExit(f"カード画像が見つかりません: {src_path}")
            write(file_name, render_png(src_path, reversed_, args.palette))
        write("LICENSE-NOTICE.txt", license_notice(args.palette))
        write("SOURCE-LICENSE-MIT.txt", mit)

    size_mib = args.out.stat().st_size / 1024 / 1024
    print(f"OK: {args.out} ({size_mib:.1f} MiB)")
    print(f"  絵文字 {len(entries)} 件（正位置78 / 逆位置78）")


if __name__ == "__main__":
    main()
