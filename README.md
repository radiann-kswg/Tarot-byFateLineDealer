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
│   └── shuffle.py                 … 乱数で公正にカードを引くスクリプト
└── readings/                      … 占い結果の保存先（任意）
```

## カードを自分で引いてみる

```bash
python3 procedures/shuffle.py --count 3          # 3枚引き
python3 procedures/shuffle.py --spread celtic    # ケルト十字（10枚）
python3 procedures/shuffle.py --count 1 --upright-only   # 正位置のみ1枚
python3 procedures/shuffle.py --count 3 --json           # 画像パス付きJSON
```

## メモ

- タロット解釈はライダー・ウェイト・スミス版（パブリックドメイン）の伝統的キーワードに基づく一般知識です。
- 現在のカード画像は仮素材です。出典・権利情報は `assets/cards-rws/README.md` を参照してください。
- 占いロジックとデータはプロジェクト直下を正本とし、Claude / GitHub Copilot / Codex のいずれからも利用します。
- 指示の正本は `roleplay.instructions.md`（キャラクター設定）と `AGENTS.md`（運用ルール）の2つだけです。
  各エージェントの入口ファイルは参照のみで、内容を複製していません。設定変更は正本の2ファイルに行ってください。
- 正本①の読み込み手順は `AGENTS.md` の「0. STEP 0」にまとめてあります。Claude では加えて、
  `.claude/settings.json` の `UserPromptSubmit` フックが毎ターン「正本の場所」だけを再通知します
  （キャラクター本文は複製していません）。不要なら同ファイルの `hooks` を削除してください。
- 占いはあくまで気持ちを整理するための手がかりです。重大な決断は専門家にもご相談を。
