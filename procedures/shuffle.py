#!/usr/bin/env python3
"""タロットカードを公正にシャッフルして引くためのスクリプト。

使い方:
    python3 shuffle.py --count 3
    python3 shuffle.py --spread celtic
    python3 shuffle.py --count 3 --upright-only
"""
import argparse
import json
from pathlib import Path
import secrets

MAJOR = [
    "愚者", "魔術師", "女教皇", "女帝", "皇帝", "教皇", "恋人", "戦車",
    "力", "隠者", "運命の輪", "正義", "吊された男", "死神", "節制",
    "悪魔", "塔", "星", "月", "太陽", "審判", "世界",
]
SUITS = {"ワンド": "火", "カップ": "水", "ソード": "風", "ペンタクル": "地"}
RANKS = ["エース", "2", "3", "4", "5", "6", "7", "8", "9", "10",
         "ペイジ", "ナイト", "クイーン", "キング"]

SPREAD_COUNTS = {"one": 1, "two": 2, "three": 3, "hexagram": 7, "celtic": 10}

MAJOR_IMAGES = {name: f"m{i:02d}.jpg" for i, name in enumerate(MAJOR)}
SUIT_IMAGE_PREFIX = {"ワンド": "w", "カップ": "c", "ソード": "s", "ペンタクル": "p"}
RANK_IMAGE_NUMBER = {rank: i for i, rank in enumerate(RANKS, 1)}


def build_deck():
    deck = list(MAJOR)
    for suit in SUITS:
        for rank in RANKS:
            deck.append(f"{suit}の{rank}")
    return deck  # 78枚


def draw(count, upright_only=False):
    deck = build_deck()
    # secrets を使った Fisher-Yates シャッフル（暗号学的乱数で公正に）
    for i in range(len(deck) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        deck[i], deck[j] = deck[j], deck[i]
    picks = deck[:count]
    result = []
    for card in picks:
        orientation = "正位置"
        if not upright_only and secrets.randbelow(2) == 1:
            orientation = "逆位置"
        result.append((card, orientation))
    return result


def image_path(card):
    """カード名に対応する、プロジェクト相対の仮画像パスを返す。"""
    if card in MAJOR_IMAGES:
        filename = MAJOR_IMAGES[card]
    else:
        suit, rank = card.split("の", 1)
        filename = f"{SUIT_IMAGE_PREFIX[suit]}{RANK_IMAGE_NUMBER[rank]:02d}.jpg"
    return (Path("assets") / "cards-rws" / filename).as_posix()


def main():
    p = argparse.ArgumentParser(description="タロットを公正に引く")
    p.add_argument("--count", type=int, help="引く枚数")
    p.add_argument("--spread", choices=SPREAD_COUNTS.keys(),
                   help="one / two / three / hexagram / celtic")
    p.add_argument("--upright-only", action="store_true", help="正位置のみ")
    p.add_argument("--json", action="store_true", help="画像パス付きJSONで出力")
    args = p.parse_args()

    count = args.count or (SPREAD_COUNTS[args.spread] if args.spread else 1)
    deck = build_deck()
    assert len(deck) == 78, f"デッキ枚数エラー: {len(deck)}"

    picks = draw(count, args.upright_only)
    if args.json:
        payload = [
            {
                "position": i,
                "card": card,
                "orientation": orient,
                "image": image_path(card),
            }
            for i, (card, orient) in enumerate(picks, 1)
        ]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"— {count}枚を引きました —")
        for i, (card, orient) in enumerate(picks, 1):
            print(f"{i}. {card} ({orient}) [{image_path(card)}]")


if __name__ == "__main__":
    main()
