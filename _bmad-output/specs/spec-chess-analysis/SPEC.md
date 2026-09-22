---
id: SPEC-chess-analysis
companions:
  - ../../planning-artifacts/architecture/architecture-chess-pl-2026-09-03/ARCHITECTURE-SPINE.md
sources: []
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# Chess Game Analysis and Improvement Engine

## Why

The pipeline fetches chess.com wins and converts them to videos, then discards all game data. The game data is the primary raw material for improving chess rating. This builds a parallel analysis layer that fetches lost games independently, evaluates positions with Stockfish, surfaces recurring weaknesses, and delivers a concrete, prioritized study plan to drive measurable rating improvement.

## Capabilities

- **CAP-1**
  - **intent:** The analysis pipeline fetches the last N lost games by time control directly from chess.com and stores them durably with full PGN and metadata, queryable by date, time control, result, and opponent rating.
  - **success:** After any analysis run, the configured window of lost games is retrievable with complete move data and metadata; no game in the window is silently dropped from the store.

- **CAP-2**
  - **intent:** Each stored game yields a labeled list of significant mistakes — blunders and errors — with move number, severity classification, and the Stockfish-preferred alternative move.
  - **success:** For every analyzed game, blunders (≥2 pawn evaluation swing) and mistakes (≥1 pawn) are listed with the move that should have been played; results are queryable per game.

- **CAP-3**
  - **intent:** Mistakes across all stored games are grouped into recurring weakness categories (e.g., tactical blindspots, endgame piece activity, opening deviations) with frequency counts and representative example positions.
  - **success:** A generated report names at least the top 3 recurring weakness categories with frequency counts and one example position per category.

- **CAP-4**
  - **intent:** Aggregated weakness patterns are passed to Claude, which produces a prioritized study plan as a static report with named topics and actionable exercises traceable to specific weakness categories.
  - **success:** The report names at least 3 study topics ranked by impact on rating, each with a concrete exercise or resource and a reference to the weakness pattern that motivated it; the report is written to a file after each analysis run.

## Constraints

- Analysis failures must not block video generation or YouTube upload — the analysis pipeline is a separate workflow with no dependency on the video pipeline.
- The analysis pipeline has its own chess.com fetch for lost games; it does not read from `won_games.json` or the video pipeline's quality filter.
- Stockfish engine integration is required for per-move evaluation; chess.com API does not provide per-move accuracy data.
- Analysis runs automatically on its own daily schedule; N (game window size) and time control are env-var parameters.

## Non-goals

- Real-time move suggestions during a live game.
- Analysis of games from platforms other than chess.com.
- Comparison or ranking against other players.
- Automated publishing of analysis results to YouTube or social media.
- Conversational interface for the improvement plan (static report is the target output; conversation is future scope).
- Semantic position-similarity search across game history (vector DB not required; structured aggregation by mistake category is sufficient).

## Success signal

After one month of daily runs, the study plan report names specific recurring weaknesses tied to observed Stockfish evaluations across the stored game window, and at least one recommendation is verifiably tied to a blunder pattern appearing in 3 or more games. Chess rating trend is trackable against the plan's focus areas.

## Assumptions

- Analysis covers games by username `abhi15041984` only.
