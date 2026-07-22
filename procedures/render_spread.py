#!/usr/bin/env python3
"""引いたカードを『陣形』ごと1枚の画像に合成する。

`shuffle.py --json` の出力（position / card / orientation / image を含むリスト）を
そのまま受け取り、スプレッドの配置に並べたPNGを書き出す。
逆位置のカードは表示レイヤーで180°回転（元画像は編集しない）。
ケルト十字の②（障害）は①に交差させて90°回転して重ねる。

使い方:
    python3 procedures/shuffle.py --spread celtic --json > /tmp/draw.json
    python3 procedures/render_spread.py --spread celtic --json /tmp/draw.json \
        --title "ケルト十字 — 相談テーマ" --out readings/2026-07-22_celtic.png

    # パイプでもよい
    python3 procedures/shuffle.py --spread three --json \
        | python3 procedures/render_spread.py --spread three --out /tmp/three.png
"""
import argparse
import json
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import shuffle

# --- 見た目の基本設定 ---------------------------------------------------------
CARD_W, CARD_H = 210, 360          # 合成時のカード寸法（原画 350x600 と同比率）
BG = (24, 22, 34)                  # 背景（落ち着いた紫紺）
CARD_BORDER = (196, 176, 132)      # カード縁（淡い金）
BADGE_BG = (196, 176, 132)
BADGE_FG = (24, 22, 34)
TEXT = (236, 232, 224)
SUBTEXT = (188, 182, 196)
REVERSED_TAG = (214, 150, 150)
ATTRIBUTION = (142, 136, 156)      # 出典表記（本文より控えめに）

ATTRIBUTION_SIZE = 16
ATTRIBUTION_LEADING = 22

FONT_CANDIDATES = {
    False: [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        r"C:\Windows\Fonts\YuGothR.ttc",
        r"C:\Windows\Fonts\meiryo.ttc",
    ],
    True: [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        r"C:\Windows\Fonts\YuGothB.ttc",
        r"C:\Windows\Fonts\meiryob.ttc",
    ],
}

CIRCLED = {i: c for i, c in enumerate("①②③④⑤⑥⑦⑧⑨⑩", start=1)}

# カード画像の出典表記（権利表記＝作者管理領域）。
# 記載内容の出典は assets/cards-rws/README.md。文言を変えるときは同 README と併せて更新すること。
# 画像単体で出典が完結するよう、合成画像の最下部に必ず焼き込む。
ATTRIBUTION_LINES = [
    "カード画像：Rider–Waite–Smith Tarot (1909) / 画: Pamela Colman Smith・監修: A.E. Waite / パブリックドメイン",
    "取得元：https://github.com/metabismuth/tarot-json (MIT License)",
]

# 各スプレッドの位置の意味（凡例に使用）
POSITION_MEANINGS = {
    "one": {1: "問いへの核心・今のあなたへのメッセージ"},
    # two / three は並びの意味が問いに応じて変わるため、凡例では番号バッジのみを示す
    # （エントリを持たない＝意味なし。凡例側で「番号 カード名」に切り替わる）
    "hexagram": {
        1: "過去", 2: "現在", 3: "未来", 4: "対策・打つ手",
        5: "周囲の状況・環境", 6: "相手の気持ち・本音", 7: "最終的な結論",
    },
    "celtic": {
        1: "現在の状況（本質）", 2: "目の前の障害・課題（①に交差）",
        3: "顕在意識・目標", 4: "潜在意識・根の原因", 5: "過去",
        6: "近い未来", 7: "相談者自身の立場・姿勢", 8: "周囲・環境からの影響",
        9: "希望と不安", 10: "最終結果",
    },
}


def _font(size, bold=False):
    """日本語を表示できるフォントをOS横断で選ぶ。"""
    env_font = os.environ.get("TAROT_SPREAD_FONT")
    candidates = ([env_font] if env_font else []) + FONT_CANDIDATES[bold]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return ImageFont.truetype(candidate, size)
    raise RuntimeError(
        "日本語フォントが見つかりません。TAROT_SPREAD_FONT に "
        "日本語対応の .ttf/.ttc ファイルを指定してください。"
    )


def _text_width(text, font):
    """キャンバス生成前に文字列の描画幅を測る。"""
    scratch = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    box = scratch.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def _fit(text, font, max_width):
    """max_width に収まるよう末尾を省略する（はみ出して切れるのを防ぐ）。"""
    if _text_width(text, font) <= max_width:
        return text
    trimmed = text
    while trimmed and _text_width(trimmed + "…", font) > max_width:
        trimmed = trimmed[:-1]
    return trimmed + "…" if trimmed else "…"


def layout(spread):
    """位置番号 -> (中心x, 中心y, 追加回転角) を相対座標で返す。"""
    hg, vg = 74, 44
    pv = CARD_H + vg                      # 縦ピッチ
    if spread == "one":
        return {1: (0, 0, 0)}
    if spread == "two":
        px = CARD_W + hg
        return {1: (0, 0, 0), 2: (px, 0, 0)}
    if spread == "three":
        px = CARD_W + hg
        return {1: (0, 0, 0), 2: (px, 0, 0), 3: (2 * px, 0, 0)}
    if spread == "hexagram":
        px = CARD_W + hg
        ph = pv * 0.62                    # 星形は縦を詰める
        return {
            1: (px, 0, 0),
            6: (0, ph, 0), 2: (2 * px, ph, 0),
            7: (px, 2 * ph, 0),
            5: (0, 3 * ph, 0), 3: (2 * px, 3 * ph, 0),
            4: (px, 4 * ph, 0),
        }
    if spread == "celtic":
        # 十字部：①中心、②交差(90°)、③上・④下、⑤左・⑥右
        dx = CARD_H / 2 + hg + CARD_W / 2         # ⑤⑥を交差カードから逃がす距離
        staff_x = dx + CARD_W / 2 + hg + CARD_W / 2  # スタッフ列のx
        ps = CARD_H + 24                          # スタッフ縦ピッチ
        return {
            1: (0, 0, 0),
            2: (0, 0, 90),
            3: (0, -pv, 0),
            4: (0, pv, 0),
            5: (-dx, 0, 0),
            6: (dx, 0, 0),
            10: (staff_x, -1.5 * ps, 0),
            9: (staff_x, -0.5 * ps, 0),
            8: (staff_x, 0.5 * ps, 0),
            7: (staff_x, 1.5 * ps, 0),
        }
    raise ValueError(f"未知のスプレッド: {spread}")


def prep_card(img_path, reversed_, extra_rot):
    card = Image.open(img_path).convert("RGBA").resize((CARD_W, CARD_H))
    # 縁取り
    bordered = Image.new("RGBA", (CARD_W + 6, CARD_H + 6), CARD_BORDER + (255,))
    bordered.paste(card, (3, 3), card)
    rot = (extra_rot + (180 if reversed_ else 0)) % 360
    if rot:
        bordered = bordered.rotate(rot, expand=True)
    return bordered


def draw_badge(base, cx, cy, num):
    d = ImageDraw.Draw(base)
    r = 22
    x, y = cx, cy
    d.ellipse([x - r, y - r, x + r, y + r], fill=BADGE_BG, outline=BG, width=3)
    f = _font(26, bold=True)
    t = str(num)
    tb = d.textbbox((0, 0), t, font=f)
    d.text((x - (tb[2] - tb[0]) / 2, y - (tb[3] - tb[1]) / 2 - tb[1]),
           t, fill=BADGE_FG, font=f)


def render(cards, spread, title, out_path, root):
    lay = layout(spread)
    by_pos = {c["position"]: c for c in cards}
    missing = sorted(set(lay) - set(by_pos))
    extra = sorted(set(by_pos) - set(lay))
    if missing or extra:
        raise ValueError(
            f"{spread} の位置データが不正です（不足: {missing or 'なし'}、"
            f"余分: {extra or 'なし'}）"
        )

    # --- レイアウトのピクセル範囲を算出 ---
    boxes = {}
    for pos, (rx, ry, rot) in lay.items():
        c = by_pos[pos]
        reversed_ = c["orientation"].startswith("逆")
        img = prep_card(root / c["image"], reversed_, rot)
        w, h = img.size
        boxes[pos] = (rx - w / 2, ry - h / 2, w, h, img)

    minx = min(b[0] for b in boxes.values())
    miny = min(b[1] for b in boxes.values())
    maxx = max(b[0] + b[2] for b in boxes.values())
    maxy = max(b[1] + b[3] for b in boxes.values())

    margin = 60
    title_h = 92
    legend_rows = (len(cards) + 1) // 2
    legend_h = 40 + legend_rows * 40 + 30

    # 出典表記フッター（画像単体で出典が完結するように必ず入れる）
    attribution_font = _font(ATTRIBUTION_SIZE)
    attribution_w = max(_text_width(line, attribution_font) for line in ATTRIBUTION_LINES)
    attribution_h = 16 + len(ATTRIBUTION_LINES) * ATTRIBUTION_LEADING + 10

    field_w = maxx - minx
    field_h = maxy - miny
    W = int(field_w + margin * 2)
    W = max(W, 1000, int(attribution_w + margin * 2))  # 出典表記が切れない幅を確保
    H = int(title_h + field_h + margin + legend_h + attribution_h)

    canvas = Image.new("RGBA", (W, H), BG + (255,))
    d = ImageDraw.Draw(canvas)

    # タイトル
    if title:
        tf = _font(34, bold=True)
        d.text((margin, 30), _fit(title, tf, W - margin * 2), fill=TEXT, font=tf)
    d.line([(margin, title_h - 8), (W - margin, title_h - 8)], fill=(70, 64, 88), width=2)

    # フィールドのオフセット（中央寄せ）
    off_x = (W - field_w) / 2 - minx
    off_y = title_h + margin / 2 - miny

    # 描画順：先に交差される①、その上に②が来るよう position 昇順で。
    # ①→②の重なりを正しくするため、②を①の直後に置く昇順で問題ない。
    for pos in sorted(boxes):
        bx, by, w, h, img = boxes[pos]
        px, py = int(bx + off_x), int(by + off_y)
        canvas.alpha_composite(img, (px, py))

    # バッジ（各カード中心のやや上・左に）
    for pos, (rx, ry, rot) in lay.items():
        cx = rx + off_x
        cy = ry + off_y
        # カード左上寄りにバッジ
        draw_badge(canvas, cx - CARD_W / 2 + 10, cy - CARD_H / 2 + 10
                   if rot == 0 else cy - CARD_W / 2 + 10, pos)

    # 凡例
    ly = title_h + field_h + margin - 10
    d.line([(margin, ly), (W - margin, ly)], fill=(70, 64, 88), width=2)
    ly += 20
    lf = _font(22, bold=True)
    d.text((margin, ly), "── 陣形と結果 ──", fill=SUBTEXT, font=lf)
    ly += 40
    ef = _font(21)
    meanings = POSITION_MEANINGS.get(spread, {})
    col_w = (W - margin * 2) // 2
    for idx, pos in enumerate(sorted(by_pos)):
        c = by_pos[pos]
        col = idx % 2
        row = idx // 2
        x = margin + col * col_w
        y = ly + row * 40
        mark = CIRCLED.get(pos, str(pos))
        meaning = meanings.get(pos, "")
        reversed_ = c["orientation"].startswith("逆")
        label = f"{mark} {meaning}：{c['card']}" if meaning else f"{mark} {c['card']}"
        d.text((x, y), label, fill=TEXT, font=ef)
        tb = d.textbbox((x, y), label, font=ef)
        tag = "（逆位置）" if reversed_ else "（正位置）"
        d.text((tb[2] + 6, y), tag,
               fill=REVERSED_TAG if reversed_ else SUBTEXT, font=ef)

    # 出典表記（権利表記＝作者管理領域。文言は ATTRIBUTION_LINES を参照）
    ay = ly + legend_rows * 40 + 16
    for line in ATTRIBUTION_LINES:
        d.text((margin, ay), line, fill=ATTRIBUTION, font=attribution_font)
        ay += ATTRIBUTION_LEADING

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out_path, "PNG")
    return out_path


def main():
    p = argparse.ArgumentParser(description="スプレッドを陣形画像に合成する")
    p.add_argument("--spread", default="celtic",
                   choices=list(shuffle.SPREAD_COUNTS))  # 枚数の正本は shuffle.py
    p.add_argument("--json", help="shuffle.py --json の出力ファイル（省略時は標準入力）")
    p.add_argument("--draw", action="store_true",
                   help="shuffle.py と同じ抽選処理でカードを引き、そのまま描画する")
    p.add_argument("--upright-only", action="store_true",
                   help="--draw 使用時に正位置のみで引く")
    p.add_argument("--json-out",
                   help="--draw の抽選結果もJSONへ保存する（読み解き用）")
    p.add_argument("--title", default="", help="画像の見出し")
    p.add_argument("--out", required=True, help="出力PNGパス")
    p.add_argument("--root", default=None,
                   help="画像パスの基準（既定：このスクリプトの1つ上=プロジェクト根）")
    args = p.parse_args()

    if args.draw and args.json:
        p.error("--draw と --json は同時に指定できません")
    if args.draw:
        picks = shuffle.draw(shuffle.SPREAD_COUNTS[args.spread], args.upright_only)
        cards = [
            {
                "position": position,
                "card": card,
                "orientation": orientation,
                "image": shuffle.image_path(card),
            }
            for position, (card, orientation) in enumerate(picks, 1)
        ]
        if args.json_out:
            json_out = Path(args.json_out)
            json_out.parent.mkdir(parents=True, exist_ok=True)
            json_out.write_text(
                json.dumps(cards, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
    else:
        if args.upright_only or args.json_out:
            p.error("--upright-only と --json-out は --draw と一緒に指定してください")
        raw = Path(args.json).read_text(encoding="utf-8") if args.json else sys.stdin.read()
        cards = json.loads(raw)
    root = Path(args.root) if args.root else Path(__file__).resolve().parent.parent
    out = render(cards, args.spread, args.title, args.out, root)
    print(f"書き出し完了: {out}")


if __name__ == "__main__":
    main()
