# 錦野舞のタロット執務室 — Misskey Bot
#
# ビルド（リポジトリのルートで実行）:
#   docker build -f bot/deploy/Dockerfile -t tarot-mai .
#
# 実行（秘密情報はイメージに焼かず --env-file で渡す）:
#   docker run -d --name tarot-mai --restart unless-stopped \
#     --env-file .env \
#     -v tarot-mai-state:/app/bot/state \
#     -v tarot-mai-readings:/app/readings \
#     tarot-mai
#
# 「今日の一枚」はホスト側の cron から:
#   docker run --rm --env-file .env -v tarot-mai-state:/app/bot/state \
#     tarot-mai python -m bot.daily --live

FROM python:3.12-slim

# 陣形画像に日本語を描くためにフォントが要る（無いと画像生成が RuntimeError で落ちる）
RUN apt-get update \
 && apt-get install -y --no-install-recommends fonts-noto-cjk \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY bot/requirements.txt bot/requirements.txt
RUN pip install --no-cache-dir -r bot/requirements.txt

# 正本・占い資料・カード画像を含むリポジトリ全体を置く（Bot は実行時にこれを読む）
COPY . .

# 非rootで動かす
RUN useradd --create-home --uid 10001 tarot \
 && mkdir -p /app/bot/state /app/readings \
 && chown -R tarot:tarot /app/bot/state /app/readings
USER tarot

# このイメージは常駐運用が前提なので CMD は --live。
# 動作確認したいときはコマンドを差し替える:
#   docker run --rm --env-file .env tarot-mai python -m bot.main --check
#   docker run --rm --env-file .env tarot-mai python -m bot.main --once --dry-run
CMD ["python", "-m", "bot.main", "--live"]
