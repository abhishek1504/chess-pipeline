"""
STEP 1b — Analyze a Game with Stockfish
The Thinking Athlete Pipeline

Runs every move of a game through Stockfish and produces:
  - A tag per move (Best / Good / Inaccuracy / Mistake / Blunder)
  - Centipawn eval before/after each move + the delta
  - The engine's preferred alternative move
  - A real accuracy score (replaces the heuristic quality score)
  - A shortlist of "key moments" worth commentating

Output: analysis/game_XXX_analysis.json  (+ readable report in terminal)

Requirements:
    brew install stockfish
    pip install chess          # already installed for step2

Usage:
    python step1b_analyze_game.py          # analyzes game 0 from won_games.json
    python step1b_analyze_game.py 3        # analyzes game at index 3
"""

import chess
import chess.pgn
import chess.engine
import json
import io
import os
import sys
import shutil

# ── Config ────────────────────────────────────────────────────────────────────

USERNAME        = "Abhi15041984"   # your chess.com username (same as step2/step3)
TIME_PER_MOVE   = 0.2              # seconds Stockfish thinks per position (0.2 ≈ chess.com quality)
MATE_SCORE      = 10000            # numeric stand-in for "forced checkmate"
EVAL_CLAMP      = 1000             # cap evals at ±10 pawns: "winning is winning",
                                   # so missing a faster mate isn't scored as a blunder
KEY_MOMENT_CP   = 150              # eval swing (in centipawns) that counts as a key moment
MAX_KEY_MOMENTS = 8                # cap so commentary stays tight
OUT_DIR         = "analysis"

# Tag thresholds — centipawns LOST compared to the engine's best move
TAGS = [
    (10,   "Best"),
    (50,   "Good"),
    (100,  "Inaccuracy"),
    (250,  "Mistake"),
    (99999,"Blunder"),
]

# ── Engine helpers ────────────────────────────────────────────────────────────

def find_stockfish():
    path = shutil.which("stockfish")
    if not path:
        print("❌ Stockfish not found. Install it with:  brew install stockfish")
        sys.exit(1)
    return path

def score_cp(info, color):
    """Engine score from the perspective of `color`, as centipawns."""
    return info["score"].pov(color).score(mate_score=MATE_SCORE)

def tag_for(cp_loss):
    for threshold, name in TAGS:
        if cp_loss <= threshold:
            return name
    return "Blunder"

# ── Analysis ──────────────────────────────────────────────────────────────────

def analyze_game(game_data, engine):
    pgn   = chess.pgn.read_game(io.StringIO(game_data["pgn"]))
    board = pgn.board()

    white = pgn.headers.get("White", "?")
    black = pgn.headers.get("Black", "?")
    i_am_white = white.lower() == USERNAME.lower()

    moves_out   = []
    total_loss  = {"me": 0, "opp": 0}
    move_count  = {"me": 0, "opp": 0}

    all_moves = list(pgn.mainline_moves())
    print(f"\n♟️  {white} vs {black} — {len(all_moves)} half-moves")
    print(f"   Thinking {TIME_PER_MOVE}s per move → ~{int(len(all_moves)*TIME_PER_MOVE*2)}s total\n")

    for idx, move in enumerate(all_moves):
        mover      = board.turn                      # chess.WHITE or chess.BLACK
        is_me      = (mover == chess.WHITE) == i_am_white
        move_num   = board.fullmove_number
        san        = board.san(move)
        fen_before = board.fen()

        # What does the engine think BEFORE the move? (also gives us best alternative)
        info_before = engine.analyse(board, chess.engine.Limit(time=TIME_PER_MOVE))
        cp_before   = score_cp(info_before, mover)
        best_move   = info_before.get("pv", [None])[0]
        best_san    = board.san(best_move) if best_move else None

        # Play the move, then evaluate AFTER (still from the mover's perspective)
        board.push(move)
        if board.is_game_over():
            cp_after = MATE_SCORE if board.is_checkmate() else 0
        else:
            info_after = engine.analyse(board, chess.engine.Limit(time=TIME_PER_MOVE))
            cp_after   = score_cp(info_after, mover)

        # Clamp before comparing: +9999 (mate found) vs +500 (still crushing)
        # are both "winning" — the difference shouldn't count as a blunder.
        clamp   = lambda v: max(-EVAL_CLAMP, min(EVAL_CLAMP, v))
        delta   = clamp(cp_after) - clamp(cp_before)
        cp_loss = max(0, -delta)                     # how much worse than staying on track
        tag     = tag_for(cp_loss)
        if best_san == san:
            tag = "Best"

        key = "me" if is_me else "opp"
        total_loss[key] += min(cp_loss, 350)         # cap so one disaster doesn't nuke accuracy
        move_count[key] += 1

        moves_out.append({
            "ply":        idx + 1,
            "move_num":   move_num,
            "player":     "me" if is_me else "opponent",
            "san":        san,
            "fen_before": fen_before,
            "tag":        tag,
            "best_alt":   best_san,
            "cp_before":  cp_before,
            "cp_after":   cp_after,
            "delta":      delta,
            "is_check":     board.is_check(),
            "is_checkmate": board.is_checkmate(),
        })

        marker = {"Blunder": "💥", "Mistake": "❗", "Inaccuracy": "⚠️ ", "Best": "⭐"}.get(tag, "  ")
        print(f"  {marker} {move_num}{'.' if mover == chess.WHITE else '...'} {san:8s} "
              f"[{tag:10s}] eval {cp_before:+5d} → {cp_after:+5d}")

    # ── Accuracy (simple, honest version: average centipawn loss → %) ────────
    def accuracy(key):
        if move_count[key] == 0:
            return None
        avg_loss = total_loss[key] / move_count[key]
        return round(max(0, min(100, 100 - avg_loss / 3.5)), 1)

    # ── Key moments: big swings, blunders by either side, and the finish ─────
    candidates = [
        m for m in moves_out
        if abs(m["delta"]) >= KEY_MOMENT_CP
        or m["tag"] in ("Blunder", "Mistake")
        or m["is_checkmate"]
    ]

    # Collapse runs of consecutive plies into ONE moment (keep the biggest swing
    # of each run) — otherwise a mate sequence eats the whole commentary budget.
    clusters, current = [], []
    for m in candidates:
        if current and m["ply"] == current[-1]["ply"] + 1:
            current.append(m)
        else:
            if current:
                clusters.append(current)
            current = [m]
    if current:
        clusters.append(current)

    key_moments = [
        max(c, key=lambda m: (m["is_checkmate"], abs(m["delta"]))) for c in clusters
    ]

    # Trim to budget by swing size, but the checkmate always survives
    key_moments.sort(key=lambda m: (m["is_checkmate"], abs(m["delta"])), reverse=True)
    key_moments = sorted(key_moments[:MAX_KEY_MOMENTS], key=lambda m: m["ply"])

    return {
        "white": white,
        "black": black,
        "played_as": "White" if i_am_white else "Black",
        "my_accuracy":  accuracy("me"),
        "opp_accuracy": accuracy("opp"),
        "moves": moves_out,
        "key_moments": [m["ply"] for m in key_moments],
    }

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not os.path.exists("won_games.json"):
        print("❌ won_games.json not found — run step1_fetch_games.py or watcher.py first!")
        sys.exit(1)

    with open("won_games.json") as f:
        games = json.load(f)

    game_idx = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    if game_idx >= len(games):
        print(f"❌ Only {len(games)} games in won_games.json (asked for index {game_idx})")
        sys.exit(1)

    engine = chess.engine.SimpleEngine.popen_uci(find_stockfish())
    try:
        result = analyze_game(games[game_idx], engine)
    finally:
        engine.quit()

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"game_{game_idx:03d}_analysis.json")
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\n{'═'*55}")
    print(f"📊 ANALYSIS SUMMARY")
    print(f"{'═'*55}")
    print(f"  You played as:   {result['played_as']}")
    print(f"  Your accuracy:   {result['my_accuracy']}%")
    print(f"  Opp accuracy:    {result['opp_accuracy']}%")
    print(f"  Key moments:     {len(result['key_moments'])} "
          f"(plies {result['key_moments']})")
    print(f"\n✅ Saved: {out_path}")
    print(f"   Next: feed this JSON to the commentary step (Gemma or Claude).")

if __name__ == "__main__":
    main()
