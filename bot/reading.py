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


def generate(config: Config, theme: str, spread: str, reason: str, cards: list[dict],
             sensitive: bool) -> Reading:
    """読み解き文を生成する。"""
    client = anthropic.Anthropic(api_key=config.anthropic_api_key)
    user_message = build_user_message(theme, spread, reason, cards, sensitive)

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
