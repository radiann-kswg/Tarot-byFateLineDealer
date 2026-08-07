"""正本（SSOT）を実行時に読み込む — Bot にとっての「入口」。

AGENTS.md §5 の編集ルールに従い、このモジュールは正本の内容を**一切ハードコピーしない**。
舞の口調も、占いの原則も、定型文も、すべてリポジトリのファイルから読み出す。
`roleplay.instructions.md` を1行書き換えれば Bot の応答も変わる ── それが正しい状態。

このモジュールが読むもの:
  - roleplay.instructions.md … 正本①（キャラクター設定）
  - AGENTS.md                … 正本②（運用ルール・占いの原則・§6 の定型文）
  - procedures/reading-procedure.md … 占い手順
  - data/spreads.md          … スプレッド資料
  - data/tarot-deck.md       … 引いたカードの行だけを抽出して使う
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re

from . import PROJECT_ROOT

# システムプロンプトの安定部を構成する正本（この順で連結する）。
# ここに可変値（日時・ユーザー名・UUID等）を混ぜるとプロンプトキャッシュが毎回失効するので注意。
SYSTEM_SOURCES: tuple[tuple[str, str], ...] = (
    ("正本①：錦野舞のキャラクター設定（roleplay.instructions.md）", "roleplay.instructions.md"),
    ("正本②：執務室の運用ルールと占いの原則（AGENTS.md）", "AGENTS.md"),
    ("占いの手順（procedures/reading-procedure.md）", "procedures/reading-procedure.md"),
    ("スプレッド資料（data/spreads.md）", "data/spreads.md"),
)

DECK_FILE = "data/tarot-deck.md"
IMAGERY_FILE = "data/card-imagery.md"
RULES_FILE = "AGENTS.md"

# data/card-imagery.md の「### 愚者 (The Fool)」形式の見出し
_IMAGERY_HEADING = re.compile(r"^###\s+(?P<name>.+?)\s+\(.+\)\s*$")

# AGENTS.md §6.3 の定型文を拾うための見出し。`#### テンプレート：<id>` の直後の
# フェンス付きコードブロックが本文。
_TEMPLATE_HEADING = re.compile(r"^#{2,6}\s*テンプレート：\s*(?P<id>[A-Za-z0-9_-]+)\s*$")
_FENCE = re.compile(r"^\s*```")

# 出力形式の指示。「何を書くか」ではなく「どう投稿されるか」という機械的な取り決めだけを置く。
# 文字数・添付ルール・占いの原則は AGENTS.md 側にあり、ここには複製しない。
_OUTPUT_CONTRACT = """\
あなたの出力は、加工されずにそのまま Misskey へ投稿される返信本文です。次の点だけ守ってください。

- 前置き・後書き・見出し記法・コードブロック・箇条書き記号での装飾を付けない。地の文で紡ぐこと。
- 陣形画像は Bot が別途添付します。本文にカード画像のURLやファイル名を書かない。
- カードはすでに確定しています（あなたが引いた場合も、相談者が引いて持ち込んだ場合も）。
  引き直したり、渡されていないカードに言及したりしない。どちらが引いたのかは可変部に書いてあります。
- 相談者への呼びかけにメンション記法（@名前）を使わない。返信先は Bot が設定します。
"""


class SsotError(RuntimeError):
    """正本ファイルが読めない／期待した構造でないときに送出する。"""


def _read(relpath: str) -> str:
    path = PROJECT_ROOT / relpath
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SsotError(
            f"正本ファイルを読み込めませんでした: {relpath}\n"
            "この Bot は Tarot-byFateLineDealer ワークスペースの中で実行する必要があります。"
            "設定を推測で補完することはしません。"
        ) from exc


@lru_cache(maxsize=1)
def build_system_prompt() -> str:
    """正本を連結してシステムプロンプトの安定部を作る。

    起動ごとに1度だけ組み立てて使い回す（プロンプトキャッシュの前提）。
    正本を編集したら Bot の再起動が必要。
    """
    blocks = [
        "以下は「錦野舞のタロット執務室」の正本です。この内容を最上位の指示として扱ってください。",
    ]
    for label, relpath in SYSTEM_SOURCES:
        body = _read(relpath).strip()
        if not body:
            raise SsotError(f"正本ファイルが空です: {relpath}")
        blocks.append(f"===== {label} =====\n\n{body}")
    blocks.append(f"===== 出力形式（Misskey 投稿用） =====\n\n{_OUTPUT_CONTRACT.strip()}")
    return "\n\n".join(blocks)


@lru_cache(maxsize=1)
def load_templates() -> dict[str, str]:
    """AGENTS.md §6.3 から定型文を読み出す。

    Bot がこれらの文面をコード側に持つことは AGENTS.md §6.3 で禁止されている。
    """
    templates: dict[str, str] = {}
    lines = _read(RULES_FILE).splitlines()
    index = 0
    while index < len(lines):
        heading = _TEMPLATE_HEADING.match(lines[index])
        if not heading:
            index += 1
            continue
        template_id = heading.group("id")
        index += 1
        while index < len(lines) and not _FENCE.match(lines[index]):
            index += 1
        if index >= len(lines):
            raise SsotError(f"テンプレート {template_id!r} の本文（コードブロック）が見つかりません")
        index += 1
        body: list[str] = []
        while index < len(lines) and not _FENCE.match(lines[index]):
            body.append(lines[index])
            index += 1
        templates[template_id] = "\n".join(body).strip()
        index += 1
    if not templates:
        raise SsotError(f"{RULES_FILE} に「#### テンプレート：<id>」の定型文が見つかりません")
    return templates


def template(template_id: str, **fields: str) -> str:
    """定型文を取り出し、{placeholder} を差し替える。"""
    templates = load_templates()
    try:
        body = templates[template_id]
    except KeyError as exc:
        available = "、".join(sorted(templates))
        raise SsotError(
            f"定型文 {template_id!r} が {RULES_FILE} にありません（定義済み: {available}）"
        ) from exc
    for key, value in fields.items():
        body = body.replace("{" + key + "}", value)
    return body


@lru_cache(maxsize=1)
def deck_index() -> dict[str, tuple[str, str]]:
    """data/tarot-deck.md の表を「カード名 -> (正位置キーワード, 逆位置キーワード)」に畳む。

    大アルカナは `| 0 | 愚者 (The Fool) | 正 | 逆 |`、小アルカナは `| ワンドのエース | 正 | 逆 |` と
    列数が違うので、いずれも末尾3セルを (名前, 正, 逆) として扱う。
    """
    index: dict[str, tuple[str, str]] = {}
    for line in _read(DECK_FILE).splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        if set("".join(cells)) <= set("-: "):      # 罫線行
            continue
        name = cells[-3].split(" (")[0].strip()    # 「愚者 (The Fool)」→「愚者」
        if not name or name in ("カード", "カード名"):   # 見出し行
            continue
        index[name] = (cells[-2], cells[-1])
    if not index:
        raise SsotError(f"{DECK_FILE} からカードのキーワードを読み取れませんでした")
    return index


def deck_entries(cards: list[dict]) -> str:
    """引いたカードの該当行だけを、読み解き用の手がかりとして整形する。

    デッキ全78枚をプロンプトに載せず、引いたカードの行だけを渡す
    （システムプロンプト側の安定部を小さく保ち、キャッシュを効かせるため）。
    """
    index = deck_index()
    lines: list[str] = []
    for card in cards:
        name = card["card"]
        orientation = card["orientation"]
        try:
            upright, reversed_ = index[name]
        except KeyError as exc:
            raise SsotError(f"{DECK_FILE} に「{name}」の行が見つかりません") from exc
        applied = "正位置" if orientation.startswith("正") else "逆位置"
        lines.append(
            f"{card['position']}. {name}（{orientation}）\n"
            f"   正位置キーワード：{upright}\n"
            f"   逆位置キーワード：{reversed_}\n"
            f"   → 今回適用するのは「{applied}」の方"
        )
    return "\n".join(lines)


@lru_cache(maxsize=1)
def imagery_index() -> dict[str, str]:
    """data/card-imagery.md を「カード名 -> 図像資料の本文」に畳む。

    見出し `### 愚者 (The Fool)` から次の見出しまでを、そのカードの資料とみなす。
    """
    index: dict[str, str] = {}
    name: str | None = None
    body: list[str] = []
    for line in _read(IMAGERY_FILE).splitlines():
        heading = _IMAGERY_HEADING.match(line)
        if heading:
            if name:
                index[name] = "\n".join(body).strip()
            name = heading.group("name").strip()
            body = []
            continue
        if line.startswith("## "):      # 章の切れ目でいったん閉じる
            if name:
                index[name] = "\n".join(body).strip()
            name = None
            body = []
            continue
        if name is not None:
            body.append(line)
    if name:
        index[name] = "\n".join(body).strip()

    index = {k: v for k, v in index.items() if v}
    if not index:
        raise SsotError(f"{IMAGERY_FILE} からカードの図像資料を読み取れませんでした")
    return index


def imagery_entries(cards: list[dict]) -> str:
    """取り上げるカードの図像資料だけを抜き出す。

    デッキ全体をプロンプトへ載せない理由は deck_entries() と同じ。
    資料が無いカードは黙って飛ばさず、その旨を明記して渡す
    （舞に「Waite はそこまで書いていない」と正直に言わせるため・AGENTS.md §6.6）。
    """
    index = imagery_index()
    lines: list[str] = []
    for card in cards:
        name = card["card"]
        entry = index.get(name)
        if entry:
            lines.append(f"{card['position']}. {name}（{card['orientation']}）\n{entry}")
        else:
            lines.append(
                f"{card['position']}. {name}（{card['orientation']}）\n"
                f"- **資料なし**：{IMAGERY_FILE} にこのカードの項目がありません。"
                "図像の細部を推測で語らず、資料が無いことを正直に伝えてください。"
            )
    return "\n\n".join(lines)
