"""抽選と陣形画像 — 既存資産（procedures/）をそのまま使う層。

**このモジュールは独自のカード選択ロジックを持たない**（AGENTS.md §4-1・§4-6）。
カードは必ず `shuffle.draw()`（`secrets` による暗号学的乱数）で引き、
Claude には「もう引かれたカード」を渡すだけにする。

サブプロセスではなく import で呼ぶのは、
  - Windows の PowerShell パイプで UTF-8 の JSON が壊れる問題を避けるため
  - 抽選の実装がリポジトリに1つしかないことをコード上も明示するため
"""
from __future__ import annotations

from pathlib import Path
import sys

from . import PROJECT_ROOT

# procedures/ をモジュールとして読めるようにする（render_spread.py が `import shuffle` するため必須）
_PROCEDURES = PROJECT_ROOT / "procedures"
if str(_PROCEDURES) not in sys.path:
    sys.path.insert(0, str(_PROCEDURES))

import render_spread  # noqa: E402  (sys.path 追加後に import する必要がある)
import shuffle  # noqa: E402

IMAGE_DIR = PROJECT_ROOT / "bot" / "state" / "images"
KEEP_IMAGES = 50          # 生成画像の保持枚数（古いものから削除）
MAX_TITLE_THEME = 24      # 画像タイトルに載せる相談テーマの最大文字数

SPREAD_LABELS = {
    "one": "ワンオラクル",
    "two": "ツーカード",
    "three": "スリーカード",
    "hexagram": "ヘキサグラム",
    "celtic": "ケルト十字",
}

# 相談者が明示的に指定したときに拾うキーワード（AGENTS.md §6・user 決定「キーワード指定＋既定は舞が選ぶ」）
EXPLICIT_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("celtic", ("ケルト", "celtic", "10枚", "１０枚", "十枚")),
    ("hexagram", ("ヘキサグラム", "hexagram", "六芒", "7枚", "７枚", "七枚")),
    ("three", ("スリーカード", "three", "3枚", "３枚", "三枚")),
    ("two", ("ツーカード", "two", "2枚", "２枚", "二枚")),
    ("one", ("ワンオラクル", "one oracle", "1枚", "１枚", "一枚")),
)

# 指定がないときの目安。data/spreads.md の「スプレッド選びの目安」表をそのまま判断材料にしている。
_ONE_HINTS = ("今日", "ひとこと", "一言", "ひとつだけ", "ひと言")
_TWO_HINTS = ("どっち", "どちら", "二択", "２択", "2択", "比較", "選ぶなら", "AかB")
_CELTIC_HINTS = ("人生", "岐路", "転職", "進路", "将来", "結婚", "離婚", "独立", "起業",
                 "引っ越", "移住", "留学", "生き方", "これから先")
_HEXAGRAM_HINTS = ("恋", "好きな人", "相手", "気持ち", "付き合", "復縁", "片思い", "人間関係",
                   "友達", "友人", "上司", "同僚", "家族", "仲直り")


class TarotError(RuntimeError):
    """抽選・描画に失敗したときに送出する。"""


def choose_spread(text: str) -> tuple[str, str]:
    """相談文からスプレッドを決める。

    Returns:
        (スプレッド名, 決めた理由のラベル)
    """
    lowered = text.lower()
    for spread, keywords in EXPLICIT_KEYWORDS:
        if any(keyword.lower() in lowered for keyword in keywords):
            return spread, "相談者の指定"

    if len(text) < 40 and any(hint in text for hint in _ONE_HINTS):
        return "one", "舞の判断（ひとことの問い）"
    if any(hint in text for hint in _TWO_HINTS):
        return "two", "舞の判断（二択・対比）"
    if any(hint in text for hint in _CELTIC_HINTS):
        return "celtic", "舞の判断（人生の岐路）"
    if any(hint in text for hint in _HEXAGRAM_HINTS):
        return "hexagram", "舞の判断（恋愛・対人）"
    return "three", "舞の判断（流れの整理）"


def position_meanings(spread: str) -> dict[int, str]:
    """スプレッドの各ポジションの意味（陣形画像の凡例と同じ正本を使う）。"""
    return render_spread.POSITION_MEANINGS.get(spread, {})


def draw(spread: str, upright_only: bool = False) -> list[dict]:
    """`shuffle.draw()` で引く。抽選の正本はここではなく shuffle.py。"""
    try:
        count = shuffle.SPREAD_COUNTS[spread]
    except KeyError as exc:
        raise TarotError(f"未知のスプレッドです: {spread}") from exc
    picks = shuffle.draw(count, upright_only)
    return [
        {
            "position": position,
            "card": card,
            "orientation": orientation,
            "image": shuffle.image_path(card),
        }
        for position, (card, orientation) in enumerate(picks, 1)
    ]


def _title(spread: str, theme: str) -> str:
    label = SPREAD_LABELS.get(spread, spread)
    cleaned = " ".join(theme.split())
    if len(cleaned) > MAX_TITLE_THEME:
        cleaned = cleaned[:MAX_TITLE_THEME] + "…"
    return f"{label} — {cleaned}" if cleaned else label


def _prune_images() -> None:
    """生成画像が溜まりすぎないよう、古いものから削除する。"""
    images = sorted(IMAGE_DIR.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    for stale in images[KEEP_IMAGES:]:
        stale.unlink(missing_ok=True)


def render(cards: list[dict], spread: str, theme: str, slug: str) -> Path:
    """陣形画像を1枚に合成する。

    Misskey Bot では**枚数によらず必ずこれを通す**（AGENTS.md §6.1）。
    合成画像にはカード画像の出典表記が焼き込まれるため、1枚引きでも出典が画像単体で完結する。
    """
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = IMAGE_DIR / f"{slug}.png"
    try:
        render_spread.render(cards, spread, _title(spread, theme), out_path, PROJECT_ROOT)
    except RuntimeError as exc:
        # _font() が日本語フォントを見つけられなかったときの典型的な失敗
        raise TarotError(
            f"陣形画像の生成に失敗しました: {exc}\n"
            "日本語フォントが必要です。Linux では fonts-noto-cjk を導入するか、"
            "TAROT_SPREAD_FONT に .ttf/.ttc の絶対パスを指定してください。"
        ) from exc
    _prune_images()
    return out_path


def summary_line(cards: list[dict]) -> str:
    """ログ・記録用の1行サマリ。"""
    return " / ".join(f"{c['position']}.{c['card']}（{c['orientation']}）" for c in cards)
