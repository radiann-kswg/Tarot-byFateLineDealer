"""「今日の一枚」定期投稿（フェーズ3）。

常駐せず1回で終わるので、systemd timer / タスクスケジューラ / cron から呼ぶ。

    py -m bot.daily --dry-run     投稿せず内容を確認（既定）
    py -m bot.daily --live        実際に投稿する
    py -m bot.daily --live --force  同じ日に二度目でも投稿する
"""
from __future__ import annotations

import argparse
import logging
from datetime import datetime

from . import state as state_mod
from .config import ConfigError, load_config
from .main import perform_reading, setup_logging, _publish, _reading_cw
from .misskey import Misskey, MisskeyError
from .reading import ReadingError
from .ssot import SsotError
from .tarot import TarotError

log = logging.getLogger("tarot-mai.daily")

# 定期投稿は1枚引きに固定する（data/spreads.md「今日の一言、迷いをひとつ晴らす」→ ワンオラクル）
DAILY_SPREAD = "one"
DAILY_THEME = "今日の一枚"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="bot.daily",
        description="錦野舞のタロット執務室 — 今日の一枚（定期投稿）",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--live", action="store_true", help="実際に Misskey へ投稿する（既定は dry-run）")
    mode.add_argument("--dry-run", action="store_true", help="投稿せず内容を標準出力に出す（既定）")
    parser.add_argument("--force", action="store_true",
                        help="同じ日にすでに投稿済みでも投稿する")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = parse_args(argv)
    try:
        config = load_config()
    except ConfigError as exc:
        log.error("%s", exc)
        return 2

    live = args.live
    if not live:
        log.info("dry-run で実行します（実投稿するには --live）")

    state = state_mod.State(config.state_path)
    date_key = datetime.now().strftime("%Y-%m-%d")
    if state.daily_already_posted(date_key) and not args.force:
        log.info("%s はすでに投稿済みです（再投稿するには --force）", date_key)
        return 0

    client = Misskey(config)
    try:
        body, image_path, meta = perform_reading(
            config, DAILY_THEME, slug=f"daily-{date_key}", spread=DAILY_SPREAD,
        )
        _publish(client, live, body, image_path, meta["alt_text"], reply_id=None,
                 cw=_reading_cw(config, meta["spread_label"]))
        if live:
            state.mark_daily_posted(date_key)
            state.save()
            if config.save_readings:
                saved = state_mod.save_reading(
                    f"{DAILY_THEME}（{date_key}）", meta["spread_label"], meta["summary"], body,
                )
                log.info("記録を保存しました: %s", saved)
        return 0
    except (MisskeyError, ReadingError, SsotError, TarotError) as exc:
        log.error("%s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
