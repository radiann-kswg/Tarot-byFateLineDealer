# GCE 本番デプロイ手順書（錦野舞のタロット Bot）

対象: Google Compute Engine の常時起動 VM で、メンション応答の常駐＋「今日の一枚」定期投稿を動かす。
方針: **GCE 一本化**（Cloudflare はこの常駐デーモンの置き場所にはならないため使わない）。
秘密情報: **ローカルの `.env` を `scp` でVMへ転送**する（中身は誰にも見せず、コミットもしない）。

構成のポイント: この Bot は Misskey へ**自分から取りに行く**（アウトバウンド）だけで、外から接続を受けない。
だから **受信ポートを開ける必要はない**（ファイアウォールは既定の egress 許可のみでよい）。

---

## 前提（先に済ませること）

1. **`origin/main` に最新を反映**しておく。この手順書と `provision.sh`、実運用の修正は
   作業ブランチ／`develop` にあるので、**PR で `develop → main` をマージ**してからデプロイする
   （`main` へ直接 push しない・AGENTS.md §7.2）。`provision.sh` は `main` から clone するため、
   これが済んでいないとVM側に存在しない。
2. **GCP プロジェクトID**を用意（VM作成に必須）。
3. ローカルの `gcloud` CLI にログイン（VMへの `scp`/`ssh` に使う）。
   ```bash
   gcloud auth login
   gcloud config set project <PROJECT_ID>
   ```

---

## STEP 1. VM を作成（担当: 舞 / GCEコネクタ）

| 項目 | 値 |
| --- | --- |
| 名前 | `tarot-mai-bot` |
| ゾーン | `asia-northeast1-a`（東京） |
| マシンタイプ | `e2-small` |
| イメージ | `debian-12`（`debian-cloud`） |

同等の gcloud コマンド（手動で作る場合の参考）:

```bash
gcloud compute instances create tarot-mai-bot \
  --project=<PROJECT_ID> --zone=asia-northeast1-a \
  --machine-type=e2-small --image-family=debian-12 --image-project=debian-cloud
```

## STEP 2. 秘密情報 `.env` を転送（担当: あなた）

ローカルのリポジトリ直下 or `bot/.env` にある本番用 `.env` を、VMのホームへ送る。

```bash
# ローカルの .env を VM の ~/.env へ（中身は表示されない）
gcloud compute scp bot/.env tarot-mai-bot:~/.env \
  --project=<PROJECT_ID> --zone=asia-northeast1-a
```

> `MISSKEY_VISIBILITY=home` のまま送ること（最初は控えめに公開）。安定確認後に `public` へ。

## STEP 3. プロビジョニング（担当: あなた / VM内で1回）

VM に入り、`main` から取得したスクリプトで環境を一括構築する（apt・venv・clone・systemd配置）。
**このスクリプトは Bot を自動起動しない**ので、この時点では何も投稿されない。

```bash
gcloud compute ssh tarot-mai-bot --project=<PROJECT_ID> --zone=asia-northeast1-a

# ↓ VM の中で
curl -fsSL https://raw.githubusercontent.com/radiann-kswg/Tarot-byFateLineDealer/main/bot/deploy/provision.sh \
  | sudo bash

# 転送した .env を所定の場所へ移し、権限を締める
sudo mv ~/.env /opt/tarot-mai/.env
sudo chown tarot:tarot /opt/tarot-mai/.env
sudo chmod 600 /opt/tarot-mai/.env
```

## STEP 4. 段階リリース（担当: あなた / provision の最後にも表示される）

投稿は公開・不可逆。いきなり常駐にせず、順番に確かめる（bot/README.md「ロールアウト」）。

```bash
cd /opt/tarot-mai
# 1) 疎通確認（投稿もAPI課金もしない）。isBot と権限4つを確認
sudo -u tarot .venv/bin/python -m bot.main --check
# 2) 読み解きだけ試す（Misskey非接続・Claudeは課金あり）
sudo -u tarot .venv/bin/python -m bot.main --simulate "今日の私へ"
# 3) 別アカウントからBot宛にメンション → 1件だけ home 公開で実投稿
sudo -u tarot .venv/bin/python -m bot.main --once --live
# 4) 問題なければ常駐開始
sudo systemctl enable --now tarot-mai-bot
sudo journalctl -u tarot-mai-bot -f
# 5) 「今日の一枚」定期投稿（毎朝08:00 JST）
sudo systemctl enable --now tarot-mai-daily.timer
```

数日 `home` で安定を見てから、`.env` の `MISSKEY_VISIBILITY=public` に変更して
`sudo systemctl restart tarot-mai-bot`。

---

## 運用メモ

- **更新**: `develop → main` を PR でマージ → VM で `cd /opt/tarot-mai && sudo git pull` →
  `sudo systemctl restart tarot-mai-bot`（正本はプロセス起動時に読むので再起動が必要）。
- **止める**: `sudo systemctl stop tarot-mai-bot`。定期投稿は `... stop tarot-mai-daily.timer`。
- **状態ファイル**: `bot/state/state.json` は消さない（消すと過去メンションを再処理しうる）。
- **コスト**: VMは `e2-small` の常時起動分＋Claude API 従量（1回 ≒ $0.03〜0.08、bot/README.md 参照）。
  使わなくなったら `gcloud compute instances stop tarot-mai-bot` で課金を止められる。
- **鍵の失効**: トークン/キーを更新したら `.env` を差し替えて Bot を再起動する。
