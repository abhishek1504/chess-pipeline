---
stepsCompleted: []
inputDocuments:
  - _bmad-output/specs/spec-chess-analysis/SPEC.md
  - _bmad-output/planning-artifacts/architecture/architecture-chess-pl-2026-09-03/ARCHITECTURE-SPINE.md
---

# chess-pl — Chess Analysis Pipeline: Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for the Chess Game Analysis and Improvement Engine, decomposing requirements from SPEC.md and ARCHITECTURE-SPINE.md into implementable stories.

## Requirements Inventory

### Functional Requirements

FR1: The analysis pipeline fetches the last N lost games by time control directly from chess.com and stores them durably with full PGN and metadata.
FR2: Stored games are queryable by date, time control, result, and opponent rating; no game in the configured window is silently dropped.
FR3: Each stored game yields a labeled list of significant mistakes (blunders and errors) with move number, severity classification, and the Stockfish-preferred alternative move.
FR4: For every analyzed game, blunders (≥2 pawn evaluation swing) and mistakes (≥1 pawn) are listed with the correct move; results are queryable per game.
FR5: Mistakes across all stored games are grouped into recurring weakness categories with frequency counts and representative example positions.
FR6: A generated report names at least the top 3 recurring weakness categories with frequency counts and one example position per category.
FR7: Aggregated weakness patterns are passed to Claude, which produces a prioritized study plan as a static report with named topics and actionable exercises traceable to specific weakness categories.
FR8: The report names at least 3 study topics ranked by rating impact, each with a concrete exercise or resource and a reference to the weakness pattern that motivated it; the report is written to file after each analysis run.

### NonFunctional Requirements

NFR1: Analysis failures must not block video generation or YouTube upload — the analysis pipeline is a separate workflow with no dependency on the video pipeline.
NFR2: The analysis pipeline fetches its own lost games; it does not read from `won_games.json` or the video pipeline's quality filter.
NFR3: Stockfish engine integration is required for per-move evaluation; chess.com API does not provide per-move accuracy data.
NFR4: Analysis runs automatically on its own daily schedule; game window size (N) and time control are env-var parameters (ANALYSIS_GAME_COUNT default 20, ANALYSIS_TIME_CONTROL default rapid).

### Additional Requirements

- AR1: AWS RDS PostgreSQL is the sole persistent store; Python psycopg2-binary driver required (AD-1).
- AR2: Standalone GitHub Actions workflow `chess_analysis.yml` — no dependency on `chess_pipeline.yml` (AD-2).
- AR3: Fetch stage calls chess.com API for lost games filtered by configured time control (AD-3).
- AR4: `ANALYSIS_GAME_COUNT` (default 20) and `ANALYSIS_TIME_CONTROL` (default rapid; valid: rapid, blitz, bullet) are GitHub Actions env vars (AD-4).
- AR5: Single Claude API call — Python aggregates Stockfish output into structured dict → one prompt → one response → report file (AD-5).
- AR6: Reports stored at `s3://{S3_BUCKET}/{username}/{time_control}/{date}.md`; same-day re-runs overwrite (AD-6).
- AR7: Per-game Stockfish failure: try/except per game, log game_id + exception, skip game, continue run (AD-7).
- AR8: Three-table schema — `games(id, username, pgn, date, time_control, result, opponent_rating, fetched_at)`, `evaluations(id, game_id, move_number, severity, best_move, eval_delta)`, `reports(id, username, time_control, window_size, s3_path, generated_at)`; evaluations filtered by joining to games on game_id (AD-8).
- AR9: `eval_delta` = centipawns lost by player (eval_before − eval_after); blunder ≥ 200cp, mistake ≥ 100cp; non-blunder moves not stored.
- AR10: Stage-level failures (chess.com fetch, RDS write, S3 upload) abort run with non-zero exit; no retry.
- AR11: GitHub Secrets required: `DB_URL`, `S3_BUCKET`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `ANTHROPIC_API_KEY`, `CHESS_USERNAME`.
- AR12: Source tree: `analysis/fetch_games.py`, `analysis/stockfish_analyze.py`, `analysis/aggregate.py`, `analysis/generate_report.py`, `analysis/db/schema.sql`, `analysis/db/client.py`, `.github/workflows/chess_analysis.yml`.

### UX Design Requirements

N/A — pure backend pipeline with no user-facing UI.

### FR Coverage Map

{{requirements_coverage_map}}

## Epic List

{{epics_list}}
