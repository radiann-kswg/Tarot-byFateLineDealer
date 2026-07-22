#!/usr/bin/env bash
# 錦野舞のタロット執務室 — GCE(Debian 12) 用 プロビジョニングスクリプト
#
# VM 上で root（sudo）で一度だけ実行する。何度流しても壊れない（冪等）。
# apt 導入 → 専用ユーザー作成 → main ブランチを clone → venv → systemd 配置 まで行う。
#
#   sudo bash /opt/tarot-mai/bot/deploy/provision.sh
#   （初回は下記 BOOTSTRAP のとおり、clone 前でも curl で取得して実行できる）
#
# ★安全のため、このスクリプトは Bot を自動で --live 起動しない。
#   .env を置いて `--check` が通ることを確認してから、最後に表示される手順で
#   段階的に公開してください（AGENTS.md §6.5 / bot/README.md「ロールアウト」）。
set -euo pipefail

REPO_URL="https://github.com/radiann-kswg/Tarot-byFateLineDealer.git"
BRANCH="main"                 # 本番は origin/main（AGENTS.md §7）。develop を直接置かない。
APP_DIR="/opt/tarot-mai"
APP_USER="tarot"
TZ_NAME="Asia/Tokyo"

log() { printf '\033[36m[provision]\033[0m %s\n' "$*"; }

if [[ $EUID -ne 0 ]]; then
  echo "root で実行してください: sudo bash $0" >&2
  exit 1
fi

log "タイムゾーンを ${TZ_NAME} に設定（定期投稿の 08:00 をJSTに合わせる）"
timedatectl set-timezone "${TZ_NAME}" || true

log "必要パッケージを導入（python3-venv / pip / git / 日本語フォント）"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y --no-install-recommends \
  python3 python3-venv python3-pip git ca-certificates fonts-noto-cjk
rm -rf /var/lib/apt/lists/*

log "実行専用ユーザー ${APP_USER} を用意（ログイン不可・最小権限）"
if ! id -u "${APP_USER}" >/dev/null 2>&1; then
  useradd --system --create-home --shell /usr/sbin/nologin "${APP_USER}"
fi

log "リポジトリを ${APP_DIR}（${BRANCH}）に配置"
if [[ -d "${APP_DIR}/.git" ]]; then
  git -C "${APP_DIR}" fetch --depth 1 origin "${BRANCH}"
  git -C "${APP_DIR}" checkout "${BRANCH}"
  git -C "${APP_DIR}" reset --hard "origin/${BRANCH}"
else
  git clone --depth 1 -b "${BRANCH}" "${REPO_URL}" "${APP_DIR}"
fi

log "Python 仮想環境を作成し依存を導入"
if [[ ! -d "${APP_DIR}/.venv" ]]; then
  python3 -m venv "${APP_DIR}/.venv"
fi
"${APP_DIR}/.venv/bin/pip" install --upgrade pip
"${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/bot/requirements.txt"

log "状態・記録ディレクトリを用意して所有者を ${APP_USER} に"
mkdir -p "${APP_DIR}/bot/state" "${APP_DIR}/readings"
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}/bot/state" "${APP_DIR}/readings"
# リポジトリ本体は root 所有（読み取りのみ）。書き込みは state / readings に限定。

log "systemd ユニットを配置"
install -m 0644 "${APP_DIR}/bot/deploy/tarot-mai-bot.service"   /etc/systemd/system/
install -m 0644 "${APP_DIR}/bot/deploy/tarot-mai-daily.service" /etc/systemd/system/
install -m 0644 "${APP_DIR}/bot/deploy/tarot-mai-daily.timer"   /etc/systemd/system/
systemctl daemon-reload

cat <<EOF

\033[32m[provision] 環境の準備が完了しました。\033[0m

次にやること（順番どおりに）:

  1) 秘密情報を置く（このスクリプトは .env を作りません）
       ローカルから scp 済みなら:  sudo mv ~/\.env ${APP_DIR}/.env
       所有者と権限を締める:        sudo chown ${APP_USER}:${APP_USER} ${APP_DIR}/.env && sudo chmod 600 ${APP_DIR}/.env

  2) 疎通確認（投稿もAPI課金もしない）
       sudo -u ${APP_USER} ${APP_DIR}/.venv/bin/python -m bot.main --check
       （working dir はリポジトリのルート ${APP_DIR}）
       cd ${APP_DIR} && sudo -u ${APP_USER} ${APP_DIR}/.venv/bin/python -m bot.main --check

  3) 読み解きだけ試す（Misskeyには繋がない・Claudeは課金あり）
       cd ${APP_DIR} && sudo -u ${APP_USER} ${APP_DIR}/.venv/bin/python -m bot.main --simulate "今日の私へ"

  4) メンションを1件だけ home 公開で実投稿（先に別アカウントからBot宛にメンションを送る）
       cd ${APP_DIR} && sudo -u ${APP_USER} ${APP_DIR}/.venv/bin/python -m bot.main --once --live

  5) 問題なければ常駐を開始
       sudo systemctl enable --now tarot-mai-bot
       sudo journalctl -u tarot-mai-bot -f

  6) 「今日の一枚」定期投稿を有効化（毎朝08:00 JST）
       sudo systemctl enable --now tarot-mai-daily.timer
       systemctl list-timers tarot-mai-daily.timer

  公開範囲を広げるのは数日 home で安定を確認してから。.env の
  MISSKEY_VISIBILITY=public に変えて Bot を再起動してください（AGENTS.md §6.5）。
EOF
