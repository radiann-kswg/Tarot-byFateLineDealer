"""実行時状態の永続化（AGENTS.md §6.5）。

プロセスが落ちて再起動しても、同じメンションに二度返信しないための記録。
`bot/state/` は .gitignore 済み。**このファイルを消すと過去の通知を再処理する可能性がある。**
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import os
import re
import tempfile

from . import PROJECT_ROOT

READINGS_DIR = PROJECT_ROOT / "readings"
MAX_REPLIED_IDS = 500     # 応答済み通知IDの保持数（古いものから捨てる）
# ファイル名に残してよい文字: 英数字・かな・カナ・漢字・アンダースコア・ハイフン
_UNSAFE_SLUG = re.compile(r"[^0-9A-Za-z぀-ヿ一-鿿_-]+")


def _now() -> float:
    return datetime.now(timezone.utc).timestamp()


def slugify(text: str, limit: int = 24) -> str:
    """ファイル名に使える短い識別子を作る。"""
    cleaned = _UNSAFE_SLUG.sub("_", " ".join(text.split())).strip("_")
    return (cleaned[:limit] or "reading")


class State:
    """JSON 1ファイルで持つ軽量な状態。書き込みは原子的に行う。"""

    def __init__(self, path: Path):
        self.path = path
        self._data = self._load()

    def _load(self) -> dict:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
        raw.setdefault("last_notification_id", None)
        raw.setdefault("replied_ids", [])
        raw.setdefault("cooldowns", {})
        raw.setdefault("last_daily_date", None)
        return raw

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # 書き込み途中で落ちても壊れたJSONを残さないよう、一時ファイル経由で差し替える
        handle, tmp_name = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as fp:
                json.dump(self._data, fp, ensure_ascii=False, indent=2)
            os.replace(tmp_name, self.path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise

    # --- 通知の重複防止 -----------------------------------------------------

    @property
    def last_notification_id(self) -> str | None:
        return self._data["last_notification_id"]

    @last_notification_id.setter
    def last_notification_id(self, value: str | None) -> None:
        self._data["last_notification_id"] = value

    def already_replied(self, notification_id: str) -> bool:
        return notification_id in self._data["replied_ids"]

    def mark_replied(self, notification_id: str) -> None:
        replied = self._data["replied_ids"]
        if notification_id in replied:
            return
        replied.append(notification_id)
        del replied[:-MAX_REPLIED_IDS]

    # --- 連投のクールダウン -------------------------------------------------

    def cooling_down(self, user_id: str, seconds: int) -> bool:
        if seconds <= 0:
            return False
        last = self._data["cooldowns"].get(user_id)
        return last is not None and (_now() - last) < seconds

    def touch_user(self, user_id: str, seconds: int) -> None:
        cooldowns = self._data["cooldowns"]
        cooldowns[user_id] = _now()
        # 期限切れの記録は捨てる（無限に増やさない）
        horizon = _now() - max(seconds, 1) * 10
        self._data["cooldowns"] = {k: v for k, v in cooldowns.items() if v >= horizon}

    # --- 「今日の一枚」の二重投稿防止 ---------------------------------------

    def daily_already_posted(self, date_key: str) -> bool:
        return self._data["last_daily_date"] == date_key

    def mark_daily_posted(self, date_key: str) -> None:
        self._data["last_daily_date"] = date_key


def save_reading(theme: str, spread_label: str, cards_summary: str, body: str) -> Path:
    """占い結果を readings/ に日付つきで保存する（AGENTS.md §3・手順書 §6）。"""
    READINGS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d")
    path = READINGS_DIR / f"{stamp}_{slugify(theme)}.md"
    counter = 2
    while path.exists():
        path = READINGS_DIR / f"{stamp}_{slugify(theme)}_{counter}.md"
        counter += 1
    path.write_text(
        f"# {theme}\n\n"
        f"- 日付：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"- スプレッド：{spread_label}\n"
        f"- 引いたカード：{cards_summary}\n\n"
        f"---\n\n{body}\n",
        encoding="utf-8",
    )
    return path
