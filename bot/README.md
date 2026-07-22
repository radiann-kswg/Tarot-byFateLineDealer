# 錦野舞のタロット執務室 — Misskey Bot

メンションに応じて占い、陣形画像つきで返信する常駐プログラムです。
この執務室の **4つ目の入口**にあたります（Claude / GitHub Copilot / Codex に続く）。

**運用ルールの正本は [`AGENTS.md`](../AGENTS.md) §6 です。** このファイルには起動・デプロイの手順だけを書きます。
舞の口調や占いの原則、定型文をここに複製しないでください。

---

## しくみ

```
[Misskey ユーザー] ──@メンション──▶ [Misskey サーバー]
                                        │ i/notifications をポーリング
                                        ▼
                                  [bot/main.py]
   1. 通知取得・重複排除・クールダウン      state.py
   2. 安全性スクリーニング                 safety.py   ← 該当時は占わず定型応答へ
   3. スプレッド決定（キーワード or 舞が選ぶ） tarot.py
   4. 抽選＋陣形画像生成                   tarot.py    ← procedures/ をそのまま import
   5. システムプロンプト組み立て            ssot.py     ← 正本を実行時に読む
   6. Claude Messages API で読み解き生成    reading.py
   7. drive/files/create → notes/create    misskey.py
```

**抽選と読み解きは分離してあります。** カードは `procedures/shuffle.py`（`secrets` による暗号学的乱数）で引き、
Claude には「もう引かれたカード」を渡すだけです。Claude にカードを選ばせません（AGENTS.md §4-1・§4-6）。

`bot/ssot.py` は正本を**実行時に読み込み**ます。`roleplay.instructions.md` を書き換えれば Bot の応答も変わります
（反映には再起動が必要）。

| ファイル | 役割 |
| --- | --- |
| `main.py` | メンション応答ループ |
| `daily.py` | 「今日の一枚」定期投稿 |
| `ssot.py` | 正本の読み込み・システムプロンプト組み立て・定型文の取り出し |
| `tarot.py` | スプレッド決定・抽選・陣形画像生成（`procedures/` を import） |
| `reading.py` | Claude Messages API |
| `misskey.py` | Misskey API |
| `safety.py` | 相談内容のスクリーニング（判定のみ。文面は AGENTS.md §6.3） |
| `state.py` | 既読通知ID・クールダウン・記録保存 |
| `config.py` | `.env` の読み込みと検証 |

---

## フェーズ0：準備

### 1. Misskey Bot アカウント

- どのインスタンスで動かすか決める（自鯖 / 既存アカウントのある鯖）
- Bot 用アカウントを作り、**設定でボットフラグ（`isBot`）を有効化**する
- プロフィール文に、錦野舞としてタロット占いを行うこと・**占いは娯楽であり気持ちを整理するための
  手がかりであること**を明記する（AGENTS.md §6.4）

### 2. アクセストークンの発行

設定 → API → アクセストークンの手動発行。**必要な権限は次の4つだけ**で、他はすべて外してください。

| 権限 | 用途 |
| --- | --- |
| アカウントの情報を見る | `--check` の疎通確認（`i`） |
| 通知を見る | メンションを拾う（`i/notifications`） |
| ノートを作成・削除する | 返信・定期投稿（`notes/create`） |
| ドライブを操作する | 陣形画像のアップロード（`drive/files/create`） |

### 3. Anthropic API キー

<https://platform.claude.com/> で発行し、使用量アラート／上限を設定してください。

### 4. `.env` の作成

置き場所は**リポジトリ直下と `bot/` のどちらでも構いません**（この順に探します）。

```bash
cp bot/.env.example .env        # リポジトリ直下
# または
cp bot/.env.example bot/.env    # テンプレートの隣
```

値の意味は `bot/.env.example` のコメントを読んでください。**`.env` はコミットしないこと**
（どちらの場所でも `.gitignore` 済み）。Linux では `chmod 600` を推奨します。

どちらを読み込んだかは `--check` の1行目に出ます。

```
2026-07-22 13:30:00 INFO 設定の読み込み元: D:\...\Tarot-byFateLineDealer\bot\.env
```

> **占い結果は CW（内容注意）で畳んで投稿されます**（`MISSKEY_FOLD_READING=1`、既定で有効）。
> 見出しの文面は `AGENTS.md` §6.3 の `cw-reading` にあります。
> **自傷検知時の応答・ロールプレイ停止・おわびの定型文は、この設定にかかわらず畳みません。**
> つらいときや不具合のときに、ワンクリック挟ませないためです（AGENTS.md §6.1-3）。

> ⚠️ `SUPPORT_RESOURCE_URL` は、自傷・他害を検知したときの定型応答に差し込まれ、
> **公開投稿へそのまま載ります。** 既定は厚生労働省「まもろうよ こころ」ですが、
> 運用前に必ずリンク先を開いて内容を確認してください。

---

## 実行環境の要件

| 項目 | 要件 |
| --- | --- |
| Python | 3.11 以上 |
| 依存 | `pip install -r bot/requirements.txt` |
| **日本語フォント** | 無いと陣形画像の生成が `RuntimeError` で失敗します（下記） |
| ネットワーク | Misskey インスタンスと `api.anthropic.com` への外向き HTTPS |

### 日本語フォント

`procedures/render_spread.py` は日本語フォントを OS 既定の候補から探します。

- **Windows**：`YuGothR.ttc` / `meiryo.ttc` が候補に入っているのでそのまま動きます
- **Linux**：**`fonts-noto-cjk` の導入が必須**です

```bash
sudo apt install -y fonts-noto-cjk
```

見つからない場合は `TAROT_SPREAD_FONT` に `.ttf` / `.ttc` の絶対パスを指定してください。

---

## 起動と動作確認

> ⚠️ **必ずリポジトリのルートで実行してください。**
> `python -m bot.main` は `bot/` の**親ディレクトリ**が `sys.path` に必要なので、
> `cd bot` した状態では `ModuleNotFoundError: No module named 'bot'` になります。

Windows のこの環境では、PATH 上の `python` は Microsoft Store のスタブなので
**`py` ランチャー**を使ってください。

```powershell
cd "d:\Claude Coworks Projectfile\Tarot-byFateLineDealer"   # ← ルートで実行する
py -m pip install -r bot/requirements.txt

py -m pytest procedures/ bot/ -q          # テスト
py -m bot.main --check                    # 疎通確認（投稿もAPI課金もしない）
py -m bot.main --simulate "相談文"         # メンションを待たずに読み解きだけ試す
py -m bot.main --once --dry-run           # 通知を1件だけ処理して結果を標準出力
py -m bot.main --once --live              # 1件だけ実投稿
py -m bot.main --live                     # 常駐

py -m bot.daily --dry-run                 # 今日の一枚（確認）
py -m bot.daily --live                    # 今日の一枚（投稿）
```

Linux / macOS では `py` を `.venv/bin/python` などに読み替えてください。

### コマンドライン引数

| 引数 | 意味 |
| --- | --- |
| `--check` | Misskey と Anthropic の疎通確認だけ行う。投稿もAPI課金もしない |
| `--simulate "相談文"` | メンションを待たずに、その相談文で読み解きだけ試す。**Misskey には接続しない**（通知も読まない・投稿もしない）。Claude API は呼ぶので課金あり |
| `--spread NAME` | `--simulate` でスプレッドを指定（`one` / `two` / `three` / `hexagram` / `celtic`）。省略時は舞が選ぶ |
| `--dry-run` | **既定。** 投稿せず、返信本文と画像パスを標準出力に出す |
| `--live` | 実際に投稿する。明示指定が必要 |
| `--once` | 1回だけポーリングして終了 |
| `--limit N` | 1回のポーリングで取得する通知の最大件数（既定 10） |
| `--catch-up` | 初回起動時に既存の通知にも応答する（既定は応答しない） |

> **初回起動はバックログに返信しません。** 何もしないと過去のメンション全部に返信してしまうためです。
> 溜まっている通知にも応答したいときだけ `--catch-up` を付けてください。

> **dry-run は通知を既読にしません。** サーバ側を書き換えないよう `markAsRead` を落とし、
> 状態ファイルも進めません。そのぶん Claude API は実際に呼ぶので**課金は発生します**。
> 課金なしで確かめたいときは `--check` を使ってください。

> **`0 件処理しました` と出るのは正常な場合があります。** Bot 宛の `mention` / `reply` の通知が
> 無いときはこれが出ます（`follow` や `login` の通知は対象外）。
> 別アカウントから Bot にメンションしてから、もう一度実行してください。
> メンションを待たずに読み解きだけ確かめたいときは `--simulate` を使います。

---

## ロールアウト（段階的に外へ出す）

投稿は公開・不可逆なので、いきなり `--live` の常駐にしないでください。

| # | コマンド | 確認すること |
| --- | --- | --- |
| 1 | `--check` | トークンの権限が足りているか。`isBot` が立っているか |
| 2 | `--simulate "相談文"` | 抽選・画像・読み解き文が意図通りか。画像に出典2行が入っているか |
| 3 | `--once --dry-run` | 実際のメンションを拾えるか（**先に別アカウントから Bot 宛メンションを送っておくこと**） |
| 4 | `--once --live`（`MISSKEY_VISIBILITY=home`） | 投稿・画像添付・リプライ先が正しいか |
| 4 | `--live` 常駐（`home` のまま数日） | 重複返信がないか。クールダウンが効いているか |
| 5 | `MISSKEY_VISIBILITY=public` に変更 | 公開範囲を広げる |
| 6 | `bot.daily` を timer / タスクに登録 | 定期投稿が1日1回だけ走るか |

---

## デプロイ

### A. ローカル常駐（Windows）

タスクスケジューラに「コンピューターの起動時」トリガーで登録します（要管理者権限）。

```powershell
$py     = "C:\Users\s-chi\AppData\Local\Python\bin\python.exe"
$repo   = "d:\Claude Coworks Projectfile\Tarot-byFateLineDealer"
$action = New-ScheduledTaskAction -Execute $py -Argument "-m bot.main --live" -WorkingDirectory $repo
$trig   = New-ScheduledTaskTrigger -AtStartup
$set    = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5) `
                                       -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName "TarotMaiBot" -Action $action -Trigger $trig -Settings $set
```

「今日の一枚」は別タスクとして `-m bot.daily --live` を毎朝のトリガーで登録してください。

> PC がスリープ・シャットダウンすると止まります。24時間応答させたいなら VPS を選んでください。

### B. VPS / Linux（本番向け）

**デプロイ元は `origin/main` です**（AGENTS.md §7）。`develop` や作業ブランチを直接デプロイしないでください。

```bash
git clone -b main https://github.com/radiann-kswg/Tarot-byFateLineDealer.git /opt/tarot-mai
cd /opt/tarot-mai
sudo apt install -y python3-venv fonts-noto-cjk
python3 -m venv .venv && .venv/bin/pip install -r bot/requirements.txt
cp bot/.env.example .env && chmod 600 .env   # 値を埋める
.venv/bin/python -m bot.main --check
```

systemd ユニットは [`deploy/`](deploy/) に置いてあります。

```bash
sudo cp bot/deploy/tarot-mai-bot.service /etc/systemd/system/
sudo cp bot/deploy/tarot-mai-daily.service /etc/systemd/system/
sudo cp bot/deploy/tarot-mai-daily.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tarot-mai-bot
sudo systemctl enable --now tarot-mai-daily.timer
sudo journalctl -u tarot-mai-bot -f
```

配置先（`/opt/tarot-mai`）と実行ユーザー（`tarot`）は環境に合わせて書き換えてください。

### C. Docker

```bash
docker build -f bot/deploy/Dockerfile -t tarot-mai .
docker run -d --name tarot-mai --restart unless-stopped \
  --env-file .env \
  -v tarot-mai-state:/app/bot/state \
  -v tarot-mai-readings:/app/readings \
  tarot-mai
```

秘密情報はイメージに焼かず `--env-file` で渡します。`bot/state/` はボリュームで永続化してください
（消すと過去の通知を再処理する可能性があります）。

### D. サーバーレス

メンション応答は常駐が前提なので、ポーリング方式とは相性がよくありません。
「今日の一枚」だけなら cron 相当のスケジューラで `bot.daily` を1日1回叩く形は成立しますが、
トークンとAPIキーを実行環境のシークレットに預けることになります。
**リポジトリが公開かどうかを確認してから**判断してください。

---

## 運用

- **重複投稿の防止**：応答済みの通知IDを `bot/state/state.json` に永続化しています。
  プロセスが落ちて再起動しても同じメンションに二度返信しません。
  **このファイルを消すと過去の通知を再処理する可能性がある**ので消さないでください。
- **止めたいとき**：`sudo systemctl stop tarot-mai-bot`（Windows はタスクの終了）。
  一時的に無害化するだけなら `--live` を外して `--dry-run` に戻します。
- **ログ**：標準出力に出るので `journalctl -u tarot-mai-bot` で読めます。
  1件の占いごとに、通知ID・スプレッド・引いたカード・トークン使用量が1行で出ます。
- **正本を更新したとき**：`git pull` のあと **Bot の再起動が必要**です
  （システムプロンプトは起動時に組み立てて使い回すため）。
- **更新の流れ**：作業ブランチ → `develop` → **プルリクエストで `origin/main`** → サーバで `git pull` → 再起動。
  `origin/main` へ直接 push しないでください（AGENTS.md §7.2）。main へのマージがそのまま本番への反映になります。

### コスト感

`claude-opus-4-8` は入力 $5 / 出力 $25 per 1M トークン。
システムプロンプトの安定部は **約 14,900 文字**（実測値。内訳は正本① 3.7k / 正本② 6.6k /
手順書 2.7k / スプレッド資料 1.3k）で、これが毎回の入力に乗ります。

実測例（スリーカード1回・キャッシュミス時）。ログにこの値が出ます。

```
INFO スプレッド=スリーカード(...) カード=... / in=491 out=753 cache_read=0 cache_write=12391
```

- 入力 12,882 トークン（安定部 12,391 ＋ 可変部 491）× $5/1M ≒ **$0.064**
- 出力 753 トークン × $25/1M ≒ **$0.019**
- 合計 **≒ $0.08 / 回**

キャッシュが効けば安定部が 1/10 の単価になるので、**$0.03 前後**まで下がります。
枚数の多いスプレッドは出力が伸びるぶん少し高くなります。

プロンプトキャッシュの既定TTLは5分なので、**低頻度の Bot ではほとんどのリクエストが
キャッシュミスになります**（`cache_read=0`・`cache_write` に全量）。連投がある時間帯にだけ効く、
と考えてください。コストを下げたいときは `ANTHROPIC_EFFORT=low` が第一手です。

`cache_read` が**連投時でも**常に 0 のままなら、システムプロンプトの安定部に
実行時の値（日時など）が混ざっている疑いがあります。

---

## トラブルシューティング

| 症状 | 原因と対処 |
| --- | --- |
| `ModuleNotFoundError: No module named 'bot'` | `bot/` の中で実行している。**リポジトリのルートに戻って**から `py -m bot.main ...` |
| `0 件処理しました` が続く | Bot 宛の `mention` / `reply` 通知が無いだけ。別アカウントからメンションを送る。読み解きの確認は `--simulate` |
| `必須の環境変数が設定されていません` | エラー本文に「探した場所」か「読み込んだファイル」が出ます。前者なら `.env` の置き場所（リポジトリ直下か `bot/`）、後者なら値の空欄・キー名の綴りを確認 |
| `陣形画像の生成に失敗しました` | 日本語フォントが無い。`fonts-noto-cjk` を入れるか `TAROT_SPREAD_FONT` を指定 |
| `i/notifications が 401 を返しました` | トークンが無効。権限4つが付いているか確認 |
| `drive/files/create が 403` | 「ドライブを操作する」権限が付いていない |
| `モデル ... が見つかりません` | `ANTHROPIC_MODEL` の綴り、またはキーの権限を確認 |
| 過去のメンションに一斉返信した | `--catch-up` を付けたまま起動した。状態ファイルを確認 |
| 同じ人に何度も返信する | `USER_COOLDOWN_SECONDS` を延ばす。`bot/state/state.json` が消えていないか確認 |
