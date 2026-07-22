# 錦野舞のタロット執務室 🔮

セブンティエイト特殊探偵団の采配幹部「錦野舞（Dealer No.79）」が、タロット占いをしてくれる執務室です。
Claudeプロジェクトのコンテキストフォルダとして使います。

## 使い方

このフォルダをコンテキストに設定した状態で、舞に話しかけるだけ。
「占ってほしいことがある」「今日の運勢を見て」などと伝えると、舞が手順に沿って占ってくれます。

## フォルダ構成

```
Tarot-byFateLineDealer/
├── roleplay.instructions.md       … 正本①：錦野舞のキャラクター設定（SSOT）
├── AGENTS.md                      … 正本②：執務室の運用ルール（SSOT）／Codex の入口
├── CLAUDE.md                      … Claude 用の入口（@ で正本①②をインポート）
├── .claude/settings.json          … Claude に毎ターン正本を再通知するフック設定
├── .github/copilot-instructions.md … Copilot 用の入口（正本①②へリンク参照）
├── .vscode/settings.json          … Copilot に正本を読み込ませる設定
├── data/
│   ├── tarot-deck.md              … 78枚の正逆キーワード
│   └── spreads.md                 … スプレッド（展開法）一覧
├── assets/cards-rws/              … 仮登録したRWS原作画像78枚
├── procedures/
│   ├── reading-procedure.md       … 舞の占い手順
│   ├── shuffle.py                 … 乱数で公正にカードを引くスクリプト
│   └── render_spread.py           … 引いたカードを陣形のまま1枚に合成する
├── bot/                           … Misskey Bot（4つ目の入口・実行時に正本を読む）
└── readings/                      … 占い結果の保存先（任意）
```

## カードを自分で引いてみる

```bash
python3 procedures/shuffle.py --count 3          # 3枚引き
python3 procedures/shuffle.py --spread celtic    # ケルト十字（10枚）
python3 procedures/shuffle.py --count 1 --upright-only   # 正位置のみ1枚
python3 procedures/shuffle.py --count 3 --json           # 画像パス付きJSON
```

陣形のまま1枚の画像に合成することもできます（カード画像の出典表記が自動で焼き込まれます）。

```bash
python3 procedures/render_spread.py --draw --spread celtic \
  --json-out readings/celtic.json --title "ケルト十字 — （相談テーマ）" \
  --out readings/celtic.png
```

## Misskey Bot として動かす

`bot/` は、この執務室の **4つ目の入口**です。Misskey で舞にメンションすると、
抽選 → 陣形画像の生成 → Claude API での読み解き → 画像つき返信、までを自動で行います。

```powershell
# リポジトリのルートで実行すること（bot/ の中からは動きません）
py -m pip install -r bot/requirements.txt
py -m bot.main --check             # 疎通確認（投稿もAPI課金もしない）
py -m bot.main --simulate "相談文"  # メンションを待たずに読み解きだけ試す
py -m bot.main --once --dry-run    # 実際のメンションを1件だけ処理して確認（既定）
py -m bot.main --live              # 常駐して実投稿
```

準備（Bot アカウント・トークンの権限・`.env`）とデプロイ手順は
[`bot/README.md`](bot/README.md)、運用ルールは [`AGENTS.md`](AGENTS.md) §6 にあります。

- **投稿は既定で dry-run**。実投稿には `--live` の明示指定が要ります。
- Bot も正本を**実行時に読み込みます**。`roleplay.instructions.md` を書き換えれば応答も変わります
  （反映には再起動が必要）。設定内容を `bot/` にコピーしていません。

## ブランチ運用

| ブランチ | 役割 |
| --- | --- |
| **`origin/main`** | **リモートのメインブランチ。Misskey Bot のデプロイ元。** |
| `develop` | 統合ブランチ。作業ブランチをマージコミットで積む |
| `feat/…` `fix/…` `chore/…` | 作業ブランチ |

**`origin/main` へは直接 push しません。** `develop` から `main` への反映はプルリクエストで行います
（`gh pr create --base main --head develop`）。Bot のサーバは `origin/main` を追うため、
main へのマージがそのまま本番への反映になります。詳細は [`AGENTS.md`](AGENTS.md) §7。

## メモ

- タロット解釈はライダー・ウェイト・スミス版（パブリックドメイン）の伝統的キーワードに基づく一般知識です。
- 現在のカード画像は仮素材です。出典・権利情報は `assets/cards-rws/README.md` を参照してください。
- 占いロジックとデータはプロジェクト直下を正本とし、Claude / GitHub Copilot / Codex / Misskey Bot のいずれからも利用します。
- 指示の正本は `roleplay.instructions.md`（キャラクター設定）と `AGENTS.md`（運用ルール）の2つだけです。
  各エージェントの入口ファイルは参照のみで、内容を複製していません。設定変更は正本の2ファイルに行ってください。
- 正本①の読み込み手順は `AGENTS.md` の「0. STEP 0」にまとめてあります。Claude では加えて、
  `.claude/settings.json` の `UserPromptSubmit` フックが毎ターン「正本の場所」だけを再通知します
  （キャラクター本文は複製していません）。不要なら同ファイルの `hooks` を削除してください。
- 占いはあくまで気持ちを整理するための手がかりです。重大な決断は専門家にもご相談を。
