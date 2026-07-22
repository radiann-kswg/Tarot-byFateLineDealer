"""錦野舞のタロット執務室 — Misskey Bot。

この執務室の4つ目の入口。Claude / Copilot / Codex が「指示ファイルを読む LLM ホスト」なのに対し、
Bot は自分で Claude API を呼ぶ常駐プログラムだが、扱いは同じ:
**正本の内容をここに複製せず、実行時に読み込む**（AGENTS.md §5 編集ルール・§6）。

- キャラクター設定を変える → roleplay.instructions.md
- 運用ルール・定型文を変える → AGENTS.md（特に §6）
- 占いの中身を変える → procedures/ と data/
"""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

__all__ = ["PROJECT_ROOT"]
