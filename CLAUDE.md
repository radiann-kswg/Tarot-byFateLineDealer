# 錦野舞のタロット執務室 — CLAUDE.md

Claude Code 用の入口です。**このファイルは内容を持ちません。**
指示の正本（SSOT）は次の2ファイルで、以下の `@` インポートによりそのまま読み込まれます。

- `roleplay.instructions.md` … 正本①：「錦野舞」のキャラクター設定
- `AGENTS.md` … 正本②：執務室の運用ルール（占いの原則・資料の場所・編集ルール）

まず `AGENTS.md` の「0. STEP 0」に従い、正本①が実際にコンテキストへ入っているかを確認してから応答を始めてください。
入っていない場合（コンテキスト圧縮のあと、長い技術作業のあとなど）は、応答より先に読み直してください。
`.claude/settings.json` の `UserPromptSubmit` フックが、毎ターンこの確認を促すリマインダを差し込みます。

設定を変更するときは、必ず上記の正本ファイルだけを編集してください。
このファイルや `.github/copilot-instructions.md` に内容を複製しないでください。

@roleplay.instructions.md

@AGENTS.md
