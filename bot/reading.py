"""読み解き文の生成 — Claude Messages API。

**カードは渡すだけで、引かせない**（AGENTS.md §4-1・§4-6）。抽選は bot/tarot.py が済ませている。

システムプロンプトの安定部（正本の連結）は毎回同じバイト列なので、`cache_control` を置いて
プロンプトキャッシュに載せる。可変部（相談文・引いたカード）はユーザーメッセージ側に置く。
"""
from __future__ import annotations

from dataclasses import dataclass

import anthropic

from . import ssot
from .config import Config
from .tarot import SPREAD_LABELS, position_meanings


class ReadingError(RuntimeError):
    """読み解きの生成に失敗したときに送出する。

    Attributes:
        retryable: 時間をおけば成功しうるか（レート制限・接続断・5xx）。
    """

    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class Reading:
    text: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int

    @property
    def cache_note(self) -> str:
        return (f"in={self.input_tokens} out={self.output_tokens} "
                f"cache_read={self.cache_read_tokens} cache_write={self.cache_write_tokens}")


def build_user_message(theme: str, spread: str, reason: str, cards: list[dict],
                       sensitive: bool) -> str:
    """可変部（キャッシュ対象外）を組み立てる。"""
    label = SPREAD_LABELS.get(spread, spread)
    meanings = position_meanings(spread)
    if meanings:
        positions = "\n".join(f"  {pos}. {meaning}" for pos, meaning in sorted(meanings.items()))
        position_block = f"各ポジションの意味：\n{positions}"
    else:
        position_block = (
            "各ポジションの意味：data/spreads.md のとおり、並びの意味は問いに応じてあなたが選ぶ。"
            "どの型（時系列／対比／選択／助言）で読むかを本文の中で自然に示すこと。"
        )

    sections = [
        f"### 相談\n{theme}",
        f"### 今回のスプレッド\n{label}（{spread}・{len(cards)}枚）— 決めた理由：{reason}\n{position_block}",
        "### 引いたカード（抽選済み・変更不可）\n"
        "以下は `shuffle.py` が乱数で引いた結果です。この並びのまま読み解いてください。\n\n"
        + ssot.deck_entries(cards),
    ]
    if sensitive:
        sections.append(
            "### 注意\n"
            "この相談は医療・法律・生死・金融といった重大な決断に触れています。"
            "AGENTS.md §4-3 に従い、§6.3 の expert-note の趣旨にあたる一文を必ず本文に添えてください。"
        )
    return "\n\n".join(sections)


def _expert_note_block() -> str:
    return (
        "### 注意\n"
        "この相談は医療・法律・生死・金融といった重大な決断に触れています。"
        "AGENTS.md §4-3 に従い、§6.3 の expert-note の趣旨にあたる一文を必ず本文に添えてください。"
    )


def build_brought_message(theme: str, spread: str, reason: str, cards: list[dict],
                          sensitive: bool) -> str:
    """持ち込みの読み解き（AGENTS.md §4-7・§6.6 の `brought`）。

    **舞が引いたことにしない。** 相談者が自分で引いた並びであることを明示して渡す。
    """
    label = SPREAD_LABELS.get(spread, spread)
    meanings = position_meanings(spread)
    if meanings:
        positions = "\n".join(f"  {pos}. {meaning}" for pos, meaning in sorted(meanings.items()))
        position_block = f"各ポジションの意味：\n{positions}"
    elif spread == "line":
        position_block = (
            "各ポジションの意味：型は決まっていません。左から順に並んだものとして読み、"
            "どの流れで読んだかを本文の中で自然に示してください。"
        )
    else:
        position_block = (
            "各ポジションの意味：data/spreads.md のとおり、並びの意味は問いに応じてあなたが選ぶ。"
            "どの型（時系列／対比／選択／助言）で読むかを本文の中で自然に示すこと。"
        )

    sections = [
        f"### 相談\n{theme}",
        "### このカードは相談者が自分で引いたものです\n"
        "AGENTS.md §4-7 に従い、**あなたは引き直しません**。この並びをそのまま読んでください。\n"
        "「私が引いたところ」のように、あなたが引いたかのような書き方をしないこと。"
        "「あなたが引いたこの並び」として語ってください。",
        f"### 並びの読み方\n{label}（{spread}・{len(cards)}枚）— そう判断した理由：{reason}\n{position_block}",
        "### 持ち込まれたカード（変更不可）\n" + ssot.deck_entries(cards),
    ]
    if sensitive:
        sections.append(_expert_note_block())
    return "\n\n".join(sections)


def build_meaning_message(theme: str, cards: list[dict], sensitive: bool) -> str:
    """カードの意味の解説（AGENTS.md §6.6 の `meaning`）。占いではない。"""
    sections = [
        f"### 相談者の言葉\n{theme}",
        "### これは占いではなく、カードの解説の求めです\n"
        "相談者は自分の運勢を占ってほしいのではなく、このカードがどういう札なのかを知りたがっています。\n"
        "- そのカードが何を表すのかを、正位置・逆位置の両方に触れながら舞の言葉で語ってください。\n"
        "- 相談者個人の状況や未来を読み解かないこと。カードそのものの話に留めること。\n"
        "- 引き直しも、渡されていないカードへの言及もしないこと。",
        "### 取り上げるカード\n" + ssot.deck_entries(cards),
    ]
    if sensitive:
        sections.append(_expert_note_block())
    return "\n\n".join(sections)


def build_imagery_message(theme: str, cards: list[dict], sensitive: bool) -> str:
    """図像の解説（AGENTS.md §6.6 の `imagery`）。"""
    sections = [
        f"### 相談者の言葉\n{theme}",
        "### これは絵柄そのものについての問いです\n"
        "相談者は、そのカードに何が描かれているのか、その象徴が何を指すのか、"
        "どんな由来があるのかを知りたがっています。\n"
        "- 下の資料に**書かれていることだけ**を根拠にしてください。\n"
        "- 資料に無い細部を足さないこと。よく知られた描写でも、"
        "Waite の原著に無いものはこの資料にも載っていません。\n"
        "- 分からないことは「Waite はそこまで書いていない」と正直に言ってください。"
        "それは誠実さであって、力不足ではありません。\n"
        "- 占いのキーワード（正逆の意味）を語る場ではありません。訊かれていれば触れる程度に。",
        "### カード図像資料（data/card-imagery.md より該当箇所）\n" + ssot.imagery_entries(cards),
    ]
    if sensitive:
        sections.append(_expert_note_block())
    return "\n\n".join(sections)


def _call(config: Config, user_message: str) -> Reading:
    """システムプロンプト（正本の連結）＋可変部で1回だけ推論する。"""
    client = anthropic.Anthropic(api_key=config.anthropic_api_key)

    try:
        response = client.messages.create(
            model=config.anthropic_model,
            max_tokens=config.anthropic_max_tokens,
            # Opus 4.8 は thinking を省略すると思考オフになるため明示する
            thinking={"type": "adaptive"},
            output_config={"effort": config.anthropic_effort},
            system=[{
                "type": "text",
                "text": ssot.build_system_prompt(),
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": user_message}],
        )
    except anthropic.AuthenticationError as exc:
        raise ReadingError(f"Anthropic の認証に失敗しました（APIキーを確認してください）: {exc}") from exc
    except anthropic.RateLimitError as exc:
        raise ReadingError(f"Anthropic のレート制限に達しました: {exc}", retryable=True) from exc
    except anthropic.APIStatusError as exc:
        raise ReadingError(f"Anthropic API エラー {exc.status_code}: {exc}",
                           retryable=exc.status_code >= 500) from exc
    except anthropic.APIConnectionError as exc:
        raise ReadingError(f"Anthropic へ接続できませんでした: {exc}", retryable=True) from exc

    # content を読む前に必ず stop_reason を確認する
    if response.stop_reason == "refusal":
        details = getattr(response, "stop_details", None)
        category = getattr(details, "category", None) if details else None
        raise ReadingError(f"安全性の理由で応答が拒否されました（category={category}）")

    text = "\n".join(block.text for block in response.content if block.type == "text").strip()
    if not text:
        raise ReadingError(f"本文が空でした（stop_reason={response.stop_reason}）")

    usage = response.usage
    return Reading(
        text=text,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
        cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
    )


def generate(config: Config, theme: str, spread: str, reason: str, cards: list[dict],
             sensitive: bool) -> Reading:
    """舞が引いた結果の読み解き文を生成する。"""
    return _call(config, build_user_message(theme, spread, reason, cards, sensitive))


def generate_brought(config: Config, theme: str, spread: str, reason: str,
                     cards: list[dict], sensitive: bool) -> Reading:
    """相談者が持ち込んだ並びの読み解き文を生成する（AGENTS.md §4-7）。"""
    return _call(config, build_brought_message(theme, spread, reason, cards, sensitive))


def generate_meaning(config: Config, theme: str, cards: list[dict],
                     sensitive: bool) -> Reading:
    """カードの意味の解説を生成する（占いではない・AGENTS.md §6.6）。"""
    return _call(config, build_meaning_message(theme, cards, sensitive))


def generate_imagery(config: Config, theme: str, cards: list[dict],
                     sensitive: bool) -> Reading:
    """カードの図像の解説を生成する（AGENTS.md §6.6）。"""
    return _call(config, build_imagery_message(theme, cards, sensitive))


def check(config: Config) -> str:
    """--check 用の疎通確認。読み解きは行わず、モデルが引けることだけ見る。"""
    client = anthropic.Anthropic(api_key=config.anthropic_api_key)
    try:
        model = client.models.retrieve(config.anthropic_model)
    except anthropic.NotFoundError as exc:
        raise ReadingError(f"モデル {config.anthropic_model!r} が見つかりません: {exc}") from exc
    except anthropic.AuthenticationError as exc:
        raise ReadingError(f"Anthropic の認証に失敗しました: {exc}") from exc
    except anthropic.APIStatusError as exc:
        raise ReadingError(f"Anthropic API エラー {exc.status_code}: {exc}") from exc
    except anthropic.APIConnectionError as exc:
        raise ReadingError(f"Anthropic へ接続できませんでした: {exc}", retryable=True) from exc
    return getattr(model, "display_name", None) or model.id
