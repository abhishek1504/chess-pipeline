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
EMAIL       = "thinkingathleteindia@gmail.com"
INSTAGRAM   = "@indianthinkingathlete"
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

def get_game_type(meta):
    """Return BLITZ or RAPID based on time control."""
    tc = meta.get("time_ctrl", "")
    if "Blitz" in tc:   return "BLITZ"
    if "Bullet" in tc:  return "BULLET"
    return "RAPID"

def generate_title(game_data, meta, my_rating, opp_name, opp_rating, win_method, move_count):
    """Generate title: Opening | Game Type | Rating | Key moment."""
    diff      = opp_rating - my_rating
    opening   = meta.get("opening", "")
    game_type = get_game_type(meta)

    # Shorten long opening names
    if opening and len(opening) > 30:
        opening = opening.split(":")[0].strip()  # e.g. "Sicilian Defense: Najdorf" -> "Sicilian Defense"

    opening_part = f"{opening} | " if opening else ""

    if diff >= 100:
        title = f"{opening_part}{game_type} | Beat {diff} pts Higher Rated | {my_rating} ♟️"
    elif win_method == "Checkmate":
        title = f"{opening_part}{game_type} | Checkmate in {move_count} Moves | {my_rating} ♟️"
    elif move_count <= 20:
        title = f"{opening_part}{game_type} | Won in {move_count} Moves | {my_rating} ♟️"
    else:
        title = f"{opening_part}{game_type} | {win_method} | Rated {my_rating} | Road to 1000 ♟️"

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

    game_type = get_game_type(meta)
    my_side   = get_my_side(game_data)
    side_str  = "White" if my_side == "white" else "Black"

    # Unique opening hook — varies by game context
    if diff >= 150:
        hook = f"Took on a player {diff} points above me and won. Playing {side_str} in a {game_type.lower()} game on chess.com."
    elif diff <= -150:
        hook = f"A {game_type.lower()} win playing {side_str}. Opponent was {abs(diff)} points below me — but every win counts on the road to 1000."
    elif win_method == "Checkmate":
        hook = f"Checkmate in {move_count} moves playing {side_str}. {opening_str} — one of my favourite setups."
    elif move_count <= 25:
        hook = f"Quick {game_type.lower()} win in just {move_count} moves playing {side_str}. {opening_str}."
    elif move_count >= 60:
        hook = f"A long {move_count}-move battle playing {side_str}. {opening_str} — grindy but worth it."
    else:
        hook = f"A {game_type.lower()} game playing {side_str} with the {opening_str}. Won by {win_method} in {move_count} moves."

    desc = f"""{hook}

I am Abhishek — software developer, distance runner, and chess player who started at 42.
Currently rated {my_rating} on chess.com.

Game Details:
- Opening: {opening_str}
- Game type: {game_type} | Time control: {time_ctrl}
- Playing as: {side_str}
- Opponent: {opp_name} (rated {opp_rating}) — {diff_str}
- Result: Won by {win_method} in {move_count} moves
- Date: {date_str}

Every game on this channel is real — wins, losses, blunders and everything in between.
Not a GM. Not a professional coach. Just a 42-year-old getting better at chess in public and documenting every step.

If you are a beginner or intermediate player trying to improve, this channel is for you.
Subscribe and follow the journey from 800 to 1000 and beyond.

{CHANNEL_URL} | chess.com: {USERNAME}
Email: thinkingathleteindia@gmail.com

─────────────────────────
{CHANNEL} — Chess. Discipline. The Grind.
─────────────────────────"""

    return desc[:4900]

def generate_hashtags(meta, my_rating, opp_rating, win_method, opening):
    """Generate optimised hashtags for reach."""
    game_type = get_game_type(meta)
    tc        = meta.get("time_ctrl", "")

    # Core high-reach chess hashtags
    tags = [
        "#chess",
        "#chesscom",
        "#chessindia",
        "#indianchess",
        "#learnchess",
        "#chessgame",
    ]

    # Game type specific — high search volume
    if game_type == "BLITZ":
        tags += ["#blitzchess", "#blitz", "#blitzgame"]
    elif game_type == "RAPID":
        tags += ["#rapidchess", "#rapid", "#rapidgame"]
    elif game_type == "BULLET":
        tags += ["#bulletchess", "#bullet"]

    # Opening specific — niche but targeted
    if opening:
        short = opening.split(":")[0].strip()
        tag   = "#" + short.replace(" ", "").replace("-","").replace("'","")[:22]
        tags.append(tag)
        # Also add generic opening tag
        if "sicilian" in opening.lower():
            tags.append("#siciliandefense")
        elif "king" in opening.lower() and "gambit" in opening.lower():
            tags.append("#kingsgambit")
        elif "london" in opening.lower():
            tags.append("#londonsystem")
        elif "italian" in opening.lower():
            tags.append("#italiangame")
        elif "french" in opening.lower():
            tags.append("#frenchdefense")
        elif "caro" in opening.lower():
            tags.append("#carokann")
        elif "queen" in opening.lower() and "gambit" in opening.lower():
            tags.append("#queensgambit")
        elif "ruy" in opening.lower() or "lopez" in opening.lower():
            tags.append("#ruylopez")

    # Win method
    if win_method == "Checkmate":
        tags += ["#checkmate", "#chessmating"]
    elif win_method == "Resignation":
        tags.append("#resignation")

    # Rating journey — community hashtags with good reach
    tags += ["#roadto1000", "#chessimprovement", "#chessbeginners"]
    if my_rating < 1000:
        tags += ["#under1000", "#800rating"]

    # Brand
    tags += ["#indianthinkingathlete", "#thinkingathlete"]

    # Music recommendation in script (not a hashtag)
    return " ".join(tags[:20])

def get_music_suggestion(meta, move_count, win_method):
    """Suggest background music from YouTube Audio Library."""
    game_type = get_game_type(meta)
    if game_type == "BULLET" or move_count < 20:
        return "🎵 Music suggestion: Search 'upbeat electronic' in YouTube Audio Library"
    elif win_method == "Checkmate":
        return "🎵 Music suggestion: Search 'dramatic cinematic' in YouTube Audio Library"
    else:
        return "🎵 Music suggestion: Search 'calm piano focus' in YouTube Audio Library"

def save_script(game_dir, title, description, hashtags, game_data, meta,
                my_rating, opp_name, opp_rating, win_method, move_count, date_str):
    """Save script.txt with all YouTube metadata."""
    side    = get_my_side(game_data)
    opening = meta.get("opening", "Unknown")
    eco     = meta.get("eco", "")

    music_tip = get_music_suggestion(meta, move_count, win_method)
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

{music_tip}

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
            music_tip   = get_music_suggestion(meta, move_count, win_method)

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
