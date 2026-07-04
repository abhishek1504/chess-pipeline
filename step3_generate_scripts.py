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
import re
import requests
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

# ── Game story (Claude API, optional) ────────────────────────────────────────
# If ANTHROPIC_API_KEY is set, each game gets a real 2-3 sentence story of
# how it unfolded (for the landscape description) plus a unique one-line
# hook (for the Shorts description). Without a key the pipeline still works,
# falling back to a factual story built from the PGN itself.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL   = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")

def generate_game_summary(game_data, meta, my_rating, opp_name, opp_rating,
                          win_method, move_count):
    """Returns {'story': ..., 'shorts_hook': ...} or None on any failure."""
    if not ANTHROPIC_API_KEY:
        return None

    side    = get_my_side(game_data)
    opening = meta.get("opening") or "unknown opening"
    pgn     = game_data.get("pgn", "")[:6000]

    prompt = f"""You write YouTube descriptions for a beginner-friendly chess channel.
The channel owner played {side.upper()} (username on that side of the PGN), rated {my_rating},
against {opp_name} ({opp_rating}). Opening: {opening}. Result: won by {win_method}
in {move_count} moves.

PGN:
{pgn}

Respond ONLY with a JSON object, no markdown fences, in this exact shape:
{{"story": "...", "shorts_hook": "..."}}

- "story": 2-3 sentences in plain language for beginner/intermediate viewers
  describing how THIS game actually unfolded: the opening plan, the turning
  point or decisive mistake, and how the win was converted. Be specific to
  the moves. No hashtags, no emoji.
- "shorts_hook": one punchy sentence, under 18 words, teasing the finish of
  this specific game. No hashtags, no emoji, no quotes."""

    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": ANTHROPIC_MODEL,
                "max_tokens": 500,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )
        r.raise_for_status()
        text = "".join(b.get("text", "") for b in r.json().get("content", [])
                       if b.get("type") == "text")
        text = re.sub(r"```json|```", "", text).strip()
        data = json.loads(text)
        story = str(data.get("story", "")).strip()
        hook  = str(data.get("shorts_hook", "")).strip().strip('"')
        if story and hook:
            return {"story": story, "shorts_hook": hook}
    except Exception as e:
        print(f"  ⚠️  Game summary via API failed, using fallback ({e})")
    return None

def basic_game_story(game_data, win_method, move_count):
    """Factual 1-2 sentence story built from the PGN — used when no
    ANTHROPIC_API_KEY is configured or the API call fails."""
    pgn = game_data.get("pgn", "")
    if not pgn:
        return ""
    game = chess.pgn.read_game(io.StringIO(pgn))
    if not game:
        return ""

    board, captures, promoted, sans = game.board(), 0, False, []
    try:
        for mv in game.mainline_moves():
            sans.append(board.san(mv))
            if board.is_capture(mv):
                captures += 1
            if mv.promotion:
                promoted = True
            board.push(mv)
    except Exception:
        pass
    if not sans:
        return ""

    style = ("A sharp, tactical game" if captures >= 14
             else "A patient, positional game" if captures <= 6
             else "A balanced fight")
    parts = [f"{style} — {captures} captures over {move_count} moves."]
    if promoted:
        parts.append("A pawn made it all the way to promotion.")
    last = sans[-1]
    if last.endswith("#"):
        piece = {"Q": "queen", "R": "rook", "B": "bishop",
                 "N": "knight", "K": "king", "O": "rook"}.get(last[0], "pawn")
        parts.append(f"The {piece} delivered the final checkmate.")
    return " ".join(parts)


ECO_NAMES = {
    "A00": "Irregular Opening",   "A04": "Réti Opening",
    "A10": "English Opening",     "A40": "Queen's Pawn Opening",
    "A45": "Indian Defense",      "B00": "King's Pawn Opening",
    "B01": "Scandinavian Defense","B06": "Modern Defense",
    "B07": "Pirc Defense",        "B10": "Caro-Kann Defense",
    "B20": "Sicilian Defense",    "C00": "French Defense",
    "C20": "King's Pawn Game",    "C23": "Bishop's Opening",
    "C25": "Vienna Game",         "C30": "King's Gambit",
    "C40": "King's Knight Opening","C41": "Philidor Defense",
    "C42": "Petrov's Defense",    "C44": "Scotch Game",
    "C50": "Italian Game",        "C55": "Two Knights Defense",
    "C60": "Ruy López",           "D00": "Queen's Pawn Game",
    "D02": "London System",       "D06": "Queen's Gambit",
    "D10": "Slav Defense",        "E00": "Indian Game",
    "E20": "Nimzo-Indian Defense","E60": "King's Indian Defense",
}

def opening_from_ecourl(url):
    """chess.com ECOUrl -> readable opening name.
    'https://www.chess.com/openings/Caro-Kann-Defense-Exchange-Variation-4.Bd3'
    -> 'Caro-Kann Defense Exchange Variation'"""
    if not url or "/openings/" not in url:
        return ""
    slug  = url.rstrip("/").split("/")[-1]
    words = []
    for w in slug.split("-"):
        if re.match(r"^\d", w):   # move-number suffix like '4.Bd3' — stop
            break
        words.append(w)
    name = " ".join(words).strip()
    # Restore possessives the slug loses: 'Queens Gambit' -> "Queen's Gambit"
    # (but not plurals like 'Two Knights Defense' / 'Four Knights Game')
    name = re.sub(r"(?<!Two )(?<!Four )(?<!Three )"
                  r"\b(King|Queen|Bishop|Knight|Rook|Alekhine|Petrov|Philidor)s\b",
                  r"\1's", name)
    # Restore hyphens in names the slug flattens
    for a, b in [("Caro Kann", "Caro-Kann"), ("Nimzo Indian", "Nimzo-Indian"),
                 ("Semi Slav", "Semi-Slav"), ("Bogo Indian", "Bogo-Indian"),
                 ("Semi Tarrasch", "Semi-Tarrasch")]:
        name = name.replace(a, b)
    return name

def resolve_opening(headers, game_data):
    """Best-effort opening name. chess.com often omits the [Opening] PGN
    header, but almost always provides ECOUrl (in the PGN and as the
    'eco' field of the game JSON)."""
    opening = headers.get("Opening", "").strip()
    if not opening:
        opening = opening_from_ecourl(headers.get("ECOUrl", ""))
    if not opening:
        opening = opening_from_ecourl(game_data.get("eco", ""))
    if not opening:
        opening = ECO_NAMES.get(headers.get("ECO", ""), "")
    return opening

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
        "opening":   resolve_opening(h, game_data),
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
        opening = shorten_opening(opening)  # "Sicilian Defense: Najdorf" -> "Sicilian Defense"

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
                         opp_rating, win_method, move_count, date_str,
                         story=""):
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

    # Unique opening hook — varies by game context. Only mention the
    # opening when we actually identified one.
    op_clause = f" {opening_str} — one of my favourite setups." if opening else ""
    if diff >= 150:
        hook = f"Took on a player {diff} points above me and won. Playing {side_str} in a {game_type.lower()} game on chess.com."
    elif diff <= -150:
        hook = f"A {game_type.lower()} win playing {side_str}. Opponent was {abs(diff)} points below me — but every win counts on the road to 1000."
    elif win_method == "Checkmate":
        hook = f"Checkmate in {move_count} moves playing {side_str}.{op_clause}"
    elif move_count <= 25:
        hook = f"Quick {game_type.lower()} win in just {move_count} moves playing {side_str}." + (f" {opening_str}." if opening else "")
    elif move_count >= 60:
        hook = f"A long {move_count}-move battle playing {side_str}." + (f" {opening_str} — grindy but worth it." if opening else " Grindy but worth it.")
    else:
        hook = (f"A {game_type.lower()} game playing {side_str} with the {opening_str}. Won by {win_method} in {move_count} moves."
                if opening else
                f"A {game_type.lower()} game playing {side_str}. Won by {win_method} in {move_count} moves.")

    story_block = f"\nHow the game went:\n{story}\n" if story else ""

    desc = f"""{hook}
{story_block}
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

OPENING_FAMILY_WORDS = {"Defense", "Opening", "Game", "Gambit", "Attack", "System"}

def shorten_opening(opening):
    """'Caro-Kann Defense Exchange Variation' -> 'Caro-Kann Defense'.
    Cuts at the opening-family word; also handles 'Family: Variation'."""
    if not opening:
        return ""
    opening = opening.split(":")[0].strip()
    words = opening.split()
    for i, w in enumerate(words):
        if w in OPENING_FAMILY_WORDS:
            return " ".join(words[:i + 1])
    return " ".join(words[:3])

def opening_hashtag(opening):
    """'Caro-Kann Defense: Exchange Variation' -> '#carokanndefense'"""
    if not opening:
        return None
    short = shorten_opening(opening)
    tag   = "#" + re.sub(r"[^a-z0-9]", "", short.lower())[:22]
    return tag if len(tag) > 3 else None

def generate_shorts_title(meta, my_rating, opp_name, opp_rating,
                          win_method, move_count, game_data):
    """Short, punchy, game-specific title for the vertical (Shorts) video.
    Must be distinct from the landscape title or YouTube treats the pair
    as duplicate content."""
    opening = shorten_opening(meta.get("opening")) or "Chess"
    diff    = opp_rating - my_rating

    if diff >= 100:
        return f"Beating a {opp_rating} Rated Player With the {opening} ♟️"[:92]

    templates = [
        f"{win_method} in {move_count} Moves — {opening}",
        f"The {opening} Finish You Need to See ♟️",
        f"How This {opening} Game Ended ({my_rating} Rated)",
        f"Final Moves: {opening} vs {opp_rating} Rated",
        f"{opening} — Watch the Final Attack ♟️",
    ]
    # Deterministic pick so re-runs produce the same title for the same game
    idx = (game_data.get("end_time", 0) + move_count) % len(templates)
    return templates[idx][:92]

def generate_shorts_description(meta, my_rating, opp_name, opp_rating,
                                win_method, move_count, date_str,
                                game_data=None, shorts_hook="", story=""):
    """Unique description for the Short. step5 replaces [FULL_GAME_LINK]
    with the real landscape URL after upload. Kept short and game-specific
    — no repeated channel bio (that lives on the landscape video)."""
    game_data = game_data or {}
    opening   = shorten_opening(meta.get("opening"))
    game_ref  = f"{opening} game" if opening else "game"

    # First line: LLM-generated hook when available, otherwise game facts
    hook = shorts_hook or \
        f"The final moves of my {game_ref} against {opp_name} ({opp_rating})."

    # Second line: what actually happened (story from API/PGN), else result
    detail = story or \
        f"Won by {win_method.lower()} in {move_count} moves — rated {my_rating}, climbing to 1000."

    # Rotate the CTA so consecutive Shorts don't end identically
    ctas = [
        "Can you spot the turning point? Drop your move in the comments 👇",
        "Would you have found this finish? Tell me in the comments 👇",
        "Pause before the last move — can you find it? 👇",
    ]
    cta = ctas[(game_data.get("end_time", 0) + move_count) % len(ctas)]

    return f"""{hook}

{detail}

♟️ Full game move by move: [FULL_GAME_LINK]

{cta}"""

def generate_shorts_hashtags(meta, my_rating, opp_rating, win_method, opening):
    """Tight hashtag set for Shorts. YouTube only surfaces the first 3
    hashtags above a Short's title, so highest-value tags go first."""
    game_type = get_game_type(meta)

    tags = ["#shorts", "#chessshorts", "#chess"]

    op_tag = opening_hashtag(opening)
    if op_tag:
        tags.append(op_tag)

    if game_type == "BLITZ":
        tags.append("#blitzchess")
    elif game_type == "BULLET":
        tags.append("#bulletchess")
    else:
        tags.append("#rapidchess")

    if win_method == "Checkmate":
        tags.append("#checkmate")

    tags += ["#chesscom", "#roadto1000", "#chessindia", "#thinkingathlete"]

    # De-duplicate, preserve order
    seen, out = set(), []
    for t in tags:
        if t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return " ".join(out[:12])

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
                my_rating, opp_name, opp_rating, win_method, move_count, date_str,
                story="", shorts_hook=""):
    """Save script.txt with all YouTube metadata."""
    side    = get_my_side(game_data)
    opening = meta.get("opening", "Unknown")
    eco     = meta.get("eco", "")

    music_tip = get_music_suggestion(meta, move_count, win_method)

    # Shorts-specific metadata — must be unique vs the landscape video,
    # otherwise YouTube deprioritises the pair as duplicate content.
    shorts_title    = generate_shorts_title(meta, my_rating, opp_name, opp_rating,
                                            win_method, move_count, game_data)
    shorts_desc     = generate_shorts_description(meta, my_rating, opp_name, opp_rating,
                                                  win_method, move_count, date_str,
                                                  game_data=game_data,
                                                  shorts_hook=shorts_hook,
                                                  story=story)
    shorts_hashtags = generate_shorts_hashtags(meta, my_rating, opp_rating,
                                               win_method, opening)

    content = f"""{"="*65}
GAME: {game_data['white']['username']} vs {game_data['black']['username']}
Game ID: {game_data.get('end_time', 0)}_{game_data['white']['username']}_vs_{game_data['black']['username']}
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

🎬 SHORTS TITLE
{"─"*40}
{shorts_title}

📋 SHORTS DESCRIPTION
{"─"*40}
{shorts_desc}

#️⃣  SHORTS HASHTAGS
{"─"*40}
{shorts_hashtags}

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

            # Per-game story: Claude API when key is set, PGN-derived
            # factual fallback otherwise — makes every description unique.
            summary     = generate_game_summary(gd, meta, my_rating, opp_name,
                                                opp_rating, win_method, move_count)
            story       = summary["story"] if summary else \
                          basic_game_story(gd, win_method, move_count)
            shorts_hook = summary["shorts_hook"] if summary else ""

            title       = generate_title(gd, meta, my_rating, opp_name,
                                         opp_rating, win_method, move_count)
            description = generate_description(gd, meta, my_rating, opp_name,
                                               opp_rating, win_method, move_count, date_str,
                                               story=story)
            hashtags    = generate_hashtags(meta, my_rating, opp_rating,
                                            win_method, meta.get("opening",""))
            music_tip   = get_music_suggestion(meta, move_count, win_method)

            save_script(game_dir, title, description, hashtags, gd, meta,
                        my_rating, opp_name, opp_rating, win_method, move_count, date_str,
                        story=story, shorts_hook=shorts_hook)

            print(f"  ✅ Title: {title[:65]}")
            success += 1

        except Exception as e:
            print(f"  ❌ Error: {e}")

    print(f"\n🏁 Done! {success}/{len(games)} scripts generated.")
    print(f"📂 script.txt saved in each game folder under {VIDEOS_DIR}/")

if __name__ == "__main__":
    main()
