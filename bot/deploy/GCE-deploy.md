# GCE 本番デプロイ手順書（錦野舞のタロット Bot）

対象: Google Compute Engine の VM で、メンション応答の常駐＋「今日の一枚」定期投稿を動かす。
方針: **Misskey Bot 群の共用VM `misskey-bots-unified` に間借りする**（GCP のコスト削減で集約された）。
秘密情報: **ローカルの `.env` を `scp` でVMへ転送**する（中身は誰にも見せず、コミットもしない）。

構成のポイント: この Bot は Misskey へ**自分から取りに行く**（アウトバウンド）だけで、外から接続を受けない。
だから **受信ポートを開ける必要はない**（ファイアウォールは既定の egress 許可のみでよい）。

---

## 配置先

| | VM | プロジェクト / ゾーン | 備考 |
| --- | --- | --- | --- |
| **移設先** | `misskey-bots-unified` | `numbertales-misskey-surver` / `us-central1-a` | e2-medium・**SPOT**・Bot 群の共用 |
| 移設元（旧） | `fli-tarot-bot` | `fateline-investigators-service` / `asia-northeast1-a` | e2-small・このBot専用。移設後は停止する |

共用VMに同居しているもの（2026-08-05 時点）:

- サービス: `aphrnts-100-bot` / `ai_bot` / `pm2-snine9801`
- タイマー: `aphrnts-100-deploy` / `aphrnts-100-watchdog` / `numbertales-watchdog`

`tarot-mai-*` という名前はどれとも衝突しない。

---

## 共用VMで守ること

**ホスト全体に及ぶものを変えない。** 同居しているBotが巻き添えになる。

- タイムゾーン（`timedatectl`）を変えない。
  「今日の一枚」の 08:00 は `tarot-mai-daily.timer` の `OnCalendar` に `Asia/Tokyo` を明示してあるので、
  ホストのTZが何であっても JST で発火する。
- `/var/lib/apt/lists` を消さない（共有の apt キャッシュ）。パッケージは不足分だけ入れる。
- root の `~/.gitconfig` を書き換えない（他のBotの更新スクリプトと共有している）。

この3つは [`provision.sh`](provision.sh) と [`auto-update.sh`](auto-update.sh) が守るように書いてある。
**触ってよいのは `/opt/tarot-mai`・`tarot-mai-*` のユニット・専用ユーザー `tarot` だけ。**

資源の食い合いは systemd 側で自分に上限を課して防いでいる（[`tarot-mai-bot.service`](tarot-mai-bot.service)）。
はみ出したときに落ちるのは同居のBotではなくこの Bot 自身で、`Restart=always` で戻ってくる。

## SPOT VM であること

共用VMは Spot（`instanceTerminationAction=STOP`）。**preemption で停止したあと、自分では戻ってこない。**
Spot VM に `automaticRestart=true` は設定できない（GCP の仕様）。復帰の手当ては下の「運用メモ」を参照。

Bot 側は止められる前提で書いてある。

- 返信するたびに `state.json` を書くので、途中で止められても同じメンションに二度返信しない（AGENTS.md §6.5）。
- `tarot-mai-daily.timer` は `Persistent=true` なので、停止中に 08:00 を跨いでも復帰後に追いかけて投稿する。
  `bot.daily` が同じ日の二度目を弾く。

### 自動で起こす仕組み（VMの外・全Bot共通）

VM側では復帰できないので、**外から定期的に起こす**。共用VM全体に効くもので、
このリポジトリの管理外（GCP 側の設定）にあることに注意。

| 仕掛け | 中身 |
| --- | --- |
| `misskey-bots-unified-autostart`（Cloud Scheduler） | 5分ごとに `compute.instances.start` を POST する。**稼働中に撃っても no-op**（数十ミリ秒で完了し、再起動はしない）ので、状態を判定せず無条件に投げている |
| `numbertales-vm-watchdog`（Cloud Scheduler → Cloud Run） | 先行して存在する見張り。`numbertales-gce-watchdog` が同じVMを対象にしている。**2026-08-05 の preemption では停止から約2分のあいだに `start` を発行しなかった**ため、動作を当てにせず上の無条件起動を重ねている |

Scheduler が使うサービスアカウント `bots-vm-autostart@…` には、
**このVM1台のリソースにだけ** `roles/compute.instanceAdmin.v1` を付けてある（プロジェクト全体には広げない）。

VM が起動すれば、`enable` 済みの `tarot-mai-*` は自動で立ち上がる。手で起こすなら:

```bash
gcloud compute instances start misskey-bots-unified \
  --project=numbertales-misskey-surver --zone=us-central1-a
```

常時稼働がどうしても要るなら Spot をやめて標準（オンデマンド）に戻す判断になるが、費用は数倍になる。
**共用VM全体の方針なので、この Bot だけで決めない。**

---

## 移設の手順

### STEP 0. 前提

1. **`origin/main` に最新を反映**しておく。`provision.sh` は `main` から clone するので、
   共用VM対応が `main` に載っていないと、専用VM前提の古いスクリプトが走る。
   `develop → main` は PR でマージすること（`main` へ直接 push しない・AGENTS.md §7.2）。
2. ローカルの `gcloud` CLI にログイン。

   ```bash
   gcloud auth login
   ```

### STEP 1. プロビジョニング（共用VM内で1回）

`main` から取得したスクリプトで環境を一括構築する（不足パッケージ・venv・clone・systemd配置）。
**このスクリプトは Bot を自動起動しない**ので、この時点では何も投稿されない。
旧VMはまだ動かしたままでよい。

```bash
gcloud compute ssh misskey-bots-unified \
  --project=numbertales-misskey-surver --zone=us-central1-a

# ↓ VM の中で
curl -fsSL https://raw.githubusercontent.com/radiann-kswg/Tarot-byFateLineDealer/main/bot/deploy/provision.sh \
  | sudo bash
```

### STEP 2. 秘密情報 `.env` を転送

ローカルのリポジトリ直下 or `bot/.env` にある本番用 `.env` を、VMのホームへ送ってから所定の場所へ移す。

```bash
gcloud compute scp bot/.env misskey-bots-unified:~/.env \
  --project=numbertales-misskey-surver --zone=us-central1-a

# ↓ VM の中で
sudo mv ~/.env /opt/tarot-mai/.env
sudo chown tarot:tarot /opt/tarot-mai/.env
sudo chmod 600 /opt/tarot-mai/.env
```

> 旧VMと同じトークンを使う。`MISSKEY_VISIBILITY` は旧VMの値をそのまま持ち込むこと
> （移設で公開範囲を同時に変えない。変えるなら安定を確認してから別途）。

### STEP 3. 投稿せずに確かめる

ここまでは旧VMが本番を担当したままでよい。以下は**実投稿しない**。

```bash
cd /opt/tarot-mai
# 疎通確認（投稿もAPI課金もしない）。isBot と権限4つを確認
sudo -u tarot .venv/bin/python -m bot.main --check
# 読み解きだけ試す（Misskey非接続・Claudeは課金あり）
sudo -u tarot .venv/bin/python -m bot.main --simulate "今日の私へ"
```

`--simulate` は陣形画像の生成まで通るので、**日本語フォントが入っているかもここで分かる**。

### STEP 4. 切り替え（★順番を守る）

**新旧の両方が動いている時間を作らないこと。** 同じトークンで同じ通知を拾うので、
二重に返信してしまう（AGENTS.md §6.5）。**必ず旧を止めてから新を上げる。**

**4-1. 旧VMを止める**

```bash
gcloud compute ssh fli-tarot-bot \
  --project=fateline-investigators-service --zone=asia-northeast1-a

# ↓ 旧VM の中で
sudo systemctl disable --now tarot-mai-update.timer   # 先に自動更新を止める
sudo systemctl disable --now tarot-mai-daily.timer
sudo systemctl disable --now tarot-mai-bot
systemctl is-active tarot-mai-bot                     # inactive になったことを確認
```

**4-2. 状態ファイルを引き継ぐ**

`state.json` には応答済み通知ID・クールダウン・「今日の一枚」の投稿日が入っている（秘密情報は無い）。
引き継がなくても初回起動のバックログ抑止が効くので二重返信はしないが、
クールダウンと当日の投稿済み記録を保つために移すのが安全。

```bash
# ↓ 旧VM の中で（tarot 所有・600 なので、読める形にしてから出す）
sudo cp /opt/tarot-mai/bot/state/state.json /tmp/state.json
sudo chown "$(whoami)" /tmp/state.json

# ↓ ローカルで（旧VM → 手元 → 共用VM）
gcloud compute scp fli-tarot-bot:/tmp/state.json ./state.json \
  --project=fateline-investigators-service --zone=asia-northeast1-a
gcloud compute scp ./state.json misskey-bots-unified:~/state.json \
  --project=numbertales-misskey-surver --zone=us-central1-a

# ↓ 共用VM の中で
sudo install -o tarot -g tarot -m 600 ~/state.json /opt/tarot-mai/bot/state/state.json
rm ~/state.json
```

**4-3. 共用VMで1件だけ実投稿して確かめる**

別アカウントからBot宛にメンションを送ってから:

```bash
cd /opt/tarot-mai
sudo -u tarot .venv/bin/python -m bot.main --once --live
```

**4-4. 常駐と定期投稿を開始**

```bash
sudo systemctl enable --now tarot-mai-bot
sudo journalctl -u tarot-mai-bot -f          # または journalctl -t tarot-mai-bot -f
sudo systemctl enable --now tarot-mai-daily.timer
sudo systemctl enable --now tarot-mai-update.timer
systemctl list-timers "tarot-mai-*"
```

### STEP 5. 旧VMを片づける

数日おいて共用VM側が安定したら、旧VMを止めて課金を切る。

```bash
gcloud compute instances stop fli-tarot-bot \
  --project=fateline-investigators-service --zone=asia-northeast1-a
```

停止だけならディスク代は残る。戻す予定が無くなったら削除する（**削除は取り消せない**）。

```bash
gcloud compute instances delete fli-tarot-bot \
  --project=fateline-investigators-service --zone=asia-northeast1-a
```

---

## 自動更新（origin/main → VM）

`tarot-mai-update.timer` が **5分ごとに `origin/main` を確認**し、ローカルより進んでいたら
`git reset --hard` で取り込み、依存とsystemdユニットを反映して `tarot-mai-bot` を再起動する
（[`auto-update.sh`](auto-update.sh)）。更新が無ければ何もしない。プル型なので受信ポートも
外部への鍵預けも不要。**`main` にマージした内容がそのまま本番へ反映される**ので、`main` は
常にデプロイ可能な状態に保つこと（作業は `develop`／PR経由・AGENTS.md §7）。

### 一時的に自動更新を止める / 手で更新する

```bash
sudo systemctl disable --now tarot-mai-update.timer     # 自動更新を止める
sudo systemctl start tarot-mai-update.service           # いますぐ1回だけ更新チェック
```

---

## 運用メモ

- **更新**: `develop → main` を PR でマージするだけ。あとは `tarot-mai-update.timer` が
  5分以内に取り込んで Bot を再起動する。急ぎで反映したいときは
  `sudo systemctl start tarot-mai-update.service` を1回叩く。
- **止める**: `sudo systemctl stop tarot-mai-bot`。定期投稿は `... stop tarot-mai-daily.timer`。
- **ログ**: 同居しているBotと journald を共有している。`journalctl -t tarot-mai-bot` /
  `-t tarot-mai-daily` / `-t tarot-mai-update` で自分の分だけ見られる。
  常駐中は相談が無ければ1時間に1行しか書かない（他のBotのログを押し出さないため）。
- **状態ファイル**: `bot/state/state.json` は消さない（消すと過去メンションを再処理しうる）。
- **preemption からの復帰**: 上の「自動で起こす仕組み」を参照。応答が途絶えたら、
  まず `gcloud compute instances describe misskey-bots-unified --format="value(status)"` で
  VMが `TERMINATED` になっていないかを見る（Bot の不具合ではなく preemption のことがある）。
- **コスト**: 共用VMの持ち分＋Claude API 従量（1回 ≒ $0.03〜0.08、bot/README.md 参照）。
- **鍵の失効**: トークン/キーを更新したら `.env` を差し替えて Bot を再起動する。
