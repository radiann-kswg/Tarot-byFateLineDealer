"""カード絵文字の解析とモード判定（AGENTS.md §4-7・§6.6）。

相談者が本文に貼った `:tarot_m00:` `:tarot_w01_r:` を、78枚のカードへ復元する。
絵文字名とカードの対応の正本は `procedures/shuffle.py`（`build_emoji_name()` が
`procedures/build_misskey_emoji.py` と同じ規則で名前を組み立てる）。ここでは複製しない。

**このモジュールはカードを引かない。** 持ち込まれた並びをそのまま返すだけ。
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import re

# tarot.py が procedures/ を sys.path へ通しているので、その後に import する
from .tarot import shuffle                                          # noqa: F401
import build_misskey_emoji                                          # noqa: E402

# 絵文字名の規則の**正本は procedures/build_misskey_emoji.py**。ここでは複製しない。
NAME_PREFIX = build_misskey_emoji.NAME_PREFIX
REVERSED_SUFFIX = build_misskey_emoji.REVERSED_SUFFIX
build_emoji_name = build_misskey_emoji.emoji_name

# Misskey のカスタム絵文字記法。リモート絵文字は `:name@example.com:`、
# ローカルを明示するときは `:name@.:` になるので、ホスト部を任意で受ける。
_EMOJI = re.compile(r":([a-zA-Z0-9_+-]+?)(@[a-zA-Z0-9_.-]+)?:")

# タロットの絵文字らしいが 78 枚のどれにも当たらないもの（`emoji-unknown` の判定に使う）
_LOOKS_LIKE_TAROT = re.compile(rf":{NAME_PREFIX}[a-zA-Z0-9_]*(@[a-zA-Z0-9_.-]+)?:")

# --- モード判定のキーワード（AGENTS.md §6.6 の表に対応） -------------------------
#
# 判定は「強い持ち込み → 図像 → 意味 → 弱い持ち込み → 既定」の順。
# 「自分で引いた」と明言している相談者に、カード解説だけを返してしまわないよう、
# **引いた事実の申告を最優先**にする。「引いてみたけど、この展開どう思うか教えて」は
# 読み解きの依頼であって、解説の依頼ではない。
_BROUGHT_STRONG_HINTS = (
    "引いてみた", "引いたんだけど", "引いたけど", "引いたの", "引きました",
    "自分で引", "自分が引", "出たんだけど", "並べてみた", "この展開", "この並び",
)
# 図像の語は「絵そのもの」を指すものだけに絞る。「背景」「象徴」は
# 相談文（転職の背景／象徴的な並び）にも出るため入れない。
_IMAGERY_HINTS = (
    "図像", "絵柄", "絵は", "絵には", "描かれ", "描写", "いわれ", "由来",
    "元ネタ", "モチーフ", "シンボル", "何が描", "どんな絵", "どういう絵", "成り立ち",
)
_MEANING_HINTS = (
    "意味", "どういうカード", "どんなカード", "どういう札", "どんな札",
    "解説", "教えて", "説明", "示すの", "表すの", "何を指す",
)
_BROUGHT_WEAK_HINTS = (
    "展開", "並び", "どう思う", "どう読む", "読んで", "見て", "見立て", "占って",
)

# 相談者が「舞が引いて」と望んだとき（AGENTS.md §4-7 の但し書き）。
# 「引いてみたんだけど」のような**相談者自身が引いた**言い方と衝突しないよう、
# ここには「舞に引いてもらう」意図がはっきり読み取れる言い回しだけを置く。
# 素の「引いて」は入れないこと（"引いてみた" に誤爆する）。
_DRAW_FOR_ME_HINTS = (
    "舞が引", "舞に引", "引いてほしい", "引いて欲しい", "引いてもらえ", "引いてくれ",
    "引いてください", "引いて下さい", "占ってほしい", "占って欲しい", "占ってくれ",
    "占ってもらえ", "占ってください", "占って下さい",
)

# **位置**の役割に言及しているか（スプレッド確認をスキップしてよいかの判断・§6.6-4）。
# 「過去」「気持ち」のような語は普通の相談文にも頻出するので入れない。
# ここに入れてよいのは「並びのどこを指しているか」が読み取れる表現だけ。
_ROLE_HINTS = (
    "枚目", "番目", "左から", "右から", "順に", "順番", "上から",
    "①", "②", "③", "④", "⑤",
)

# 枚数から推定できる型（AGENTS.md §6.6-2）。枚数の正本は shuffle.SPREAD_COUNTS。
_COUNT_TO_SPREAD = {count: spread for spread, count in shuffle.SPREAD_COUNTS.items()}

# 型が決まらないときに使う「並び」レイアウト（procedures/render_spread.py の line）
LINE_SPREAD = "line"


class EmojiError(RuntimeError):
    """絵文字の解析に失敗したときに送出する。"""


@dataclass(frozen=True)
class Parsed:
    """メンション1件から読み取れたもの。

    Attributes:
        cards: 持ち込まれたカード（`tarot.draw()` と同じ形の辞書のリスト）。
        mode: "meaning" / "brought" / "imagery" のいずれか。カードが無ければ None。
        unknown: タロットの絵文字らしいのに対応づけられなかった記法。
        wants_draw: 相談者が「舞が引いて」と望んでいるか。
    """
    cards: list[dict]
    mode: str | None
    unknown: list[str]
    wants_draw: bool

    @property
    def has_cards(self) -> bool:
        return bool(self.cards)


@lru_cache(maxsize=1)
def emoji_index() -> dict[str, tuple[str, str]]:
    """絵文字名 -> (カード名, 正位置/逆位置) の対応表を 156 件つくる。"""
    index: dict[str, tuple[str, str]] = {}
    for card in shuffle.build_deck():
        index[build_emoji_name(card, False)] = (card, "正位置")
        index[build_emoji_name(card, True)] = (card, "逆位置")
    if len(index) != 156:
        raise EmojiError(f"絵文字の対応表が156件になりません（{len(index)}件）")
    return index


def extract_cards(text: str) -> tuple[list[dict], list[str]]:
    """本文からカードを取り出す。

    同じ絵文字が複数回出てきたら、その回数ぶん並びに数える（相談者が同じ札を
    二度置くことは無いはずだが、勝手に間引くと並びがずれるので数えたまま渡す）。

    Returns:
        (カードのリスト, 対応づけられなかった絵文字記法のリスト)
    """
    index = emoji_index()
    cards: list[dict] = []
    for match in _EMOJI.finditer(text):
        name = match.group(1)
        if name not in index:
            continue
        card, orientation = index[name]
        cards.append({
            "position": len(cards) + 1,
            "card": card,
            "orientation": orientation,
            "image": shuffle.image_path(card),
        })

    matched_spans = {m.group(0) for m in _EMOJI.finditer(text) if m.group(1) in index}
    unknown = [m.group(0) for m in _LOOKS_LIKE_TAROT.finditer(text)
               if m.group(0) not in matched_spans]
    return cards, unknown


def choose_mode(text: str, card_count: int) -> str:
    """何を訊かれているかを判定する（AGENTS.md §6.6）。

    「自分で引いた」と申告している相談者を最優先で読み解きへ回す。
    「教えて」「解説」のような汎用語で解説へ落としてしまうと、
    読み解きを求めた人にカードの説明だけが返ってしまうため。
    """
    if any(hint in text for hint in _BROUGHT_STRONG_HINTS):
        return "brought"
    if any(hint in text for hint in _IMAGERY_HINTS):
        return "imagery"
    if any(hint in text for hint in _MEANING_HINTS):
        return "meaning"
    if any(hint in text for hint in _BROUGHT_WEAK_HINTS):
        return "brought"
    # 判定できないときの既定
    return "meaning" if card_count == 1 else "brought"


def wants_fresh_draw(text: str) -> bool:
    """「舞が引いて」と望まれているか（§4-7 の但し書き）。"""
    return any(hint in text for hint in _DRAW_FOR_ME_HINTS)


def mentions_roles(text: str) -> bool:
    """各位置の役割に言及しているか。あればスプレッドを尋ねずに「並び」として読む。"""
    return any(hint in text for hint in _ROLE_HINTS)


def _mentions_keyword(text: str, keyword: str) -> bool:
    """スプレッド名のキーワードが、本文で「型の指定」として使われているか。

    `EXPLICIT_KEYWORDS` には「1枚」「3枚」のような枚数表現が入っている。
    これは「1枚目は過去で……」のような**位置の説明**にも現れてしまうので、
    直後が「目」のときは型の指定とみなさない。
    """
    lowered = text.lower()
    start = 0
    needle = keyword.lower()
    while True:
        at = lowered.find(needle, start)
        if at < 0:
            return False
        after = lowered[at + len(needle): at + len(needle) + 1]
        if after != "目":
            return True
        start = at + 1


def infer_spread(text: str, card_count: int) -> tuple[str | None, str]:
    """持ち込みの並びをどう読むか決める（AGENTS.md §6.6 の1〜4）。

    Returns:
        (スプレッド名 or None, 決めた理由のラベル)
        None は「尋ねる」＝ `spread-unclear` を返すべきことを意味する。
    """
    # 循環 import を避けるため関数内で取る（tarot.py が正本）
    from .tarot import EXPLICIT_KEYWORDS, SPREAD_LABELS

    for spread, keywords in EXPLICIT_KEYWORDS:
        if any(_mentions_keyword(text, keyword) for keyword in keywords):
            if shuffle.SPREAD_COUNTS[spread] == card_count:
                return spread, "相談者の指定"
            # 型の名前と枚数が噛み合わない。どちらかへ寄せず尋ねる（AGENTS.md §4-7）。
            label = SPREAD_LABELS.get(spread, spread)
            return None, f"相談者は{label}と言ったが{card_count}枚あり噛み合わない"

    if card_count in _COUNT_TO_SPREAD:
        return _COUNT_TO_SPREAD[card_count], "枚数からの推定"
    if mentions_roles(text):
        return LINE_SPREAD, "相談者が位置の役割に触れているため並びとして読む"
    return None, "型を決めきれない"


def parse(text: str) -> Parsed:
    """メンション本文を解析する。カードが無ければ mode は None。"""
    cards, unknown = extract_cards(text)
    mode = choose_mode(text, len(cards)) if cards else None
    return Parsed(cards=cards, mode=mode, unknown=unknown,
                  wants_draw=wants_fresh_draw(text))
