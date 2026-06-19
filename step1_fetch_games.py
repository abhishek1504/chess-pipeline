import chess
import chess.pgn
"""
STEP 1 — Fetch ALL Won Games (All Time)
Filters:
  ✅ Abhishek won
  ❌ Skips games won by abandonment

The Thinking Athlete Pipeline
"""

import requests
import json
import time
from datetime import datetime

USERNAME    = "abhi15041984"
HEADERS     = {"User-Agent": "TheThinkingAthlete/1.0 Chess Pipeline"}
OUTPUT_FILE = "won_games.json"

# Result codes chess.com uses that mean opponent abandoned — not real games
ABANDONMENT_CODES = {"abandoned", "timeout", "timevsinsufficient"}

def get_archives():
    url = f"https://api.chess.com/pub/player/{USERNAME}/games/archives"
    res = requests.get(url, headers=HEADERS)
    res.raise_for_status()
    return res.json()["archives"]

def get_games_from_archive(archive_url, retries=3):
    for attempt in range(retries):
        try:
            res = requests.get(archive_url, headers=HEADERS, timeout=15)
            res.raise_for_status()
            return res.json().get("games", [])
        except Exception as e:
            if attempt < retries - 1:
                print(f"    ⚠️  Retrying ({attempt+1}/{retries})...")
                time.sleep(2)
            else:
                print(f"    ❌ Failed: {e}")
                return []

def get_my_side(game):
    if game["white"]["username"].lower() == USERNAME.lower():
        return "white"
    return "black"



# ── Game quality estimation (accuracy proxy) ──────────────────────────────────
# Estimates game quality without chess.com Game Review
# Based on: blunders, mistakes, material hanging, move efficiency
#
# Quality score 0-100 (roughly maps to chess.com accuracy):
#   90-100 = excellent (≈ 90%+ accuracy)
#   75-89  = good      (≈ 75-90% accuracy)
#   60-74  = ok        (≈ 60-75% accuracy)  ← MIN_QUALITY default
#   below 60 = poor

MIN_QUALITY     = 70    # minimum quality score to upload (≈ 70% accuracy proxy)
PIECE_VALUES    = {
    chess.PAWN:1, chess.KNIGHT:3, chess.BISHOP:3,
    chess.ROOK:5, chess.QUEEN:9, chess.KING:0
}

def estimate_game_quality(game_data):
    """
    Estimate game quality 0-100 as a proxy for chess.com accuracy.
    Analyses Abhishek's moves only.

    Penalties:
    - Hanging a queen  (9pts): -25 points
    - Hanging a rook   (5pts): -18 points
    - Hanging a bishop/knight (3pts): -12 points
    - Hanging a pawn   (1pt):  -4 points
    - Missing a free capture worth 5+: -8 points

    Score starts at 100, penalties applied per bad move.
    """
    pgn_text = game_data.get("pgn", "")
    if not pgn_text:
        return 100  # no data = don't penalise

    try:
        import chess.pgn as cpgn, io
        game     = cpgn.read_game(io.StringIO(pgn_text))
        if not game:
            return 100

        side     = get_my_side(game_data)
        my_color = chess.WHITE if side == "white" else chess.BLACK
        board    = game.board()
        score    = 100
        my_moves = 0

        for move in game.mainline_moves():
            is_my = (board.turn == my_color)

            if is_my:
                my_moves += 1

                # Check 1: Am I missing a free capture?
                best_free = 0
                for candidate in board.legal_moves:
                    if board.is_capture(candidate):
                        target = board.piece_at(candidate.to_square)
                        if target and target.color != my_color:
                            val = PIECE_VALUES.get(target.piece_type, 0)
                            # Check if it's safe to take
                            b2 = board.copy()
                            b2.push(candidate)
                            attacked = b2.is_attacked_by(
                                not my_color, candidate.to_square
                            )
                            if not attacked and val > best_free:
                                best_free = val

                board.push(move)

                # Penalty for missing free capture
                if best_free >= 5:
                    score -= 8
                elif best_free >= 3:
                    score -= 4

                # Check 2: Did I just hang a piece?
                for opp_mv in board.legal_moves:
                    if not board.is_capture(opp_mv):
                        continue
                    victim = board.piece_at(opp_mv.to_square)
                    if not victim or victim.color != my_color:
                        continue
                    val = PIECE_VALUES.get(victim.piece_type, 0)
                    if val == 0:
                        continue

                    # Can I recapture?
                    b2 = board.copy()
                    b2.push(opp_mv)
                    can_recap = any(
                        b2.is_capture(m) and b2.piece_at(m.to_square) and
                        b2.piece_at(m.to_square).color != my_color and
                        PIECE_VALUES.get(b2.piece_at(m.to_square).piece_type,0) >= val
                        for m in b2.legal_moves
                    )
                    if not can_recap:
                        # Penalty based on piece value
                        if val >= 9:   score -= 25
                        elif val >= 5: score -= 18
                        elif val >= 3: score -= 12
                        else:          score -= 4
                        break   # count once per move

            else:
                board.push(move)

        return max(0, min(100, score))

    except Exception:
        return 100  # parse error = don't penalise

    try:
        import chess.pgn, io
        game     = chess.pgn.read_game(io.StringIO(pgn_text))
        if not game:
            return 0

        side     = get_my_side(game_data)
        my_color = chess.WHITE if side == "white" else chess.BLACK
        board    = game.board()
        blunders = 0

        for move in game.mainline_moves():
            is_my_move = (board.turn == my_color)
            if is_my_move:
                # Check if I am leaving a piece hanging after this move
                board.push(move)
                # Look at all opponent responses — if any capture my piece for free
                for opp_move in board.legal_moves:
                    if board.is_capture(opp_move):
                        captured = board.piece_at(opp_move.to_square)
                        if captured and captured.color == my_color:
                            val = PIECE_VALUES.get(captured.piece_type, 0)
                            if val >= BLUNDER_THRESHOLD:
                                # Check if I can recapture
                                board2 = board.copy()
                                board2.push(opp_move)
                                can_recapture = any(
                                    board2.is_capture(m) and
                                    board2.piece_at(m.to_square) and
                                    board2.piece_at(m.to_square).color != my_color
                                    for m in board2.legal_moves
                                    if board2.piece_at(m.to_square) and
                                    PIECE_VALUES.get(board2.piece_at(m.to_square).piece_type,0) >= val
                                )
                                if not can_recapture:
                                    blunders += 1
                                    break   # count once per move
            else:
                board.push(move)

        return blunders

    except Exception:
        return 0   # if parsing fails, don't skip the game

def is_real_win(game):
    """Win by actual play — not abandonment/timeout."""
    side     = get_my_side(game)
    opp_side = "black" if side == "white" else "white"
    if game[side]["result"] != "win":
        return False, "not_win"
    # Check how opponent lost — skip abandonment
    opp_result = game[opp_side]["result"]
    if opp_result in ABANDONMENT_CODES:
        return False, "abandonment"
    # Quality filter — estimated accuracy >= MIN_QUALITY
    quality = estimate_game_quality(game)
    if quality < MIN_QUALITY:
        return False, f"low_quality({quality})"
    return True, "ok"

def main():
    print(f"🔍 Fetching ALL archives for {USERNAME}")
    print(f"   Filter: Real wins only (no abandonment)\n")

    archives    = get_archives()
    total       = len(archives)
    print(f"📦 Found {total} monthly archives — fetching all...\n")

    passed      = []
    total_games = 0
    skipped_loss      = 0
    skipped_abandoned = 0

    for idx, archive_url in enumerate(archives):
        month = archive_url.split("/")[-2] + "/" + archive_url.split("/")[-1]
        print(f"  [{idx+1:03d}/{total}] {month} ", end="", flush=True)

        games        = get_games_from_archive(archive_url)
        total_games += len(games)

        month_wins = 0
        for game in games:
            ok, reason = is_real_win(game)
            if ok:
                passed.append(game)
                month_wins += 1
            elif reason == "abandonment":
                skipped_abandoned += 1
            else:
                skipped_loss += 1

        print(f"→ {len(games)} games, {month_wins} real wins ✅")
        time.sleep(0.3)

    print(f"\n{'─'*55}")
    print(f"📊 All time summary:")
    print(f"   Total games fetched:     {total_games}")
    print(f"   Skipped (loss/draw):     {skipped_loss}")
    print(f"   Skipped (abandonment):   {skipped_abandoned}")
    print(f"   ✅ Real wins:            {len(passed)}")
    print(f"{'─'*55}\n")

    if not passed:
        print("⚠️  No real wins found — check your username.")
        return

    # Filter to 2026 only
    from datetime import datetime
    passed_2026 = [g for g in passed
                   if datetime.fromtimestamp(g.get("end_time", 0)).year == 2026]
    passed = passed_2026

    # Sort newest first
    passed.sort(key=lambda g: g.get("end_time", 0), reverse=True)

    print(f"🏆 {len(passed)} real wins in 2026 (most recent first, showing first 20):\n")
    for i, g in enumerate(passed[:20]):
        side       = get_my_side(g)
        opp_side   = "black" if side == "white" else "white"
        my_rating  = g[side]["rating"]
        opp_name   = g[opp_side]["username"]
        opp_rating = g[opp_side]["rating"]
        time_class = g.get("time_class", "?")
        end_time   = datetime.fromtimestamp(g["end_time"]).strftime("%Y-%m-%d")
        print(f"  {i+1:03d}. vs {opp_name} ({opp_rating}) | "
              f"My rating: {my_rating} | "
              f"{time_class} | {end_time}")

    if len(passed) > 20:
        print(f"  ... and {len(passed)-20} more")

    with open(OUTPUT_FILE, "w") as f:
        json.dump(passed, f, indent=2)

    print(f"\n💾 Saved {len(passed)} games to {OUTPUT_FILE}")
    print(f"▶️  Now run step2_generate_video.py!")

if __name__ == "__main__":
    main()
