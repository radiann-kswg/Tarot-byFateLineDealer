"""Bot の設定。値はすべて .env から読み、コードには埋め込まない。

秘密情報（Misskey トークン / Anthropic APIキー）はリポジトリにコミットしないこと。
`.env` は .gitignore 済み。設定項目の説明は bot/README.md を参照。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv

from . import PROJECT_ROOT

VISIBILITIES = ("public", "home", "followers")
EFFORTS = ("low", "medium", "high", "xhigh", "max")

# .env の探索順。テンプレートの bot/.env.example の隣に置く方が自然なので、両方を見る。
ENV_CANDIDATES = (".env", "bot/.env")

# 相談窓口の既定URL。公開投稿に載る文字列なので、運用前に user が必ず確認・差し替えること
# （AGENTS.md §6.3 の safety-block テンプレートの {support_url} に入る）。
DEFAULT_SUPPORT_URL = "https://www.mhlw.go.jp/mamorouyokokoro/"


class ConfigError(RuntimeError):
    """設定が足りない・不正なときに送出する。"""


@dataclass(frozen=True)
class Config:
    misskey_host: str
    misskey_token: str
    misskey_visibility: str
    anthropic_api_key: str
    anthropic_model: str
    anthropic_effort: str
    anthropic_max_tokens: int
    poll_interval: int
    user_cooldown: int
    max_body_chars: int
    support_url: str
    save_readings: bool
    state_path: Path
    request_timeout: int
    fold_reading: bool = True         # 占い結果を CW で畳むか（AGENTS.md §6.1-3）
    env_file: Path | None = None      # 実際に読み込んだ .env（--check で表示する）

    @property
    def api_base(self) -> str:
        return f"{self.misskey_host}/api"


def find_env_file(root: Path | None = None) -> Path | None:
    """ENV_CANDIDATES を順に探し、最初に見つかった .env を返す。"""
    base = root or PROJECT_ROOT
    for relpath in ENV_CANDIDATES:
        candidate = base / relpath
        if candidate.is_file():
            return candidate
    return None


def _int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} は整数で指定してください（現在: {raw!r}）") from exc
    if value < minimum:
        raise ConfigError(f"{name} は {minimum} 以上にしてください（現在: {value}）")
    return value


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    raise ConfigError(f"{name} は 1/0（true/false）で指定してください（現在: {raw!r}）")


def _choice(name: str, default: str, allowed: tuple[str, ...]) -> str:
    value = os.environ.get(name, "").strip() or default
    if value not in allowed:
        raise ConfigError(f"{name} は {' / '.join(allowed)} のいずれかにしてください（現在: {value!r}）")
    return value


def load_config(env_file: Path | None = None) -> Config:
    """.env を読み込んで Config を組み立てる。不足があれば ConfigError。"""
    loaded_from = env_file or find_env_file()
    if loaded_from is not None:
        load_dotenv(loaded_from, override=False)

    missing = [k for k in ("MISSKEY_HOST", "MISSKEY_TOKEN", "ANTHROPIC_API_KEY")
               if not os.environ.get(k, "").strip()]
    if missing:
        if loaded_from is None:
            searched = "\n".join(f"    - {PROJECT_ROOT / p}" for p in ENV_CANDIDATES)
            detail = f".env が見つかりませんでした。次の場所を探しています:\n{searched}"
        else:
            detail = (f"{loaded_from} は読み込みましたが、上の項目が空か未記載です。\n"
                      "  値が入っているか、キー名の綴りが合っているか確認してください。")
        raise ConfigError(
            "必須の環境変数が設定されていません: " + ", ".join(missing) + "\n"
            f"  {detail}\n"
            "  bot/.env.example をコピーして値を埋めてください（リポジトリ直下か bot/ のどちらでも構いません）。"
        )

    host = os.environ["MISSKEY_HOST"].strip().rstrip("/")
    if not host.startswith(("http://", "https://")):
        raise ConfigError(f"MISSKEY_HOST は http(s):// から始めてください（現在: {host!r}）")

    # フォント指定は render_spread.py が直接 os.environ から読むため、ここでは検証のみ
    font = os.environ.get("TAROT_SPREAD_FONT", "").strip()
    if font and not Path(font).is_file():
        raise ConfigError(f"TAROT_SPREAD_FONT のファイルが見つかりません: {font}")

    return Config(
        misskey_host=host,
        misskey_token=os.environ["MISSKEY_TOKEN"].strip(),
        misskey_visibility=_choice("MISSKEY_VISIBILITY", "home", VISIBILITIES),
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"].strip(),
        anthropic_model=os.environ.get("ANTHROPIC_MODEL", "").strip() or "claude-opus-4-8",
        anthropic_effort=_choice("ANTHROPIC_EFFORT", "medium", EFFORTS),
        anthropic_max_tokens=_int("ANTHROPIC_MAX_TOKENS", 8000, minimum=1024),
        poll_interval=_int("POLL_INTERVAL_SECONDS", 30, minimum=5),
        user_cooldown=_int("USER_COOLDOWN_SECONDS", 60, minimum=0),
        max_body_chars=_int("MAX_BODY_CHARS", 1200, minimum=100),
        support_url=os.environ.get("SUPPORT_RESOURCE_URL", "").strip() or DEFAULT_SUPPORT_URL,
        save_readings=_bool("SAVE_READINGS", False),
        state_path=PROJECT_ROOT / "bot" / "state" / "state.json",
        request_timeout=_int("REQUEST_TIMEOUT_SECONDS", 30, minimum=5),
        fold_reading=_bool("MISSKEY_FOLD_READING", True),
        env_file=loaded_from,
    )
