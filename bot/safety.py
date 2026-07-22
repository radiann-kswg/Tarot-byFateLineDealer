"""相談内容のスクリーニング（AGENTS.md §6.2）。

対面と違って相手の状態が読めないぶん、**迷ったら占わない側に倒す**。
判定ロジックだけをここに置き、**応答の文面は持たない**（文面の正本は AGENTS.md §6.3）。

未公開設定の要求はキーワードで機械判定すると誤検知が大きいため、ここでは扱わない。
システムプロンプトに正本②（AGENTS.md §4-4）が入っているので、Claude 側の判断に委ねる。
"""
from __future__ import annotations

from dataclasses import dataclass

# 自傷・他害・生命の危険をうかがわせる表現。
# 粗い網であることを承知のうえで、取りこぼしより誤検知を選ぶ（占わない側に倒す）。
# 「死神」「塔」などのカード名や「死ぬほど嬉しい」に反応しないよう、語句は具体的に絞ってある。
SELF_HARM_PATTERNS: tuple[str, ...] = (
    "死にたい", "死のうと", "死んでしまいたい", "消えてしまいたい", "消えたい",
    "いなくなりたい", "生きていたくない", "生きるのがつらい", "生きるのが辛い",
    "自殺", "自傷", "リストカット", "リスカ", "首を吊", "飛び降り", "遺書",
    "殺したい", "殺してやる", "刺したい",
)

# 重大な決断に関わる語。占いは行うが、専門家相談を促す一文を必ず添える（AGENTS.md §4-3）。
SENSITIVE_PATTERNS: tuple[str, ...] = (
    # 医療
    "病気", "疾患", "診断", "手術", "入院", "がん", "癌", "腫瘍", "余命", "薬を", "服薬",
    "うつ病", "精神科", "心療内科", "検査結果", "妊娠", "不妊", "中絶",
    # 法律
    "訴訟", "裁判", "弁護士", "告訴", "示談", "相続", "遺産", "離婚調停", "慰謝料",
    # 金融
    "借金", "債務", "破産", "投資", "株を", "仮想通貨", "暗号資産", "FX", "ローン", "返済",
    # 生死
    "余命", "看取", "延命",
)

# ロールプレイの明示的な中止指示（AGENTS.md §2・§4-5）。
ROLEPLAY_OFF_PATTERNS: tuple[str, ...] = (
    "ロールプレイをやめ", "ロールプレイを止め", "ロールプレイ終了", "ロールプレイをやめて",
    "なりきりをやめ", "キャラをやめ", "キャラ設定をやめ", "素に戻っ", "通常モード",
)


@dataclass(frozen=True)
class Verdict:
    """スクリーニング結果。

    Attributes:
        action:   "block"（占わない） / "roleplay_off"（通常モードへ） / "read"（占う）
        template: action が "read" 以外のときに使う AGENTS.md §6.3 の定型文ID
        sensitive: 重大な決断に触れているか（占うが専門家相談の一文を添える）
        matched:  判定の根拠になった語（ログ用）
    """
    action: str
    template: str | None = None
    sensitive: bool = False
    matched: str | None = None


def _first_match(text: str, patterns: tuple[str, ...]) -> str | None:
    for pattern in patterns:
        if pattern in text:
            return pattern
    return None


def screen(text: str) -> Verdict:
    """相談文を判定する。判定順は AGENTS.md §6.2 の表と同じ。"""
    harm = _first_match(text, SELF_HARM_PATTERNS)
    if harm:
        return Verdict(action="block", template="safety-block", matched=harm)

    stop = _first_match(text, ROLEPLAY_OFF_PATTERNS)
    if stop:
        return Verdict(action="roleplay_off", template="roleplay-off", matched=stop)

    sensitive = _first_match(text, SENSITIVE_PATTERNS)
    return Verdict(action="read", sensitive=sensitive is not None, matched=sensitive)
