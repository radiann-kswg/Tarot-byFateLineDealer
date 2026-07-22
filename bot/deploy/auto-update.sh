#!/usr/bin/env bash
# 錦野舞のタロット執務室 — 自動更新（プル型）
#
# origin/main が進んでいたら pull して、依存・systemdユニットを取り込み、Bot を再起動する。
# tarot-mai-update.timer から root で定期実行される。何度流しても壊れない（冪等）。
#
# ★デプロイ元は origin/main のみ（AGENTS.md §7）。main に載ったものがそのまま本番へ反映される。
#   .env はリポジトリ管理外なので、この更新で MISSKEY_VISIBILITY 等が書き換わることはない。
set -euo pipefail

APP_DIR="/opt/tarot-mai"
BRANCH="main"
APP_USER="tarot"
LOCK="/run/tarot-mai-update.lock"

log() { printf '%s [auto-update] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }

# 多重起動を防ぐ（前回がまだ走っていたら黙って抜ける）
exec 9>"${LOCK}"
flock -n 9 || { log "別の更新が実行中のためスキップ"; exit 0; }

git config --global --add safe.directory "${APP_DIR}" 2>/dev/null || true
cd "${APP_DIR}"

git fetch --quiet origin "${BRANCH}"
local_rev="$(git rev-parse HEAD)"
remote_rev="$(git rev-parse "origin/${BRANCH}")"

if [[ "${local_rev}" == "${remote_rev}" ]]; then
  log "更新なし（${local_rev:0:7}）"
  exit 0
fi

log "更新を検出: ${local_rev:0:7} -> ${remote_rev:0:7}"
git reset --hard "origin/${BRANCH}"          # ローカル変更は破棄。state/readings は gitignore なので残る

# 依存を取り込む（変化が無ければ短時間で終わる）
"${APP_DIR}/.venv/bin/pip" install --quiet --upgrade pip
"${APP_DIR}/.venv/bin/pip" install --quiet -r "${APP_DIR}/bot/requirements.txt"

# systemd ユニットの変更も反映（この更新スクリプト自身の変更も次回から効く）
for unit in tarot-mai-bot.service tarot-mai-daily.service tarot-mai-daily.timer \
            tarot-mai-update.service tarot-mai-update.timer; do
  install -m 0644 "${APP_DIR}/bot/deploy/${unit}" /etc/systemd/system/
done
systemctl daemon-reload

# 書き込み先の所有者を保つ（reset で新規ファイルが入っても崩れないように）
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}/bot/state" "${APP_DIR}/readings" 2>/dev/null || true

# 正本・コードは起動時に読み込むので、常駐 Bot を再起動して反映する
systemctl restart tarot-mai-bot
log "更新して再起動しました（${remote_rev:0:7}）"
