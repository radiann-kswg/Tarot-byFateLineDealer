---
name: tarot-reading
description: Use when the user asks for a tarot reading in the 錦野舞のタロット執務室 (Tarot-byFateLineDealer) workspace. Keeps the shared project files as the source of truth and draws cards only with the project's cryptographically random shuffle script.
---

# 錦野舞のタロット占い アダプター（Claude用）

これは薄いアダプターです。デッキ・キャラクター・スプレッド・読み解きのデータをこのスキル内に複製しないでください。正本は常にワークスペース側のファイルです。

1. `roleplay.instructions.md` と `procedures/shuffle.py` を含むワークスペースのルートを特定する。
2. 次を読み込む：`roleplay.instructions.md`（キャラクター設定・正本①）、`AGENTS.md`（執務室の運用ルールと占いの原則・正本②）、`procedures/reading-procedure.md`（占いの手順）、`data/spreads.md`（スプレッド）、`data/tarot-deck.md` の該当カード。
3. `procedures/reading-procedure.md` の手順に厳密に従う。ワークスペースのファイルがこのアダプターより優先される。
4. カードは必ず `procedures/shuffle.py` を実行して引く。恣意的に選ばない。カード画像を提示するときは `--json` を使う。

   ```bash
   # ワンオラクル
   python3 procedures/shuffle.py --count 1

   # スリーカード（画像パス付きJSON）
   python3 procedures/shuffle.py --count 3 --json

   # スプレッド指定：one / three / hexagram(7) / celtic(10)
   python3 procedures/shuffle.py --spread celtic --json

   # 正位置のみ
   python3 procedures/shuffle.py --count 3 --upright-only
   ```

5. 返ってきた各 `image` パスはワークスペースのルート基準で解決する（例：`assets/cards-rws/m00.jpg`）。逆位置は表示側で180度回転するか本文に「逆位置」と明記し、元画像は編集しない。
6. カード画像の提示は枚数で切り替える：
   - **ワンオラクル（1枚）**：カード画像を1枚そのまま提示する。
   - **3枚以上（スリーカード／ヘキサグラム／ケルト十字）**：1枚ずつではなく、`procedures/render_spread.py` で陣形のまま1枚に合成した全体画像を提示する。`shuffle.py --json` の出力をそのまま渡せばよい（逆位置は自動で180°回転、ケルト十字の②は①に交差）。

   ```bash
   python3 procedures/shuffle.py --spread celtic --json \
     | python3 procedures/render_spread.py --spread celtic \
         --title "ケルト十字 — （相談テーマ）" --out /tmp/spread.png
   ```
7. 読み解きは会話内に留める。ユーザーが明示的に希望したときだけ `readings/` に日付つきで保存する。
8. 共有ファイルが見つからない場合は、このアダプターが Tarot-byFateLineDealer ワークスペースを必要とする旨を説明し、代替データを捏造しない。

## 占いの原則（厳守）

原則の正本はワークスペースの `AGENTS.md`「4. 占いの原則」です。ここには複製せず、必ずそちらを読んで従ってください。
特に、結果をねじ曲げないこと・重大な決断は断定せず専門家への相談も促すこと・未公開設定を自動生成しないこと・
「ロールプレイをやめて」と言われたら即座に通常モードへ戻ることは、いかなる場合も外さないでください。
