"""
STEP 2 — Generate Landscape + Portrait Videos for ALL Won Games
The Thinking Athlete Pipeline

Features:
  - Landscape 1280x720  → videos/YYYY/MM_Month/landscape/
  - Portrait  1080x1920 → videos/YYYY/MM_Month/portrait/
  - Wikipedia PNG chess pieces
  - Move sound / capture sound / castle sound / promote sound
  - Animated confetti on game end
  - King highlight on check
  - Move list panel
  - Skips already-generated videos

Requirements:
    pip install chess imageio imageio-ffmpeg pillow numpy requests
    brew install ffmpeg
"""

import chess
import chess.pgn
import imageio
import numpy as np
import requests
import json
import io
import os
import sys
import subprocess
import random
import calendar
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont


# ── Clock parsing ─────────────────────────────────────────────────────────────

def parse_clocks(game):
    """
    Extract clock times from PGN comments like { [%clk 0:09:45] }
    Returns list of (white_clk, black_clk) strings per move pair,
    indexed by move number (0 = before game starts).
    """
    clocks = []   # one entry per half-move: "0:09:45" or None
    node = game
    while node.variations:
        node = node.variations[0]
        clk = None
        comment = node.comment or ""
        if "[%clk" in comment:
            try:
                clk = comment.split("[%clk")[1].split("]")[0].strip()
            except:
                clk = None
        clocks.append(clk)
    return clocks

def fmt_clk(clk_str):
    """Format clock string nicely. Returns '--:--' if None."""
    if not clk_str:
        return "--:--"
    try:
        # clk_str is like "0:09:45" or "0:01:23" or "0:00:57.6"
        parts = clk_str.split(":")
        if len(parts) == 3:
            h = int(parts[0])
            m = int(parts[1])
            s = int(float(parts[2]))  # handle decimal seconds like 57.6
            if h > 0:
                return f"{h}:{m:02d}:{s:02d}"
            return f"{m}:{s:02d}"
        return clk_str
    except:
        return "--:--"

def get_clocks_at_move(clocks, move_idx):
    """
    Return (white_clk, black_clk) display strings after move_idx half-moves.
    move_idx 0 = start, 1 = after white's first move, 2 = after black's first, etc.
    """
    w_clk = b_clk = None
    # White moves at even indices (0,2,4...), black at odd (1,3,5...)
    for i in range(min(move_idx, len(clocks))):
        if i % 2 == 0:   # white's move
            w_clk = clocks[i]
        else:             # black's move
            b_clk = clocks[i]
    return fmt_clk(w_clk), fmt_clk(b_clk)

# ── Config ────────────────────────────────────────────────────────────────────
USERNAME   = "abhi15041984"
FPS        = 1
OUTPUT_DIR = "videos"
PIECES_DIR = "pieces"
SOUNDS_DIR = "sounds"
CONFETTI_FRAMES = 5   # frames of animated confetti at end
# ─────────────────────────────────────────────────────────────────────────────

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(PIECES_DIR, exist_ok=True)
os.makedirs(SOUNDS_DIR, exist_ok=True)

# Colors
AMBER      = (239, 159, 39)
WHITE_C    = (255, 255, 255)
DARK_C     = (13,  13,  15)
PANEL_C    = (22,  22,  24)
GRAY_C     = (136, 136, 136)
GRAY_DK    = (42,  42,  46)
LIGHT_SQ   = (240, 217, 181)
DARK_SQ    = (181, 136, 99)
HL_LIGHT   = (205, 210, 106)
HL_DARK    = (170, 162, 58)
CHECK_CLR  = (220, 50,  50)

CONFETTI_COLORS = [
    (255, 215, 0), (255, 69, 0), (50, 205, 50),
    (30, 144, 255), (238, 130, 238), (255, 165, 0),
    (0, 255, 200), (239, 159, 39), (255, 20, 147),
]

PIECE_NAMES = {
    chess.PAWN:   "P", chess.ROOK:   "R", chess.KNIGHT: "N",
    chess.BISHOP: "B", chess.QUEEN:  "Q", chess.KING:   "K",
}

MONTH_NAMES = {
    1:"01_January", 2:"02_February", 3:"03_March", 4:"04_April",
    5:"05_May",     6:"06_June",     7:"07_July",  8:"08_August",
    9:"09_September",10:"10_October",11:"11_November",12:"12_December"
}

BASE_URL = "https://raw.githubusercontent.com/oakmac/chessboardjs/master/website/img/chesspieces/wikipedia"

# ── Folder structure ──────────────────────────────────────────────────────────

def get_output_paths(game_data, index):
    """Return (landscape_path, portrait_path, game_dir) — one folder per game."""
    end_time  = game_data.get("end_time", 0)
    dt        = datetime.fromtimestamp(end_time)
    year      = str(dt.year)
    month_dir = MONTH_NAMES[dt.month]

    white    = game_data["white"]["username"]
    black    = game_data["black"]["username"]
    game_dir = os.path.join(OUTPUT_DIR, year, month_dir,
                            f"game_{index:03d}_{white}_vs_{black}")
    os.makedirs(game_dir, exist_ok=True)

    return (
        os.path.join(game_dir, "landscape.mp4"),
        os.path.join(game_dir, "portrait.mp4"),
        game_dir,
    )

# ── Sound ─────────────────────────────────────────────────────────────────────

def get_sound_paths():
    sounds = {
        "move":    os.path.join(SOUNDS_DIR, "move1.mp3"),
        "capture": os.path.join(SOUNDS_DIR, "capture.mp3"),
        "castle":  os.path.join(SOUNDS_DIR, "castle.mp3"),
        "promote": os.path.join(SOUNDS_DIR, "promote.mp3"),
    }
    for name, path in sounds.items():
        if not os.path.exists(path):
            print(f"  ❌ Missing sound: {path}")
            sys.exit(1)
    return sounds

def classify_move(board, move):
    """Return sound type for a move: capture / castle / promote / move."""
    if board.is_castling(move):
        return "castle"
    if move.promotion:
        return "promote"
    if board.is_capture(move):
        return "capture"
    return "move"

def build_audio_track(move_types, fps=FPS):
    """Build audio track with correct sound per move. Silent during confetti."""
    sounds     = get_sound_paths()
    num_moves  = len(move_types)
    # Audio ends at last move — confetti hold is silent
    total_dur  = (2 + num_moves) / fps

    inputs  = []
    filters = []
    for i, mtype in enumerate(move_types):
        sound     = sounds[mtype]
        offset_ms = int((2 + i) * 1000 / fps)
        inputs   += ["-i", sound]
        filters.append(f"[{i}]adelay={offset_ms}|{offset_ms}[a{i}]")

    mix = "".join(f"[a{i}]" for i in range(num_moves))
    filters.append(f"{mix}amix=inputs={num_moves}:normalize=0:duration=longest[out]")

    out = os.path.join(SOUNDS_DIR, "track.aac")
    cmd = (["ffmpeg", "-y"] + inputs +
           ["-filter_complex", ";".join(filters),
            "-map", "[out]", "-t", str(total_dur), "-c:a", "aac", out])
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        print(f"  ⚠️ Audio failed: {r.stderr.decode()[-200:]}")
        return None
    return out

def mux_audio(video_path, audio_path):
    if not audio_path or not os.path.exists(audio_path):
        return False
    out = video_path.replace(".mp4", "_final.mp4")
    cmd = ["ffmpeg", "-y",
           "-i", video_path, "-i", audio_path,
           "-filter_complex", "[1:a]apad[aout]",
           "-map", "0:v", "-map", "[aout]",
           "-c:v", "copy", "-c:a", "aac", "-shortest", out]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode == 0:
        os.replace(out, video_path)
        return True
    print(f"  ⚠️ Mux failed: {r.stderr.decode()[-150:]}")
    return False

# ── Pieces ────────────────────────────────────────────────────────────────────

def download_pieces():
    for c in ["w", "b"]:
        for p in ["P","R","N","B","Q","K"]:
            fn = f"{c}{p}.png"
            fp = os.path.join(PIECES_DIR, fn)
            if not os.path.exists(fp):
                print(f"  Downloading {fn}...")
                r = requests.get(f"{BASE_URL}/{fn}", timeout=10)
                if r.status_code == 200:
                    open(fp, "wb").write(r.content)
                else:
                    print(f"  ❌ Failed: {fn}"); sys.exit(1)

def load_pieces(sq_size):
    """Load pieces resized to sq_size."""
    pieces = {}
    for color in [chess.WHITE, chess.BLACK]:
        cc = "w" if color == chess.WHITE else "b"
        for pt, pc in PIECE_NAMES.items():
            img = Image.open(os.path.join(PIECES_DIR, f"{cc}{pc}.png")).convert("RGBA")
            pieces[(color, pt)] = img.resize((sq_size, sq_size), Image.LANCZOS)
    return pieces

def load_all_pieces():
    """Load pieces for both landscape and portrait square sizes."""
    land_sq = 680 // 8          # 85px
    port_sq = (1080 - 40) // 8  # 130px
    return {
        "landscape": load_pieces(land_sq),
        "portrait":  load_pieces(port_sq),
    }

# ── Fonts ─────────────────────────────────────────────────────────────────────

def get_font(size, bold=False):
    for p in ["/System/Library/Fonts/Helvetica.ttc", "/Library/Fonts/Arial.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
              else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        if os.path.exists(p):
            try: return ImageFont.truetype(p, size)
            except: continue
    return ImageFont.load_default()

def make_fonts(scale=1.0):
    return {
        "xl":      get_font(int(30*scale), bold=True),
        "lg":      get_font(int(22*scale), bold=True),
        "md":      get_font(int(18*scale)),
        "sm":      get_font(int(13*scale)),
        "sm_bold": get_font(int(13*scale), bold=True),
        "xs":      get_font(int(10*scale)),
    }


# ── Game metadata ─────────────────────────────────────────────────────────────

def parse_game_meta(game):
    """Extract opening, ECO, time control, termination from PGN headers."""
    h = game.headers

    opening  = h.get("Opening", "")
    eco      = h.get("ECO", "")
    term     = h.get("Termination", "")
    date_str = h.get("Date", "").replace(".", "-")

    # Parse time control — "600" → "10 min", "180+2" → "3 min +2"
    tc_raw = h.get("TimeControl", "")
    tc_str = fmt_time_control(tc_raw)

    # Shorten termination — "Abhi15041984 won by checkmate" → "by checkmate"
    term_short = ""
    for kw in ["by checkmate", "by resignation", "by timeout",
                "on time", "by stalemate", "by insufficient"]:
        if kw in term.lower():
            term_short = kw.replace("by ", "").capitalize()
            break
    if not term_short and term:
        term_short = term.split("won")[-1].strip().capitalize() if "won" in term else ""

    return {
        "opening":    opening,
        "eco":        eco,
        "time_ctrl":  tc_str,
        "termination": term_short,
        "date":       date_str,
    }

def fmt_time_control(tc):
    """Convert '600' → '10 min Rapid', '180' → '3 min Blitz', '60+1' → '1 min Bullet'."""
    if not tc or tc == "-":
        return ""
    try:
        base = int(tc.split("+")[0])
        inc  = int(tc.split("+")[1]) if "+" in tc else 0
        mins = base // 60
        inc_str = f" +{inc}" if inc else ""
        if mins >= 10:   label = "Rapid"
        elif mins >= 3:  label = "Blitz"
        else:            label = "Bullet"
        return f"{mins} min{inc_str} {label}"
    except:
        return tc

# ── Board ─────────────────────────────────────────────────────────────────────

def draw_board(board, pieces, last_move=None, sq_size=80, flip=False):
    """Draw board. flip=True shows it from Black's perspective (Abhishek on bottom)."""
    bpx  = sq_size * 8
    img  = Image.new("RGBA", (bpx, bpx), DARK_C)
    draw = ImageDraw.Draw(img)
    cf   = get_font(max(9, sq_size // 7))
    lsq  = {last_move.from_square, last_move.to_square} if last_move else set()

    check_sq = None
    if board.is_check():
        k = board.king(board.turn)
        if k is not None:
            check_sq = k

    for rank in range(7, -1, -1):
        for file in range(8):
            sq  = chess.square(file, rank)
            # Flip board if Abhishek is Black
            if flip:
                x = (7 - file) * sq_size
                y = rank * sq_size
            else:
                x = file * sq_size
                y = (7 - rank) * sq_size
            isl = (file + rank) % 2 == 1

            if sq == check_sq:      col = CHECK_CLR
            elif sq in lsq:         col = HL_LIGHT if isl else HL_DARK
            else:                   col = LIGHT_SQ if isl else DARK_SQ

            draw.rectangle([x, y, x+sq_size, y+sq_size], fill=col)

            if sq == check_sq:
                b = 3
                draw.rectangle([x+b, y+b, x+sq_size-b, y+sq_size-b],
                                outline=(255,80,80), width=b)

            cc = DARK_SQ if isl else LIGHT_SQ
            if (file == 0 and not flip) or (file == 7 and flip):
                draw.text((x+3, y+2), str(rank+1), fill=cc, font=cf)
            if (rank == 0 and not flip) or (rank == 7 and flip):
                draw.text((x+sq_size-11, y+sq_size-15), "abcdefgh"[file], fill=cc, font=cf)

            piece = board.piece_at(sq)
            if piece:
                pi = pieces.get((piece.color, piece.piece_type))
                if pi:
                    # Center piece on square
                    pw, ph = pi.size
                    ox = x + (sq_size - pw) // 2
                    oy = y + (sq_size - ph) // 2
                    img.paste(pi, (ox, oy), pi)

    return img.convert("RGB")

# ── Confetti (animated) ───────────────────────────────────────────────────────

def make_confetti_particles(W, H, count=200, seed=0):
    """Generate particle positions — returns list of particle dicts."""
    rng = random.Random(seed)
    particles = []
    for _ in range(count):
        particles.append({
            "x":     rng.randint(0, W),
            "y":     rng.randint(-H, H),   # start above screen
            "vx":    rng.uniform(-2, 2),
            "vy":    rng.uniform(8, 20),    # falling speed
            "w":     rng.randint(8, 20),
            "h":     rng.randint(4, 10),
            "color": rng.choice(CONFETTI_COLORS),
            "shape": rng.choice(["rect", "ellipse"]),
            "rot":   rng.randint(0, 90),
        })
    return particles

def draw_confetti_frame(draw, particles, W, H, frame_idx):
    """Draw confetti particles at their position for this frame."""
    for p in particles:
        x = int(p["x"] + p["vx"] * frame_idx * 8) % W
        y = int(p["y"] + p["vy"] * frame_idx * 8) % H
        w, h = p["w"], p["h"]
        color = p["color"]
        if p["shape"] == "rect":
            draw.rectangle([x, y, x+w, y+h], fill=color)
        else:
            draw.ellipse([x, y, x+w, y+h], fill=color)

def draw_winner_banner(draw, W, H, winner_text, fonts, term=""):
    cy = H // 2
    draw.rectangle([0, cy-70, W, cy+70], fill=(0,0,0))
    draw.rectangle([0, cy-70, W, cy-66], fill=AMBER)
    draw.rectangle([0, cy+66, W, cy+70], fill=AMBER)
    draw.text((W//2, cy-28), "GAME OVER", fill=GRAY_C, font=fonts["md"], anchor="mm")
    draw.text((W//2, cy+10), winner_text,  fill=AMBER,  font=fonts["xl"], anchor="mm")
    if term:
        draw.text((W//2, cy+48), term, fill=GRAY_C, font=fonts["sm"], anchor="mm")

# ── Move list ─────────────────────────────────────────────────────────────────

def format_move_pairs(moves):
    board = chess.Board()
    pairs, i, n = [], 0, 1
    while i < len(moves):
        ws = board.san(moves[i]); board.push(moves[i]); i += 1
        bs = ""
        if i < len(moves):
            bs = board.san(moves[i]); board.push(moves[i]); i += 1
        pairs.append((n, ws, bs)); n += 1
    return pairs

def draw_move_list(draw, pairs, cur_idx, px, py, pw, max_h, fonts):
    rh   = int(22 * (pw / 540))   # scale row height with panel width
    vis  = max_h // rh
    cpair = max(0, (cur_idx - 1) // 2)
    iswh  = (cur_idx % 2 == 1)
    cnw   = int(pw * 0.14)
    cww   = int(pw * 0.38)

    start = max(0, cpair - vis // 2)
    end   = min(len(pairs), start + vis)

    draw.text((px, py-22), "MOVES", fill=GRAY_C, font=fonts["xs"])
    draw.line([px, py-5, px+pw, py-5], fill=GRAY_DK, width=1)

    for i, (mn, ws, bs) in enumerate(pairs[start:end]):
        pidx = start + i
        y    = py + i * rh
        iscur = (pidx == cpair) and (cur_idx > 0)
        if iscur:
            draw.rectangle([px-4, y-2, px+pw, y+rh-4], fill=(35,35,25))
        draw.text((px, y), f"{mn}.", fill=GRAY_C, font=fonts["xs"])
        wc = AMBER if (iscur and iswh)  else WHITE_C
        wf = fonts["sm_bold"] if (iscur and iswh)  else fonts["sm"]
        draw.text((px+cnw, y), ws, fill=wc, font=wf)
        if bs:
            bc = AMBER if (iscur and not iswh) else (200,200,200)
            bf = fonts["sm_bold"] if (iscur and not iswh) else fonts["sm"]
            draw.text((px+cnw+cww, y), bs, fill=bc, font=bf)

# ── Frame builders ────────────────────────────────────────────────────────────

def make_landscape_frame(board, pieces, move_pairs, cur_idx,
                         move=None, move_num=0, total=0,
                         flip=False,
                         top_name="", top_rating=0, top_clk="--:--",
                         bot_name="", bot_rating=0, bot_clk="--:--",
                         meta=None,
                         confetti_particles=None, confetti_fidx=0, winner_text=""):
    W, H = 1280, 720
    img  = Image.new("RGB", (W, H), DARK_C)
    draw = ImageDraw.Draw(img)
    F    = make_fonts(1.0)

    draw.rectangle([0,0,W,4], fill=AMBER)
    draw.rectangle([0,H-4,W,H], fill=AMBER)

    sq  = 680 // 8
    bi  = draw_board(board, pieces, move, sq_size=sq, flip=flip)
    img.paste(bi, (20, (H - sq*8)//2))

    px, pw = 720, W-720-20

    draw.text((px,22),  "The Thinking Athlete", fill=AMBER, font=F["lg"])
    draw.line([px,52,W-20,52], fill=AMBER, width=1)

    draw.text((px,62),  "OPPONENT", fill=GRAY_C,  font=F["xs"])
    draw.text((px,76),  top_name,   fill=WHITE_C,  font=F["md"])
    draw.text((px,97),  f"Rating: {top_rating}", fill=GRAY_C, font=F["sm"])
    draw.text((px+pw-60,76), top_clk, fill=AMBER, font=F["md"])
    draw.line([px,118,W-20,118], fill=GRAY_DK, width=1)

    draw.text((px,126), "YOU ♟",   fill=AMBER,   font=F["xs"])
    draw.text((px,140), bot_name,   fill=WHITE_C,  font=F["md"])
    draw.text((px,161), f"Rating: {bot_rating}", fill=GRAY_C, font=F["sm"])
    draw.text((px+pw-60,140), bot_clk, fill=AMBER, font=F["md"])
    draw.line([px,182,W-20,182], fill=GRAY_DK, width=1)

    # Opening + time control
    if meta:
        if meta["opening"]:
            eco_str  = f"[{meta['eco']}] " if meta["eco"] else ""
            opening  = meta["opening"]
            # Truncate long opening names to fit panel
            if len(opening) > 28:
                opening = opening[:26] + "…"
            draw.text((px,190), f"{eco_str}{opening}", fill=AMBER, font=F["sm"])
        if meta["time_ctrl"]:
            draw.text((px,206), meta["time_ctrl"], fill=GRAY_C, font=F["xs"])
        draw.line([px,220,W-20,220], fill=GRAY_DK, width=1)
        move_y = 228
    else:
        move_y = 190

    draw.text((px, move_y),    "MOVE",   fill=GRAY_C,  font=F["xs"])
    draw.text((px, move_y+16), f"{move_num}  /  {total}", fill=AMBER, font=F["xl"])

    by2 = (move_y + 48) if meta else 248
    draw.rounded_rectangle([px,by2,px+pw,by2+8], radius=4, fill=GRAY_DK)
    if total > 0 and move_num > 0:
        draw.rounded_rectangle([px,by2,px+int(pw*move_num/total),by2+8], radius=4, fill=AMBER)

    chk_y = by2 + 18
    if board.is_check():
        draw.text((px, chk_y), "⚠ CHECK!", fill=CHECK_CLR, font=F["sm"])
    else:
        tc = (220,220,220) if board.turn==chess.WHITE else (160,160,160)
        draw.text((px, chk_y), "White to move" if board.turn==chess.WHITE else "Black to move",
                  fill=tc, font=F["sm"])

    draw_move_list(draw, move_pairs, cur_idx, px, chk_y+28, pw, H-chk_y-55, F)
    draw.text((px,H-14), "@TheThinkingAthlete", fill=(55,55,60), font=F["xs"])

    # Animated confetti — drawn last
    if confetti_particles:
        draw_confetti_frame(draw, confetti_particles, W, H, confetti_fidx)
        draw_winner_banner(draw, W, H, winner_text, F, term=meta.get('termination','') if meta else '')

    return img

def make_portrait_frame(board, pieces, move_pairs, cur_idx,
                        move=None, move_num=0, total=0,
                        flip=False,
                        top_name="", top_rating=0, top_clk="--:--",
                        bot_name="", bot_rating=0, bot_clk="--:--",
                        meta=None,
                        confetti_particles=None, confetti_fidx=0, winner_text=""):
    W, H = 1080, 1920
    img  = Image.new("RGB", (W, H), DARK_C)
    draw = ImageDraw.Draw(img)
    F    = make_fonts(1.3)

    draw.rectangle([0,0,W,5],   fill=AMBER)
    draw.rectangle([0,H-5,W,H], fill=AMBER)

    # Channel name top
    draw.text((W//2, 60), "The Thinking Athlete", fill=AMBER, font=F["lg"], anchor="mm")
    draw.line([40, 90, W-40, 90], fill=AMBER, width=1)

    # Board centred, top half
    sq      = (W - 40) // 8
    bi      = draw_board(board, pieces, move, sq_size=sq, flip=flip)
    board_y = 110
    img.paste(bi, (20, board_y))

    # Info panel below board
    py  = board_y + sq*8 + 30
    px  = 40
    pw  = W - 80

    # Players side by side
    hw = pw // 2 - 10
    # White box
    draw.rounded_rectangle([px, py, px+hw, py+90], radius=8, fill=PANEL_C)
    draw.text((px+10, py+10), "OPPONENT", fill=GRAY_C,  font=F["xs"])
    draw.text((px+10, py+30), top_name,   fill=WHITE_C,  font=F["sm"])
    draw.text((px+10, py+58), f"⭐ {top_rating}", fill=AMBER, font=F["sm"])
    draw.text((px+hw-70, py+58), top_clk, fill=AMBER, font=F["sm"])
    # You box
    bx = px + hw + 20
    draw.rounded_rectangle([bx, py, bx+hw, py+90], radius=8, fill=PANEL_C)
    draw.text((bx+10, py+10), "YOU ♟",   fill=AMBER,   font=F["xs"])
    draw.text((bx+10, py+30), bot_name,   fill=WHITE_C,  font=F["sm"])
    draw.text((bx+10, py+58), f"⭐ {bot_rating}", fill=AMBER, font=F["sm"])
    draw.text((bx+hw-70, py+58), bot_clk, fill=AMBER, font=F["sm"])

    py += 110

    # Opening name
    if meta and meta["opening"]:
        eco_str  = f"[{meta['eco']}] " if meta["eco"] else ""
        opening  = meta["opening"]
        if len(opening) > 32:
            opening = opening[:30] + "…"
        draw.text((W//2, py), f"{eco_str}{opening}",
                  fill=AMBER, font=F["sm"], anchor="mm")
        py += 26
    if meta and meta["time_ctrl"]:
        draw.text((W//2, py), meta["time_ctrl"], fill=GRAY_C, font=F["sm"], anchor="mm")
        py += 26
    draw.line([px, py, px+pw, py], fill=GRAY_DK, width=1)
    py += 16

    # Move counter
    draw.text((W//2, py), f"Move {move_num} / {total}", fill=AMBER,
              font=F["xl"], anchor="mm")
    py += 50

    # Progress bar
    draw.rounded_rectangle([px, py, px+pw, py+12], radius=6, fill=GRAY_DK)
    if total > 0 and move_num > 0:
        draw.rounded_rectangle([px, py, px+int(pw*move_num/total), py+12],
                                radius=6, fill=AMBER)
    py += 30

    # Check / turn
    if board.is_check():
        draw.text((W//2, py), "⚠  CHECK!", fill=CHECK_CLR, font=F["sm"], anchor="mm")
    else:
        tc = (220,220,220) if board.turn==chess.WHITE else (160,160,160)
        draw.text((W//2, py),
                  "White to move" if board.turn==chess.WHITE else "Black to move",
                  fill=tc, font=F["sm"], anchor="mm")
    py += 36

    # Move list
    draw_move_list(draw, move_pairs, cur_idx, px, py, pw, H-py-60, F)

    draw.text((W//2, H-40), "@TheThinkingAthlete", fill=(55,55,60),
              font=F["xs"], anchor="mm")

    # Animated confetti — drawn last
    if confetti_particles:
        draw_confetti_frame(draw, confetti_particles, W, H, confetti_fidx)
        draw_winner_banner(draw, W, H, winner_text, F, term=meta.get('termination','') if meta else '')

    return img

# ── Video generator ───────────────────────────────────────────────────────────

def write_video(frames, path, fps=FPS):
    writer = imageio.get_writer(
        path, fps=fps, codec="libx264",
        output_params=["-crf", "23", "-pix_fmt", "yuv420p"]
    )
    for f in frames:
        writer.append_data(np.array(f))
    writer.close()

def generate_videos(game_data, all_pieces, land_path, port_path, game_dir):
    pgn_text = game_data.get("pgn", "")
    if not pgn_text:
        print("  ❌ No PGN, skipping."); return False

    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if not game:
        print("  ❌ Bad PGN, skipping."); return False

    wname = game_data["white"]["username"]
    bname = game_data["black"]["username"]
    wr    = game_data["white"]["rating"]
    br    = game_data["black"]["rating"]
    wres  = game_data["white"]["result"]
    winner_text = f"{wname} wins!" if wres=="win" else f"{bname} wins!" \
                  if game_data["black"]["result"]=="win" else "Draw!"

    board      = game.board()
    moves      = list(game.mainline_moves())
    move_pairs = format_move_pairs(moves)
    clocks     = parse_clocks(game)
    meta       = parse_game_meta(game)
    land_pieces = all_pieces["landscape"]
    port_pieces = all_pieces["portrait"]

    # Flip board if Abhishek plays as Black — so he's always on bottom
    my_side = "white" if game_data["white"]["username"].lower() == USERNAME.lower() else "black"
    flip    = (my_side == "black")

    # Opponent always on top, Abhishek always on bottom
    if my_side == "white":
        top_name, top_rating    = bname, br
        bot_name, bot_rating    = wname, wr
        top_clk_key, bot_clk_key = "b", "w"
    else:
        top_name, top_rating    = wname, wr
        bot_name, bot_rating    = bname, br
        top_clk_key, bot_clk_key = "w", "b"

    # Classify each move for audio
    move_types = []
    tb = game.board()
    for mv in moves:
        move_types.append(classify_move(tb, mv))
        tb.push(mv)

    # Confetti particles (fixed set, animated by frame index)
    land_particles = make_confetti_particles(1280, 720,  count=200, seed=42)
    port_particles = make_confetti_particles(1080, 1920, count=300, seed=42)

    land_frames, port_frames = [], []

    # Common args builder
    def common(move_num, move, cur_idx, cp=None, cf=0):
        wc, bc = get_clocks_at_move(clocks, cur_idx)
        top_clk = bc if my_side == "white" else wc
        bot_clk = wc if my_side == "white" else bc
        return dict(move_num=move_num, total=len(moves),
                    flip=flip,
                    top_name=top_name, top_rating=top_rating, top_clk=top_clk,
                    bot_name=bot_name, bot_rating=bot_rating, bot_clk=bot_clk,
                    meta=meta,
                    confetti_particles=cp, confetti_fidx=cf,
                    winner_text=winner_text if cp else "")

    # Opening hold — 2 frames
    for _ in range(2):
        land_frames.append(make_landscape_frame(board, land_pieces, move_pairs, 0,
                           move=None, **common(0, None, 0)))
        port_frames.append(make_portrait_frame(board, port_pieces, move_pairs, 0,
                           move=None, **common(0, None, 0)))

    # One frame per move
    for i, mv in enumerate(moves):
        board.push(mv)
        is_last = (i == len(moves)-1)
        land_frames.append(make_landscape_frame(board, land_pieces, move_pairs, i+1,
                           move=mv, **common(i+1, mv, i+1)))
        port_frames.append(make_portrait_frame(board, port_pieces, move_pairs, i+1,
                           move=mv, **common(i+1, mv, i+1)))
        if (i+1) % 10 == 0:
            print(f"  ... {i+1}/{len(moves)} moves")

    # Animated confetti — CONFETTI_FRAMES frames
    for fi in range(CONFETTI_FRAMES):
        land_frames.append(make_landscape_frame(board, land_pieces, move_pairs, len(moves),
                           move=moves[-1] if moves else None,
                           **common(len(moves), None, len(moves),
                                    cp=land_particles, cf=fi)))
        port_frames.append(make_portrait_frame(board, port_pieces, move_pairs, len(moves),
                           move=moves[-1] if moves else None,
                           **common(len(moves), None, len(moves),
                                    cp=port_particles, cf=fi)))

    # Write silent videos
    land_tmp = land_path.replace(".mp4", "_silent.mp4")
    port_tmp = port_path.replace(".mp4", "_silent.mp4")
    print(f"  🎬 Writing landscape...")
    write_video(land_frames, land_tmp)
    print(f"  🎬 Writing portrait...")
    write_video(port_frames, port_tmp)

    # Build audio once, mux into both
    print(f"  🔊 Building audio track...")
    audio = build_audio_track(move_types, FPS)
    mux_audio(land_tmp, audio)
    mux_audio(port_tmp, audio)

    # Rename if silent still exists
    for tmp, final in [(land_tmp, land_path), (port_tmp, port_path)]:
        if os.path.exists(tmp):
            os.rename(tmp, final)

    ls = os.path.getsize(land_path)/1024/1024
    ps = os.path.getsize(port_path)/1024/1024
    print(f"  ✅ Landscape: {ls:.1f}MB  |  Portrait: {ps:.1f}MB")
    return True

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not os.path.exists("won_games.json"):
        print("❌ won_games.json not found — run step1_fetch_games.py first!")
        sys.exit(1)

    with open("won_games.json") as f:
        games = json.load(f)

    if not games:
        print("❌ No games found."); sys.exit(1)

    # Respect MAX_UPLOADS — no point generating more than we can upload
    max_uploads = int(os.environ.get("MAX_UPLOADS", 0))
    if max_uploads > 0 and len(games) > max_uploads:
        print(f"⚙️  MAX_UPLOADS={max_uploads} — limiting to {max_uploads} of {len(games)} games")
        games = games[:max_uploads]

    print(f"🎮 {len(games)} games to process\n")
    print("🖼️  Checking piece images...")
    download_pieces()
    print("🔊 Checking sounds...")
    get_sound_paths()
    print("✅ Assets ready!\n")

    all_pieces = load_all_pieces()
    pieces     = all_pieces  # passed to generate_videos
    success = 0

    for i, gd in enumerate(games):
        white = gd["white"]["username"]
        black = gd["black"]["username"]
        wr    = gd["white"]["rating"]
        br    = gd["black"]["rating"]
        dt    = datetime.fromtimestamp(gd.get("end_time", 0)).strftime("%Y-%m-%d")
        print(f"[{i+1:03d}/{len(games)}] {white} ({wr}) vs {black} ({br}) | {dt}")

        land_path, port_path, game_dir = get_output_paths(gd, i+1)

        if os.path.exists(land_path) and os.path.exists(port_path):
            print(f"  ⏭️  Already exists, skipping.")
            success += 1
            continue

        if generate_videos(gd, all_pieces, land_path, port_path, game_dir):
            success += 1

    print(f"\n🏁 Done! {success}/{len(games)} games processed.")
    print(f"📂 Videos saved in: {os.path.abspath(OUTPUT_DIR)}/")

if __name__ == "__main__":
    main()
