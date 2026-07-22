"""Misskey API クライアント。

エンドポイントとパラメータ名は misskey-dev/misskey の実装で確認済み:
  - i                   … 自分のアカウント情報（権限 read:account）
  - i/notifications     … limit / sinceId / includeTypes / markAsRead（権限 read:notifications）
  - drive/files/create  … multipart。file と name / comment（権限 write:drive）
  - notes/create        … text / replyId / fileIds / visibility / cw（権限 write:notes）

認証は `Authorization: Bearer <token>` を使う。Misskey は body の `i` フィールドも受け付けるが、
Bearer ヘッダが優先されるうえ、JSON と multipart で同じ書き方にできる。
"""
from __future__ import annotations

from pathlib import Path
import re

import requests

from .config import Config

# 本文の先頭に並ぶ Bot 宛メンションを取り除くための正規表現（@name / @name@host）
_MENTION = re.compile(r"@[A-Za-z0-9_]+(?:@[A-Za-z0-9._\-]+)?")

NOTIFICATION_TYPES = ["mention", "reply"]


class MisskeyError(RuntimeError):
    """Misskey API の呼び出しに失敗したときに送出する。

    Attributes:
        retryable: 時間をおけば成功しうるか（接続断・5xx・レート制限）。
    """

    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


def strip_mentions(text: str) -> str:
    """相談文から Bot 宛メンション記法を取り除く。"""
    return " ".join(_MENTION.sub(" ", text or "").split())


class Misskey:
    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {config.misskey_token}"

    def _post(self, endpoint: str, payload: dict | None = None, files: dict | None = None,
              data: dict | None = None):
        url = f"{self.config.api_base}/{endpoint}"
        try:
            if files is not None:
                response = self.session.post(url, data=data or {}, files=files,
                                             timeout=self.config.request_timeout)
            else:
                response = self.session.post(url, json=payload or {},
                                             timeout=self.config.request_timeout)
        except requests.Timeout as exc:
            raise MisskeyError(f"{endpoint} がタイムアウトしました", retryable=True) from exc
        except requests.RequestException as exc:
            raise MisskeyError(f"{endpoint} へ接続できませんでした: {exc}", retryable=True) from exc

        if response.status_code == 204 or not response.content:
            return None
        if not response.ok:
            detail = response.text[:400]
            raise MisskeyError(
                f"{endpoint} が {response.status_code} を返しました: {detail}",
                retryable=response.status_code >= 500 or response.status_code == 429,
            )
        try:
            return response.json()
        except ValueError as exc:
            raise MisskeyError(f"{endpoint} の応答が JSON ではありません: {response.text[:200]}") from exc

    # --- 疎通確認 -----------------------------------------------------------

    def me(self) -> dict:
        """自分のアカウント情報。トークンの権限確認も兼ねる（--check）。"""
        account = self._post("i")
        if not isinstance(account, dict):
            raise MisskeyError("i の応答が想定と違います")
        return account

    # --- 受信 ---------------------------------------------------------------

    def notifications(self, since_id: str | None, limit: int = 20,
                      mark_as_read: bool = True) -> list[dict]:
        """メンション／リプライの通知を古い順に返す。

        `mark_as_read` は dry-run では False にする（既読化はサーバ側を書き換える副作用のため）。
        """
        payload: dict = {
            "limit": limit,
            "includeTypes": NOTIFICATION_TYPES,
            "markAsRead": mark_as_read,
        }
        if since_id:
            payload["sinceId"] = since_id
        result = self._post("i/notifications", payload)
        if not isinstance(result, list):
            raise MisskeyError("i/notifications の応答が配列ではありません")
        # Misskey の ID は時系列に並ぶので、昇順に直せば受信順に処理できる
        return sorted((n for n in result if isinstance(n, dict) and n.get("id")),
                      key=lambda n: n["id"])

    # --- 送信 ---------------------------------------------------------------

    def upload(self, path: Path, comment: str | None = None) -> str:
        """画像をドライブへアップロードし、fileId を返す。"""
        with path.open("rb") as handle:
            data = {"name": path.name}
            if comment:
                data["comment"] = comment[:512]
            result = self._post("drive/files/create", files={"file": (path.name, handle, "image/png")},
                                data=data)
        if not isinstance(result, dict) or not result.get("id"):
            raise MisskeyError(f"drive/files/create が fileId を返しませんでした: {result!r}")
        return result["id"]

    def create_note(self, text: str, reply_id: str | None = None,
                    file_ids: list[str] | None = None, cw: str | None = None) -> dict:
        """ノートを投稿する。公開範囲は設定（既定 home）に従う。"""
        payload: dict = {"text": text, "visibility": self.config.misskey_visibility}
        if reply_id:
            payload["replyId"] = reply_id
        if file_ids:
            payload["fileIds"] = file_ids
        if cw:
            payload["cw"] = cw[:100]
        result = self._post("notes/create", payload)
        if not isinstance(result, dict):
            raise MisskeyError(f"notes/create の応答が想定と違います: {result!r}")
        return result.get("createdNote", result)
