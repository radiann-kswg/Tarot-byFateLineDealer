"""メンション応答ループ（フェーズ1〜2）。

外向きの投稿は公開・不可逆なので**既定は dry-run**。実投稿には `--live` が要る（AGENTS.md §6.5）。

    py -m bot.main --check              疎通確認のみ（投稿もAPI課金もしない）
    py -m bot.main --once --dry-run     1件だけ処理して結果を標準出力（既定）
    py -m bot.main --once --live        1件だけ実投稿
    py -m bot.main --live               常駐
"""
from __future__ import annotations

import argparse
import logging
import sys
import time

from . import reading as reading_mod
from . import misskey as misskey_mod
from . import emoji as emoji_mod
from . import safety, ssot, state as state_mod, tarot
from .config import Config, ConfigError, load_config
from .emoji import EmojiError
from .misskey import Misskey, MisskeyError, strip_mentions
from .reading import ReadingError
from .ssot import SsotError
from .tarot import TarotError

log = logging.getLogger("tarot-mai")

# 相談文が空だったときに使う既定のテーマ（一言だけ引く）
EMPTY_THEME = "今のあなたへのメッセージ"

# 常駐中、相談が無いときに生存を書き残す間隔（秒）
IDLE_LOG_INTERVAL = 3600


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )


def clamp(text: str, limit: int) -> str:
    """本文を上限内に収める。文の切れ目を優先して切る。"""
    if len(text) <= limit:
        return text
    log.warning("本文が %d 字だったため %d 字に収めました", len(text), limit)
    cut = text[:limit]
    for separator in ("。", "\n"):
        index = cut.rfind(separator)
        if index > limit * 0.6:
            return cut[: index + 1].rstrip()
    return cut.rstrip() + "…"


def perform_reading(config: Config, theme: str, slug: str, spread: str | None = None):
    """抽選 → 陣形画像 → 読み解き。投稿はしない。

    Returns:
        (本文, 画像パス, メタ情報の辞書)
    """
    verdict = safety.screen(theme)
    if verdict.action != "read":
        raise AssertionError("safety の判定は呼び出し側で処理してください")

    if spread is None:
        spread, reason = tarot.choose_spread(theme)
    else:
        reason = "呼び出し側の指定"

    cards = tarot.draw(spread)
    image_path = tarot.render(cards, spread, theme, slug)
    result = reading_mod.generate(config, theme, spread, reason, cards, verdict.sensitive)

    label = tarot.SPREAD_LABELS.get(spread, spread)
    summary = tarot.summary_line(cards)
    log.info("スプレッド=%s(%s) カード=%s / %s", label, reason, summary, result.cache_note)

    body = clamp(result.text, config.max_body_chars)
    meta = {
        "spread": spread,
        "spread_label": label,
        "reason": reason,
        "cards": cards,
        "summary": summary,
        "sensitive": verdict.sensitive,
        "alt_text": f"{label}：{summary}",
    }
    return body, image_path, meta


def perform_emoji_reply(config: Config, theme: str, slug: str, parsed: emoji_mod.Parsed):
    """カード絵文字つきのメンションに応じる（AGENTS.md §4-7・§6.6）。

    **抽選しない。** 相談者が持ち込んだ並びをそのまま扱う。

    Returns:
        (本文, 画像パス, メタ情報の辞書)。
        並びの型を決めきれないときは本文が None になり、meta["ask"] に定型文IDが入る。
    """
    verdict = safety.screen(theme)
    if verdict.action != "read":
        raise AssertionError("safety の判定は呼び出し側で処理してください")

    cards = parsed.cards
    tarot.validate_cards(cards)
    mode = parsed.mode

    if mode == "brought":
        spread, reason = emoji_mod.infer_spread(theme, len(cards))
        if spread is None:
            # 推測で型を当てはめず、尋ねる（AGENTS.md §6.6-3）
            log.info("持ち込み %d 枚。並びの型を決めきれないため確認します", len(cards))
            return None, None, {"ask": "spread-unclear", "count": len(cards), "cards": cards}
    else:
        # 解説は並びを問わないので、常に「並び」として合成する
        spread, reason = emoji_mod.LINE_SPREAD, f"{mode} の解説のため並びとして扱う"

    image_path = tarot.render(cards, spread, theme, slug)

    if mode == "brought":
        result = reading_mod.generate_brought(config, theme, spread, reason, cards,
                                              verdict.sensitive)
    elif mode == "imagery":
        result = reading_mod.generate_imagery(config, theme, cards, verdict.sensitive)
    else:
        result = reading_mod.generate_meaning(config, theme, cards, verdict.sensitive)

    label = tarot.SPREAD_LABELS.get(spread, spread)
    summary = tarot.summary_line(cards)
    log.info("持ち込み（%s）=%s(%s) カード=%s / %s",
             mode, label, reason, summary, result.cache_note)

    meta = {
        "ask": None,
        "mode": mode,
        "spread": spread,
        "spread_label": label,
        "reason": reason,
        "cards": cards,
        "summary": summary,
        "sensitive": verdict.sensitive,
        "alt_text": f"{label}：{summary}",
        # 占いは畳む。解説は占いではないので畳まない（AGENTS.md §6.6）
        "fold": mode == "brought",
    }
    return clamp(result.text, config.max_body_chars), image_path, meta


def _reading_cw(config: Config, spread_label: str, brought: bool = False) -> str | None:
    """占い結果を畳むための CW 見出し（AGENTS.md §6.1-3）。文面の正本は §6.3。

    持ち込みの読み解きでは、舞が引いたように読めない `cw-brought` を使う（§4-7）。
    """
    if not config.fold_reading:
        return None
    return ssot.template("cw-brought" if brought else "cw-reading", spread=spread_label)


def _publish(client: Misskey | None, live: bool, body: str, image_path, alt_text: str,
             reply_id: str | None, cw: str | None = None) -> None:
    """投稿する。dry-run のときは標準出力に出すだけ（client は使わないので None でよい）。"""
    if not live:
        print("\n" + "=" * 72)
        print(f"[dry-run] 返信先: {reply_id or '(なし・単独投稿)'}")
        print(f"[dry-run] 添付画像: {image_path}")
        print(f"[dry-run] 画像の説明: {alt_text}")
        print(f"[dry-run] CW（畳む見出し）: {cw or '(畳まない)'}")
        print("-" * 72)
        print(body)
        print("=" * 72 + "\n")
        return
    file_ids = [client.upload(image_path, comment=alt_text)] if image_path else None
    note = client.create_note(body, reply_id=reply_id, file_ids=file_ids, cw=cw)
    log.info("投稿しました: %s（CW=%s）", note.get("id", "(id不明)"), "あり" if cw else "なし")


def _reply_template(client: Misskey, config: Config, live: bool, template_id: str,
                    reply_id: str) -> None:
    """定型文で返す（占わない分岐）。文面の正本は AGENTS.md §6.3。

    **これらは CW で畳まない**（AGENTS.md §6.1-3）。つらいときや不具合のときに、
    ワンクリック挟ませないため。
    """
    body = ssot.template(template_id, support_url=config.support_url)
    _publish(client, live, body, None, "", reply_id, cw=None)


def _reply_template_fields(client: Misskey, config: Config, live: bool, template_id: str,
                           reply_id: str, **fields: str) -> None:
    """差し替え値のある定型文で返す（`spread-unclear` の {count} など）。**畳まない**。"""
    body = ssot.template(template_id, support_url=config.support_url, **fields)
    _publish(client, live, body, None, "", reply_id, cw=None)


def handle_notification(config: Config, client: Misskey, state: state_mod.State,
                        notification: dict, live: bool) -> bool:
    """通知1件を処理する。応答したら True。"""
    notification_id = notification["id"]
    note = notification.get("note") or {}
    note_id = note.get("id")
    user = notification.get("user") or {}
    user_id = user.get("id") or "unknown"
    handle = user.get("username", "unknown")

    if not note_id:
        log.info("[%s] ノートが無い通知のためスキップ", notification_id)
        return False
    if state.already_replied(notification_id):
        log.debug("[%s] 応答済みのためスキップ", notification_id)
        return False
    if state.cooling_down(user_id, config.user_cooldown):
        log.info("[%s] @%s はクールダウン中のため応答しません", notification_id, handle)
        return False

    theme = strip_mentions(note.get("text") or "") or EMPTY_THEME
    log.info("[%s] @%s からの相談: %s", notification_id, handle,
             theme[:60] + ("…" if len(theme) > 60 else ""))

    verdict = safety.screen(theme)
    parsed = emoji_mod.parse(theme)

    if verdict.action != "read":
        # 安全性の分岐は絵文字の有無より先に効く（AGENTS.md §6.6）
        log.warning("[%s] %s に該当（%s）。占わずに定型応答します",
                    notification_id, verdict.action, verdict.matched)
        _reply_template(client, config, live, verdict.template, note_id)
    elif parsed.unknown:
        # 読み取れない絵文字が1つでもあれば、黙って落として枚数を変えない（AGENTS.md §4-7）。
        # 一部だけ読めていても同じ。並びが欠けたまま型を推定するほうが害が大きい。
        log.warning("[%s] 未知のカード絵文字 %d 個（読めた札 %d 枚）: %s", notification_id,
                    len(parsed.unknown), len(parsed.cards), "、".join(parsed.unknown))
        _reply_template(client, config, live, "emoji-unknown", note_id)
    elif parsed.has_cards and not parsed.wants_draw:
        # 持ち込み（AGENTS.md §4-7）。抽選しない
        body, image_path, meta = perform_emoji_reply(config, theme, notification_id, parsed)
        if meta["ask"]:
            _reply_template_fields(client, config, live, meta["ask"], note_id,
                                   count=str(meta["count"]))
        else:
            cw = (_reading_cw(config, meta["spread_label"], brought=True)
                  if meta["fold"] else None)
            _publish(client, live, body, image_path, meta["alt_text"], note_id, cw=cw)
            if live and config.save_readings and meta["mode"] == "brought":
                saved = state_mod.save_reading(theme, meta["spread_label"], meta["summary"], body)
                log.info("[%s] 記録を保存しました: %s", notification_id, saved)
    else:
        body, image_path, meta = perform_reading(config, theme, slug=notification_id)
        _publish(client, live, body, image_path, meta["alt_text"], note_id,
                 cw=_reading_cw(config, meta["spread_label"]))
        if live and config.save_readings:
            saved = state_mod.save_reading(theme, meta["spread_label"], meta["summary"], body)
            log.info("[%s] 記録を保存しました: %s", notification_id, saved)

    if live:
        state.mark_replied(notification_id)
        state.touch_user(user_id, config.user_cooldown)
        # 1件返すたびに永続化する。バッチの最後まで待つと、途中でプロセスが落ちたときに
        # 「投稿は済んでいるのに応答済みとして残っていない」通知ができてしまい、
        # 再起動後に二度返信する（AGENTS.md §6.5）。SPOT VM のように予告なく
        # 止められる環境では、この取りこぼしが現実に起こりうる。
        state.save()
    return True


def run_once(config: Config, client: Misskey, state: state_mod.State, live: bool,
             limit: int, catch_up: bool, idle_notice: bool = True) -> int:
    """1回分のポーリング。処理した件数を返す。

    idle_notice を False にすると、通知が無かったときの案内を DEBUG に落とす
    （常駐ループ用。共用VMの journald を埋めないため）。
    """
    since_id = state.last_notification_id
    notifications = client.notifications(since_id, limit=limit, mark_as_read=live)
    if not notifications:
        if idle_notice:
            log.info("新しいメンション・リプライはありません（sinceId=%s）。"
                     "Bot 宛にメンションしてから、もう一度試してください。", since_id or "なし")
            log.info("読み解きだけ先に確かめたいときは: py -m bot.main --simulate \"相談文\"")
        else:
            log.debug("新しいメンション・リプライはありません（sinceId=%s）", since_id or "なし")
        return 0

    newest = notifications[-1]["id"]

    # 初回起動でバックログ全体に返信してしまうのを防ぐ（--catch-up で明示的に処理できる）
    if since_id is None and not catch_up:
        log.info("初回起動のため、既存の通知 %d 件には応答しません（処理するには --catch-up）",
                 len(notifications))
        if live:
            state.last_notification_id = newest
            state.save()
        return 0

    handled = 0
    for notification in notifications:
        try:
            if handle_notification(config, client, state, notification, live):
                handled += 1
        except (ReadingError, TarotError, EmojiError, SsotError) as exc:
            log.error("[%s] 読み解きに失敗: %s", notification["id"], exc)
            note_id = (notification.get("note") or {}).get("id")
            if note_id:
                try:
                    _reply_template(client, config, live, "api-error", note_id)
                    if live:
                        state.mark_replied(notification["id"])
                except MisskeyError as post_exc:
                    log.error("おわびの投稿にも失敗しました: %s", post_exc)
        except MisskeyError as exc:
            log.error("[%s] Misskey への送信に失敗: %s", notification["id"], exc)
            if not exc.retryable and live:
                state.mark_replied(notification["id"])

    if live:
        state.last_notification_id = newest
        state.save()
    return handled


def run_loop(config: Config, client: Misskey, state: state_mod.State, live: bool,
             limit: int, catch_up: bool) -> None:
    log.info("メンションの監視を開始します（%d 秒ごと・%s）",
             config.poll_interval, "実投稿" if live else "dry-run")
    last_idle_log: float | None = None
    while True:
        try:
            run_once(config, client, state, live, limit, catch_up, idle_notice=False)
            # 何も無いときは IDLE_LOG_INTERVAL に1回だけ生存を書く。毎回書くと
            # 1日5千行を超え、共用VMでは他のBotのログを journald から押し出す。
            now = time.monotonic()
            if last_idle_log is None or now - last_idle_log >= IDLE_LOG_INTERVAL:
                log.info("待機中（%d 秒ごとに確認・sinceId=%s）",
                         config.poll_interval, state.last_notification_id or "なし")
                last_idle_log = now
        except MisskeyError as exc:
            log.error("通知の取得に失敗: %s", exc)
        except KeyboardInterrupt:
            log.info("停止します")
            return
        catch_up = False   # 2周目以降は sinceId で絞られる
        try:
            time.sleep(config.poll_interval)
        except KeyboardInterrupt:
            log.info("停止します")
            return


def cmd_check(config: Config, client: Misskey) -> int:
    """疎通確認。投稿もAPI課金もしない。"""
    log.info("設定の読み込み元: %s", config.env_file or "（環境変数のみ）")
    account = client.me()
    is_bot = account.get("isBot")
    log.info("Misskey: @%s（%s）に接続できました", account.get("username"), config.misskey_host)
    log.info("  ボットフラグ isBot = %s", is_bot)
    if not is_bot:
        log.warning("  ボットフラグが立っていません。AGENTS.md §6.4 に従って有効化してください")
    log.info("  投稿の公開範囲 = %s", config.misskey_visibility)

    model = reading_mod.check(config)
    log.info("Anthropic: モデル %s（%s）を確認しました", config.anthropic_model, model)

    prompt = ssot.build_system_prompt()
    templates = sorted(ssot.load_templates())
    deck = ssot.deck_index()
    imagery = ssot.imagery_index()
    emojis = emoji_mod.emoji_index()
    log.info("正本: システムプロンプト %d 文字 / 定型文 %s / デッキ %d 枚",
             len(prompt), "・".join(templates), len(deck))
    log.info("  図像資料 %d 枚 / カード絵文字 %d 個", len(imagery), len(emojis))
    missing = [card for card in deck if card not in imagery]
    if missing:
        log.warning("  図像資料が無いカードが %d 枚あります（先頭: %s）",
                    len(missing), "、".join(missing[:3]))
    log.info("相談窓口URL = %s", config.support_url)
    return 0


def cmd_simulate(config: Config, text: str, spread: str | None) -> int:
    """メンションを待たずに、読み解きの中身だけを確かめる。

    Misskey には一切触れない（通知も読まないし投稿もしない）。Claude API は呼ぶので課金は発生する。
    正本を編集したあと、応答の調子が変わったかを見るのにも使える。
    """
    log.info("シミュレーション（Misskey には接続しません）")
    verdict = safety.screen(text)
    if verdict.action != "read":
        log.warning("%s に該当（%s）。占わずに定型応答します", verdict.action, verdict.matched)
        body = ssot.template(verdict.template, support_url=config.support_url)
        _publish(None, False, body, None, "", reply_id=None)
        return 0

    parsed = emoji_mod.parse(text)
    if parsed.unknown and not parsed.has_cards:
        log.warning("未知のカード絵文字: %s", "、".join(parsed.unknown))
        _publish(None, False, ssot.template("emoji-unknown"), None, "", reply_id=None)
        return 0
    if parsed.has_cards and not parsed.wants_draw:
        log.info("カード絵文字 %d 枚を検出しました（モード=%s）。抽選せず持ち込みとして扱います",
                 len(parsed.cards), parsed.mode)
        body, image_path, meta = perform_emoji_reply(config, text, "simulate", parsed)
        if meta["ask"]:
            _publish(None, False,
                     ssot.template(meta["ask"], count=str(meta["count"])),
                     None, "", reply_id=None)
            return 0
        cw = (_reading_cw(config, meta["spread_label"], brought=True)
              if meta["fold"] else None)
        _publish(None, False, body, image_path, meta["alt_text"], reply_id=None, cw=cw)
        return 0

    body, image_path, meta = perform_reading(config, text, slug="simulate", spread=spread)
    _publish(None, False, body, image_path, meta["alt_text"], reply_id=None,
             cw=_reading_cw(config, meta["spread_label"]))
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="bot.main",
        description="錦野舞のタロット執務室 — Misskey Bot（メンション応答）",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--live", action="store_true",
                      help="実際に Misskey へ投稿する（既定は dry-run）")
    mode.add_argument("--dry-run", action="store_true",
                      help="投稿せず、返信本文と画像パスを標準出力に出す（既定）")
    parser.add_argument("--check", action="store_true",
                        help="疎通確認だけ行って終了する（投稿もAPI課金もしない）")
    parser.add_argument("--simulate", metavar="相談文",
                        help="メンションを待たずに、その相談文で読み解きだけ試す"
                             "（Misskey には接続しない。Claude API は呼ぶので課金あり）")
    parser.add_argument("--spread", choices=list(tarot.DRAWABLE_SPREADS),
                        help="--simulate でスプレッドを指定する（省略時は舞が選ぶ）")
    parser.add_argument("--once", action="store_true", help="1回だけポーリングして終了する")
    parser.add_argument("--limit", type=int, default=10,
                        help="1回のポーリングで取得する通知の最大件数（既定: 10）")
    parser.add_argument("--catch-up", action="store_true",
                        help="初回起動時に既存の通知にも応答する（既定は応答しない）")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = parse_args(argv)
    try:
        config = load_config()
    except ConfigError as exc:
        log.error("%s", exc)
        return 2

    try:
        # Misskey に触れない経路は、クライアントを作る前に処理する
        if args.simulate:
            return cmd_simulate(config, args.simulate, args.spread)

        client = Misskey(config)
        if args.check:
            return cmd_check(config, client)

        live = args.live
        if not live:
            log.info("dry-run で実行します（実投稿するには --live）")

        state = state_mod.State(config.state_path)
        if args.once:
            handled = run_once(config, client, state, live, args.limit, args.catch_up)
            log.info("%d 件処理しました", handled)
        else:
            run_loop(config, client, state, live, args.limit, args.catch_up)
        return 0
    except (MisskeyError, ReadingError, SsotError, TarotError, EmojiError) as exc:
        log.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        log.info("停止します")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
