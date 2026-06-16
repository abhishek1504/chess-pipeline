"""
STEP 3 — Generate Per-Move Commentary + YouTube/Instagram Metadata
The Thinking Athlete Pipeline

Generates:
  - commentary.json  — per-move commentary for synced TTS in step4
  - script.txt       — full voiceover + YT title + description + hashtags

Style: Sagar Shah / ChessBase India energy — commentary only on key moments,
opening named and explained, silence on normal moves, depth on interesting ones.

Requirements:
    pip install anthropic chess
    export ANTHROPIC_API_KEY="your-key-here"
"""

import json
import os
import sys
import re
import chess
import chess.pgn
import io
from datetime import datetime

try:
    import anthropic
except ImportError:
    print("❌ Run: pip install anthropic")
    sys.exit(1)

USERNAME    = "abhi15041984"
VIDEOS_DIR  = "videos"
INPUT_FILE  = "won_games.json"
MONTH_NAMES = {
    1:"01_January", 2:"02_February", 3:"03_March", 4:"04_April",
    5:"05_May",     6:"06_June",     7:"07_July",  8:"08_August",
    9:"09_September",10:"10_October",11:"11_November",12:"12_December"
}

client = anthropic.Anthropic()

def get_my_side(game_data):
    return "white" if game_data["white"]["username"].lower() == USERNAME.lower() else "black"

def get_game_dir(game_data, index):
    dt        = datetime.fromtimestamp(game_data.get("end_time", 0))
    white     = game_data["white"]["username"]
    black     = game_data["black"]["username"]
    game_dir  = os.path.join(VIDEOS_DIR, str(dt.year), MONTH_NAMES[dt.month],
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

def analyse_game(game_data):
    """
    Extract full move list with annotations for key moments.
    Returns (moves_info, meta) where moves_info is a list of dicts per half-move.
    """
    pgn_text = game_data.get("pgn", "")
    if not pgn_text: return [], {}

    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if not game: return [], {}

    side      = get_my_side(game_data)
    my_color  = chess.WHITE if side == "white" else chess.BLACK
    h         = game.headers
    opp_side  = "black" if side == "white" else "white"

    meta = {
        "opening":      h.get("Opening", ""),
        "eco":          h.get("ECO", ""),
        "time_ctrl":    fmt_time_control(h.get("TimeControl", "")),
        "my_name":      game_data[side]["username"],
        "opp_name":     game_data[opp_side]["username"],
        "my_rating":    game_data[side]["rating"],
        "opp_rating":   game_data[opp_side]["rating"],
        "my_side":      side,
        "win_method":   game_data[opp_side]["result"],
        "date":         datetime.fromtimestamp(game_data["end_time"]).strftime("%B %d, %Y"),
    }

    piece_values = {chess.PAWN:1, chess.KNIGHT:3, chess.BISHOP:3,
                    chess.ROOK:5, chess.QUEEN:9, chess.KING:0}

    board      = game.board()
    all_moves  = list(game.mainline_moves())
    moves_info = []

    for i, move in enumerate(all_moves):
        is_my    = (board.turn == my_color)
        move_num = (i // 2) + 1
        san      = board.san(move)

        # Classify move
        is_capture  = board.is_capture(move)
        is_castle   = board.is_castling(move)
        is_promote  = move.promotion is not None
        cap_val     = 0
        if is_capture:
            cap_piece = board.piece_at(move.to_square)
            if cap_piece:
                cap_val = piece_values.get(cap_piece.piece_type, 0)

        board_after = board.copy()
        board_after.push(move)
        is_check    = board_after.is_check()
        is_checkmate= board_after.is_checkmate()

        # Determine if this is a KEY moment (worth commenting on)
        is_key = (
            i < 6 or                    # Opening moves
            is_castle or
            is_promote or
            is_checkmate or
            (is_capture and cap_val >= 3) or  # Takes a minor piece or better
            (is_check and i > 10) or    # Checks in middlegame/endgame
            (is_my and cap_val >= 5)    # I take a rook or queen
        )

        moves_info.append({
            "half_move":    i + 1,
            "move_num":     move_num,
            "san":          san,
            "is_my":        is_my,
            "is_key":       is_key,
            "is_capture":   is_capture,
            "is_castle":    is_castle,
            "is_promote":   is_promote,
            "is_check":     is_check,
            "is_checkmate": is_checkmate,
            "cap_val":      cap_val,
            "is_opening":   i < 6,
        })
        board.push(move)

    return moves_info, meta

def build_move_sequence_for_claude(moves_info, meta):
    """Build a readable move sequence string with key moment markers."""
    lines = []
    i = 0
    while i < len(moves_info):
        w = moves_info[i]
        b = moves_info[i+1] if i+1 < len(moves_info) else None

        w_ann = ""
        if w["is_castle"]:   w_ann = "[CASTLE]"
        elif w["is_promote"]: w_ann = "[PROMOTION]"
        elif w["is_checkmate"]: w_ann = "[CHECKMATE]"
        elif w["is_check"]:  w_ann = "[CHECK]"
        elif w["cap_val"] >= 5: w_ann = f"[TAKES ROOK/QUEEN]"
        elif w["cap_val"] >= 3: w_ann = f"[TAKES PIECE]"
        elif w["is_opening"]: w_ann = "[OPENING]"

        b_san = b["san"] if b else ""
        b_ann = ""
        if b:
            if b["is_castle"]:    b_ann = "[CASTLE]"
            elif b["is_promote"]: b_ann = "[PROMOTION]"
            elif b["is_checkmate"]: b_ann = "[CHECKMATE]"
            elif b["is_check"]:   b_ann = "[CHECK]"
            elif b["cap_val"] >= 5: b_ann = f"[TAKES ROOK/QUEEN]"
            elif b["cap_val"] >= 3: b_ann = f"[TAKES PIECE]"
            elif b["is_opening"]:  b_ann = "[OPENING]"

        line = f"{w['move_num']}. {w['san']} {w_ann}  {b_san} {b_ann}"
        lines.append(line.strip())
        i += 2

    return "\n".join(lines)

def generate_commentary(moves_info, meta):
    """
    Ask Claude to generate per-move commentary for key moments only.
    Returns a list of {half_move, commentary} dicts.
    """
    key_moves   = [m for m in moves_info if m["is_key"]]
    move_seq    = build_move_sequence_for_claude(moves_info, meta)
    total_moves = len(moves_info)
    diff        = meta["opp_rating"] - meta["my_rating"]
    diff_str    = f"{abs(diff)} points {'higher' if diff > 0 else 'lower'} rated"

    prompt = f"""You are writing chess commentary for Abhishek's YouTube channel "The Thinking Athlete".

STYLE: Sagar Shah / ChessBase India energy. Commentary only on interesting moments.
Calm, analytical, warm. Self-deprecating when Abhishek makes a dubious move.
Excited (but not over the top) on brilliant moments. Plain English, no jargon.
Abhishek's rating: {meta['my_rating']} — he references this for comic effect.

GAME:
- Abhishek ({meta['my_side']}, rated {meta['my_rating']}) vs {meta['opp_name']} ({meta['opp_rating']}) — {diff_str}
- Opening: {meta['opening']} ({meta['eco']})
- Time control: {meta['time_ctrl']}
- Won by: {meta['win_method']}
- Total moves: {total_moves}

FULL MOVE SEQUENCE (annotated):
{move_seq}

KEY MOVES TO COMMENT ON (half-move numbers):
{', '.join(str(m['half_move']) for m in key_moves)}

YOUR TASK:
Generate commentary ONLY for the key moments listed above.
Return a JSON array. Each element:
{{
  "half_move": <number>,   // which half-move this commentary is for
  "commentary": "<text>",  // what Abhishek says out loud (1-3 sentences max)
  "hold_seconds": <number> // how long to hold this frame (2-5 seconds)
}}

RULES:
- Opening moves (half_move 1-6): name the opening, explain it simply in 1-2 sentences
  e.g. "This is the Sicilian Defense — black is saying I want a complex fight for the center"
- Normal captures of minor pieces: 1 short punchy line
  e.g. "I take the bishop here — free piece, thank you very much"
- Big captures (rook/queen): 2-3 sentences, build the drama
  e.g. "Now look at this. The queen is completely undefended. I play Bxq... and just like that,
  I'm up a queen. I genuinely did not see this coming three moves ago."
- Checks: short, building tension
  e.g. "Check. King has to move."
- Castling: brief
  e.g. "I castle here — king safety first"
- Checkmate/resignation: satisfying conclusion, 2-3 sentences
  e.g. "And that's checkmate. The king has nowhere to go.
  This is what 946 rated chess looks like on a good day."
- Add ONE funny self-deprecating line somewhere in the middlegame
- Do NOT comment on boring moves

Also add TWO special entries:
1. half_move: 0  — the intro (before move 1)
   Commentary: Hook opener. Funny, references rating, sets up the matchup.
   hold_seconds: 4
2. half_move: 99999 — the outro (after last move)
   Commentary: Wrap up, subscribe CTA in his style.
   hold_seconds: 5

Return ONLY valid JSON array. No markdown, no explanation."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()
    # Strip markdown fences if present
    raw = re.sub(r'^```json\s*', '', raw)
    raw = re.sub(r'^```\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)

    try:
        commentary = json.loads(raw)
        return commentary
    except json.JSONDecodeError as e:
        print(f"  ⚠️  JSON parse error: {e}")
        print(f"  Raw response: {raw[:300]}")
        return []

def generate_metadata(moves_info, meta):
    """Generate YouTube title, description, hashtags, Instagram caption."""
    diff     = meta["opp_rating"] - meta["my_rating"]
    diff_str = f"{abs(diff)} points {'higher' if diff > 0 else 'lower'} rated"

    prompt = f"""Write YouTube and Instagram metadata for Abhishek's chess video.

Style: self-deprecating, deadpan, funny. "The Thinking Athlete" brand.
Rating: {meta['my_rating']}. Won by {meta['win_method']} vs {meta['opp_name']} ({meta['opp_rating']}) — {diff_str}.
Opening: {meta['opening']} ({meta['eco']}). Time: {meta['time_ctrl']}. Date: {meta['date']}.

Generate using EXACT section headers:

===YOUTUBE TITLE===
Max 70 chars. Punchy, funny, references opening or rating.

===YOUTUBE DESCRIPTION===
3-4 paragraphs. Hook, opening explained simply, key moment, subscribe CTA. His voice throughout.

===YOUTUBE HASHTAGS===
12 hashtags. Opening-specific + chess general + india + brand + rating journey.

===INSTAGRAM CAPTION===
4-5 lines max. Punchy. Ends with a question.

===INSTAGRAM HASHTAGS===
10 hashtags for Reels reach.

Return only the content. No meta-commentary."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text.strip()

def parse_metadata_sections(raw):
    sections = {"yt_title":"", "yt_desc":"", "yt_tags":"", "ig_caption":"", "ig_tags":""}
    markers  = {
        "===YOUTUBE TITLE===":       "yt_title",
        "===YOUTUBE DESCRIPTION===": "yt_desc",
        "===YOUTUBE HASHTAGS===":    "yt_tags",
        "===INSTAGRAM CAPTION===":   "ig_caption",
        "===INSTAGRAM HASHTAGS===":  "ig_tags",
    }
    current = None
    for line in raw.split("\n"):
        if line.strip() in markers:
            current = markers[line.strip()]; continue
        if current:
            sections[current] += line + "\n"
    for k in sections:
        sections[k] = sections[k].strip()
    return sections

def save_outputs(game_dir, index, game_data, meta, commentary, sections):
    """Save commentary.json and script.txt into game folder."""

    # Save commentary JSON for step4
    commentary_path = os.path.join(game_dir, "commentary.json")
    with open(commentary_path, "w") as f:
        json.dump({
            "meta":       meta,
            "commentary": commentary,
        }, f, indent=2)

    # Save script.txt with everything
    side     = get_my_side(game_data)
    opp_side = "black" if side == "white" else "white"
    white    = game_data["white"]["username"]
    black    = game_data["black"]["username"]
    dt       = datetime.fromtimestamp(game_data.get("end_time", 0)).strftime("%Y-%m-%d")

    out = []
    out.append("=" * 65)
    out.append(f"GAME {index:03d}: {white} vs {black}")
    out.append(f"Date: {dt}  |  My Rating: {meta['my_rating']}  |  Opponent: {meta['opp_rating']}")
    out.append(f"Opening: {meta['opening']} ({meta['eco']})  |  Won by: {meta['win_method']}")
    out.append("=" * 65)

    out.append("\n📹 MOVE-BY-MOVE COMMENTARY (synced to video)")
    out.append("─" * 40)
    for c in sorted(commentary, key=lambda x: x["half_move"]):
        if c["half_move"] == 0:
            out.append(f"\n[INTRO — hold {c['hold_seconds']}s]")
        elif c["half_move"] == 99999:
            out.append(f"\n[OUTRO — hold {c['hold_seconds']}s]")
        else:
            move_idx = c["half_move"] - 1
            move_num = (move_idx // 2) + 1
            whose    = "Abhishek" if (move_idx % 2 == 0 and side == "white") or \
                                     (move_idx % 2 == 1 and side == "black") else meta["opp_name"]
            out.append(f"\n[Move {move_num} — {whose} — hold {c['hold_seconds']}s]")
        out.append(c["commentary"])

    out.append("\n\n🎬 YOUTUBE TITLE")
    out.append("─" * 40)
    out.append(sections["yt_title"])

    out.append("\n\n📋 YOUTUBE DESCRIPTION")
    out.append("─" * 40)
    out.append(sections["yt_desc"])

    out.append("\n\n#️⃣  YOUTUBE HASHTAGS")
    out.append("─" * 40)
    out.append(sections["yt_tags"])

    out.append("\n\n📱 INSTAGRAM CAPTION")
    out.append("─" * 40)
    out.append(sections["ig_caption"])

    out.append("\n\n#️⃣  INSTAGRAM HASHTAGS")
    out.append("─" * 40)
    out.append(sections["ig_tags"])

    script_path = os.path.join(game_dir, "script.txt")
    with open(script_path, "w") as f:
        f.write("\n".join(out))

def main():
    if not os.path.exists(INPUT_FILE):
        print(f"❌ {INPUT_FILE} not found — run step1 first!")
        sys.exit(1)

    with open(INPUT_FILE) as f:
        games = json.load(f)

    if not games:
        print("❌ No games found."); sys.exit(1)

    print(f"📝 Generating synced commentary for {len(games)} games...\n")

    success = 0
    for i, gd in enumerate(games):
        white    = gd["white"]["username"]
        black    = gd["black"]["username"]
        dt       = datetime.fromtimestamp(gd.get("end_time", 0)).strftime("%Y-%m-%d")
        game_dir = get_game_dir(gd, i+1)

        print(f"[{i+1:03d}/{len(games)}] {white} vs {black} | {dt}")

        if os.path.exists(os.path.join(game_dir, "commentary.json")) and \
           os.path.exists(os.path.join(game_dir, "script.txt")):
            print(f"  ⏭️  Already exists, skipping.")
            success += 1
            continue

        try:
            moves_info, meta = analyse_game(gd)
            if not moves_info:
                print(f"  ⚠️  No moves found, skipping."); continue

            key_count = sum(1 for m in moves_info if m["is_key"])
            print(f"  ♟️  {len(moves_info)} moves | {key_count} key moments | {meta['opening']}")

            print(f"  🤖 Generating commentary...")
            commentary = generate_commentary(moves_info, meta)
            print(f"  🤖 Generating metadata...")
            metadata_raw = generate_metadata(moves_info, meta)
            sections     = parse_metadata_sections(metadata_raw)

            save_outputs(game_dir, i+1, gd, meta, commentary, sections)
            print(f"  ✅ commentary.json + script.txt saved")
            print(f"  📌 Title: {sections['yt_title'][:70]}")
            success += 1

        except Exception as e:
            print(f"  ❌ Error: {e}")
            import traceback; traceback.print_exc()

    print(f"\n🏁 Done! {success}/{len(games)} games processed.")
    print(f"📂 Files saved in each game folder in {os.path.abspath(VIDEOS_DIR)}/")

if __name__ == "__main__":
    main()
