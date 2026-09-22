<!-- bmad:context -->
<!-- Verified 2026-09-03 against cd2a4de. Managed by bmad-project-context; edits inside this block are replaced on refresh. Keep anything you want preserved outside the markers. -->

## chess-pl

Automated pipeline: chess.com wins → videos → YouTube. Python 3.11, ffmpeg, chess.com API, YouTube Data API v3, Anthropic API. No dedicated docs folder yet.

## Policy

- Never reset or modify `uploaded_games.json` without explicit instruction — it is the live upload history; silent loss is unrecoverable without re-syncing YouTube.
- Never touch `step1b_*`, `step1c_*`, `step1d_*`, or `step2b_*` files — origin and intent are unknown; leave them alone unless explicitly asked.
- Never develop `step4_post_instagram.py` or `step4_tts_voiceover.py` — abandoned; do not work on them unless asked.
- Never commit `client_secrets.json`, `youtube_token.json`, or `youtube_token.pickle`.

## Where things are

- Daily entry: `watcher.py` (last 24h wins); historical: `backfill.py <year> <month>`
- Pipeline sequence: `watcher.py → step2_generate_video.py → step3_generate_scripts.py → step5_upload_youtube.py`
- Upload log: `uploaded_games.json` (committed — source of truth for what's been uploaded)

## Running and verifying

- Backfill CI workflows are disabled — run backfill locally, never via CI.

<!-- /bmad:context -->
