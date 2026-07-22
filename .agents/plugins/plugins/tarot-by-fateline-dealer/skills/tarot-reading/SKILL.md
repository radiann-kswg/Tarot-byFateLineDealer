---
name: tarot-reading
description: Use when the user asks for a tarot reading in the 錦野舞のタロット執務室 workspace. Keeps the shared project files as the source of truth and uses the project's cryptographically random draw script.
---

# Tarot Reading Adapter

This is a thin Codex adapter. Do not duplicate the deck, character, spread, or reading data inside this plugin.

1. Locate the active workspace root containing `roleplay.instructions.md` and `procedures/shuffle.py`.
2. Read `roleplay.instructions.md` (character SSOT), `AGENTS.md` (office rules and reading principles SSOT), `procedures/reading-procedure.md`, `data/spreads.md`, and the relevant entries in `data/tarot-deck.md`.
3. Follow `procedures/reading-procedure.md` exactly. The workspace files are authoritative over this adapter.
4. Draw cards only by running `procedures/shuffle.py`. Use `--json` when card images will be displayed.
5. Resolve each returned `image` path relative to the workspace root. For reversed cards, rotate only in the presentation layer or label the orientation; do not edit the source image.
6. Choose how to present card images by card count:
   - **One-card (one oracle):** show the single card image as-is.
   - **Three or more cards (three-card / hexagram / celtic):** do not show cards one by one. Compose the whole spread into a single formation image with `procedures/render_spread.py`, piping the `shuffle.py --json` output straight in (reversed cards auto-rotate 180°, and the celtic ② is drawn crossing ①).

   ```bash
   python procedures/render_spread.py --draw --spread celtic \
     --json-out readings/celtic.json --title "ケルト十字 — (theme)" \
     --out readings/celtic.png
   ```
   `--draw` calls the shared `shuffle.py` functions rather than adding another card-selection
   implementation. Prefer it on Windows because PowerShell can corrupt UTF-8 JSON in a native
   command pipeline. Read `--json-out` for the exact cards to interpret. On Unix, piping
   `shuffle.py --json` into the renderer remains supported.
   In Codex Desktop, use the bundled workspace Python when `python` is not on `PATH`.
   Show the resulting PNG with an absolute local Markdown image path so the app renders it inline.
7. Keep readings in conversation unless the user explicitly asks to save one under `readings/`.
8. If the shared files cannot be found, explain that this adapter requires the Tarot-byFateLineDealer workspace and do not invent replacement data.
