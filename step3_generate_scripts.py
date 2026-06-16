"""
STEP 3 — Generate YouTube Metadata (No AI needed)
The Thinking Athlete Pipeline

Generates title, description and hashtags for each game
directly from chess.com game data. No API calls needed.

Requirements: chess (already installed)
"""

import json
import os
import sys
import chess
import chess.pgn
import io
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
USERNAME    = "abhi15041984"
VIDEOS_DIR  = "videos"
INPUT_FILE  = "won_games.json"
CHANNEL     = "Indian Thinking Athlete"
CHANNEL_URL = "@indianthinkingathlete"
MONTH_NAMES = {
    1:"01_January", 2:"02_February", 3:"03_March", 4:"04_April",
    5:"05_May",     6:"06_June",     7:"07_July",  8:"08_August",
    9:"09_September",10:"10_October",11:"11_November",12:"12_December"
}
# ─────────────────────────────────────────────────────────────────────────────

def get_my_side(game_data):
    return "white" if game_data["white"]["username"].lower() == USERNAME.lower() else "black"

def get_game_dir(game_data, index):
    dt       = datetime.fromtimestamp(game_data.get("end_time", 0))
    white    = game_data["white"]["username"]
    black    = game_data["black"]["username"]
    game_dir = os.path.join(VIDEOS_DIR, str(dt.year), MONTH_NAMES[dt.month],
                            f"game_{index:03d}_{white}_vs_{black}")
    os.makedirs(game_dir, exist_ok=True)
    return game_dir

def fmt_time_control(tc):
    if not tc or tc == "-": return "Rapid"
    try:
        base = int(tc.split("+")[0])
        inc  = int(tc.split("+")[1]) if "+" in tc else 0
        mins = base // 60
        label = "Rapid" if mins >= 10 else "Blitz" if mins >= 3 else "Bullet"
        return f"{mins} min{f'+{inc}' if inc else ''} {label}"
    except: return tc

def get_win_method(game_data):
    side     = get_my_side(game_data)
    opp_side = "black" if side == "white" else "white"
    result   = game_data[opp_side]["result"]
    methods  = {
        "checkmated": "Checkmate",
        "resigned":   "Resignation",
        "timeout":    "On Time",
        "stalemate":  "Stalemate",
    }
    return methods.get(result, "Resignation")

def parse_game(game_data):
    """Extract opening, move count, captures from PGN."""
    pgn  = game_data.get("pgn", "")
    if not pgn:
        return {}, 0, 0

    game = chess.pgn.read_game(io.StringIO(pgn))
    if not game:
        return {}, 0, 0

    h = game.headers
    meta = {
        "opening":   h.get("Opening", ""),
        "eco":       h.get("ECO", ""),
        "time_ctrl": fmt_time_control(h.get("TimeControl", "")),
    }

    # Walk through moves properly — check capture BEFORE pushing
    board    = game.board()
    moves    = list(game.mainline_moves())
    captures = 0
    for m in moves:
        try:
            if board.is_capture(m):
                captures += 1
            board.push(m)
        except Exception:
            break   # stop on illegal move, still return what we have

    return meta, len(moves), captures

def generate_title(game_data, meta, my_rating, opp_name, opp_rating, win_method, move_count):
    """Generate a punchy YouTube title."""
    diff     = opp_rating - my_rating
    opening  = meta.get("opening", "")
    eco      = meta.get("eco", "")

    # Pick a title style based on what's interesting about the game
    if diff >= 100:
        title = f"I Beat Someone {diff} Points Higher Rated | Road to 1000 ♟️"
    elif diff <= -100:
        title = f"Beating a Lower Rated Opponent | {opening or 'Chess Game'} | Road to 1000"
    elif opening and eco:
        title = f"{opening} | Road to 1000 | {my_rating} Rated ♟️"
    elif win_method == "Checkmate":
        title = f"Checkmate in {move_count} Moves | Road to 1000 | Chess.com ♟️"
    elif move_count <= 20:
        title = f"Quick Win in {move_count} Moves | Road to 1000 | Chess.com ♟️"
    else:
        title = f"Road to 1000 | Rated {my_rating} | {win_method} | Chess.com ♟️"

    return title[:100]

def generate_description(game_data, meta, my_rating, opp_name,
                         opp_rating, win_method, move_count, date_str):
    """Generate YouTube description."""
    diff        = opp_rating - my_rating
    diff_str    = f"{abs(diff)} points {'higher' if diff > 0 else 'lower'} rated"
    opening     = meta.get("opening", "")
    eco         = meta.get("eco", "")
    time_ctrl   = meta.get("time_ctrl", "Rapid")
    opening_str = f"{opening} ({eco})" if opening and eco else opening or "Unknown Opening"

    desc = f"""I am Abhishek — software developer, runner, and a chess player who started at 42.
Currently rated {my_rating} on chess.com. This is the Road to 1000.

🎮 Game Details:
• Playing as: {'White' if get_my_side(game_data) == 'white' else 'Black'}
• Opponent: {opp_name} (rated {opp_rating}) — {diff_str}
• Opening: {opening_str}
• Time Control: {time_ctrl}
• Result: Won by {win_method} in {move_count} moves
• Date: {date_str}

♟️ Every game on this channel is a real game — wins, losses, blunders and all.
Not a GM. Not a coach. Just a 42-year-old trying to get better at chess in public.

📌 Subscribe for weekly chess games, puzzles, and the slow grind of improvement.
👍 Like if you enjoyed the game
🔔 Hit the bell so you don't miss new uploads

{CHANNEL_URL} | chess.com: {USERNAME}

─────────────────────────
🏃 {CHANNEL} — Chess. Discipline. The slow grind of getting better.
─────────────────────────"""

    return desc[:4900]

def generate_hashtags(meta, my_rating, opp_rating, win_method, opening):
    """Generate relevant hashtags."""
    tags = [
        "#chess", "#chesscom", "#roadto1000",
        "#indianthinkingathlete", "#chessindia",
        "#learnchess", "#chessbeginner",
        f"#{'rapid' if 'Rapid' in meta.get('time_ctrl','') else 'blitz'}chess",
        "#chessgame", "#chessvideo",
    ]

    # Add opening-specific hashtag
    if opening:
        opening_tag = "#" + opening.replace(" ", "").replace(":", "").replace("-", "")[:20]
        tags.append(opening_tag)

    # Add win method tag
    if win_method == "Checkmate":
        tags.append("#checkmate")
    elif win_method == "Resignation":
        tags.append("#resignation")

    # Rating journey tags
    if my_rating < 1000:
        tags.append("#sub1000chess")
    tags.append("#chessimprovement")

    return " ".join(tags[:15])

def save_script(game_dir, title, description, hashtags, game_data, meta,
                my_rating, opp_name, opp_rating, win_method, move_count, date_str):
    """Save script.txt with all YouTube metadata."""
    side    = get_my_side(game_data)
    opening = meta.get("opening", "Unknown")
    eco     = meta.get("eco", "")

    content = f"""{"="*65}
GAME: {game_data['white']['username']} vs {game_data['black']['username']}
Date: {date_str}  |  My Rating: {my_rating}  |  Opponent: {opp_rating}
Opening: {opening} ({eco})  |  Won by: {win_method}  |  Moves: {move_count}
{"="*65}

🎬 YOUTUBE TITLE
{"─"*40}
{title}

📋 YOUTUBE DESCRIPTION
{"─"*40}
{description}

#️⃣  HASHTAGS (add to description or first comment)
{"─"*40}
{hashtags}

📱 INSTAGRAM CAPTION
{"─"*40}
Rated {my_rating} on chess.com. Played the {opening or 'game'} today.
Won by {win_method.lower()} in {move_count} moves vs {opp_name} ({opp_rating}).
Road to 1000 — one game at a time. ♟️

What would you have played differently? Drop it in the comments 👇

{hashtags}
"""
    with open(os.path.join(game_dir, "script.txt"), "w") as f:
        f.write(content)

def main():
    if not os.path.exists(INPUT_FILE):
        print(f"❌ {INPUT_FILE} not found — run step1 first!")
        sys.exit(1)

    with open(INPUT_FILE) as f:
        games = json.load(f)

    if not games:
        print("❌ No games found.")
        sys.exit(1)

    # Respect MAX_UPLOADS — match what step2 generated
    max_uploads = int(os.environ.get("MAX_UPLOADS", 0))
    if max_uploads > 0 and len(games) > max_uploads:
        games = games[:max_uploads]

    print(f"📝 Generating metadata for {len(games)} games (no API needed)...\n")

    success = 0
    for i, gd in enumerate(games):
        white    = gd["white"]["username"]
        black    = gd["black"]["username"]
        dt       = datetime.fromtimestamp(gd.get("end_time", 0))
        date_str = dt.strftime("%B %d, %Y")
        game_dir = get_game_dir(gd, i+1)

        print(f"[{i+1:03d}/{len(games)}] {white} vs {black} | {dt.strftime('%Y-%m-%d')}")

        if os.path.exists(os.path.join(game_dir, "script.txt")):
            print(f"  ⏭️  Already exists, skipping.")
            success += 1
            continue

        try:
            side       = get_my_side(gd)
            opp_side   = "black" if side == "white" else "white"
            my_rating  = gd[side]["rating"]
            opp_name   = gd[opp_side]["username"]
            opp_rating = gd[opp_side]["rating"]
            win_method = get_win_method(gd)
            meta, move_count, captures = parse_game(gd)

            title       = generate_title(gd, meta, my_rating, opp_name,
                                         opp_rating, win_method, move_count)
            description = generate_description(gd, meta, my_rating, opp_name,
                                               opp_rating, win_method, move_count, date_str)
            hashtags    = generate_hashtags(meta, my_rating, opp_rating,
                                            win_method, meta.get("opening",""))

            save_script(game_dir, title, description, hashtags, gd, meta,
                        my_rating, opp_name, opp_rating, win_method, move_count, date_str)

            print(f"  ✅ Title: {title[:65]}")
            success += 1

        except Exception as e:
            print(f"  ❌ Error: {e}")

    print(f"\n🏁 Done! {success}/{len(games)} scripts generated.")
    print(f"📂 script.txt saved in each game folder under {VIDEOS_DIR}/")

if __name__ == "__main__":
    main()
