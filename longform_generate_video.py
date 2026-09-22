"""
longform_generate_video.py — Monthly Compilation Video Generator
The Thinking Athlete Pipeline — Long-Form Content

Generates a single landscape (1280×720) video containing ALL wins for a month:
  - Intro card  (3 s)
  - Per game: transition card + full game replay with move annotations
  - Outro card  (5 s)
  - Optional background music mixed with move sounds
  - YouTube chapter timestamps saved to _chapters.txt

Move annotations (via Stockfish if available):
  Blunder (??)  · Mistake (?)  · Inaccuracy (?!)  · Brilliant (!!)  · Great (!)

Usage:
    YEAR=2026 MONTH=1 python longform_generate_video.py
    python longform_generate_video.py --year 2026 --month 1

Requirements:
    pip install chess imageio imageio-ffmpeg pillow numpy requests
    apt-get install ffmpeg stockfish        (stockfish optional — skips annotations)
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
import shutil
import subprocess
import random
import argparse
from datetime import datetime
import math
from PIL import Image, ImageDraw, ImageFont

# ── Config ────────────────────────────────────────────────────────────────────

USERNAME   = "abhi15041984"
FPS        = 1
OUTPUT_DIR = "longform"
PIECES_DIR = "pieces"
SOUNDS_DIR = "sounds"
BASE_URL   = ("https://raw.githubusercontent.com/oakmac/"
              "chessboardjs/master/website/img/chesspieces/wikipedia")

INTRO_FRAMES      = 3
TRANSITION_FRAMES = 5    # animated: announce → vs → full card × 3
OPENING_HOLD      = 2
CONFETTI_FRAMES   = 4
OUTRO_FRAMES      = 5

STOCKFISH_THINK   = float(os.environ.get("SF_THINK", "0.05"))   # seconds per position
MATE_SCORE        = 10_000

# ── Colors ────────────────────────────────────────────────────────────────────

AMBER      = (239, 159,  39)
WHITE_C    = (255, 255, 255)
DARK_C     = ( 13,  13,  15)
PANEL_C    = ( 22,  22,  24)
GRAY_C     = (136, 136, 136)
GRAY_DK    = ( 42,  42,  46)
LIGHT_SQ   = (240, 217, 181)
DARK_SQ    = (181, 136,  99)
HL_LIGHT   = (205, 210, 106)
HL_DARK    = (170, 162,  58)
CHECK_CLR  = (220,  50,  50)

CONFETTI_COLORS = [
    (255, 215, 0), (255, 69, 0), (50, 205, 50),
    (30, 144, 255), (238, 130, 238), (255, 165, 0),
    (0, 255, 200), (239, 159, 39), (255, 20, 147),
]

PIECE_NAMES = {
    chess.PAWN:"P", chess.ROOK:"R", chess.KNIGHT:"N",
    chess.BISHOP:"B", chess.QUEEN:"Q", chess.KING:"K",
}

MONTH_NAMES = {
    1:"01_January", 2:"02_February", 3:"03_March", 4:"04_April",
    5:"05_May",     6:"06_June",     7:"07_July",  8:"08_August",
    9:"09_September",10:"10_October",11:"11_November",12:"12_December",
}

# ── Annotation config ─────────────────────────────────────────────────────────

ANN_COLOR = {
    "Brilliant":  ( 40, 210, 210),   # cyan
    "Great":      ( 60, 210, 100),   # bright green
    "Best":       ( 80, 170,  80),   # medium green
    "Good":       (100, 160, 220),   # soft blue
    "Inaccuracy": (230, 190,  30),   # yellow
    "Mistake":    (255, 130,  30),   # orange
    "Blunder":    (220,  60,  60),   # red
}
ANN_SYMBOL = {
    "Brilliant": "!!", "Great": "!", "Best": "✓", "Good": "⊙",
    "Inaccuracy": "?!", "Mistake": "?", "Blunder": "??",
}

# ── Fonts ─────────────────────────────────────────────────────────────────────

def get_font(size, bold=False):
    for p in ["/System/Library/Fonts/Helvetica.ttc",
              "/Library/Fonts/Arial.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
              else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def make_fonts():
    return {
        "xl":      get_font(30, bold=True),
        "lg":      get_font(22, bold=True),
        "md":      get_font(18),
        "sm":      get_font(13),
        "sm_bold": get_font(13, bold=True),
        "xs":      get_font(10),
    }

# ── Pieces ────────────────────────────────────────────────────────────────────

def download_pieces():
    os.makedirs(PIECES_DIR, exist_ok=True)
    for c in ["w", "b"]:
        for p in ["P","R","N","B","Q","K"]:
            fn = f"{c}{p}.png"
            fp = os.path.join(PIECES_DIR, fn)
            if not os.path.exists(fp):
                r = requests.get(f"{BASE_URL}/{fn}", timeout=10)
                if r.status_code == 200:
                    open(fp, "wb").write(r.content)
                else:
                    print(f"  ❌ Could not download piece {fn}"); sys.exit(1)


def load_pieces(sq_size):
    pieces = {}
    for color in [chess.WHITE, chess.BLACK]:
        cc = "w" if color == chess.WHITE else "b"
        for pt, pc in PIECE_NAMES.items():
            img = Image.open(os.path.join(PIECES_DIR, f"{cc}{pc}.png")).convert("RGBA")
            pieces[(color, pt)] = img.resize((sq_size, sq_size), Image.LANCZOS)
    return pieces

# ── Clock helpers ─────────────────────────────────────────────────────────────

def parse_clocks(game):
    clocks = []
    node = game
    while node.variations:
        node = node.variations[0]
        clk = None
        if "[%clk" in (node.comment or ""):
            try:
                clk = node.comment.split("[%clk")[1].split("]")[0].strip()
            except Exception:
                pass
        clocks.append(clk)
    return clocks


def fmt_clk(s):
    if not s:
        return "--:--"
    try:
        parts = s.split(":")
        if len(parts) == 3:
            h, m, sec = int(parts[0]), int(parts[1]), int(float(parts[2]))
            return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"
    except Exception:
        pass
    return "--:--"


def get_clocks_at_move(clocks, move_idx):
    w = b = None
    for i in range(min(move_idx, len(clocks))):
        if i % 2 == 0:
            w = clocks[i]
        else:
            b = clocks[i]
    return fmt_clk(w), fmt_clk(b)

# ── Game meta ─────────────────────────────────────────────────────────────────

def fmt_time_control(tc):
    if not tc or tc == "-":
        return ""
    try:
        base = int(tc.split("+")[0])
        inc  = int(tc.split("+")[1]) if "+" in tc else 0
        mins = base // 60
        inc_s = f" +{inc}" if inc else ""
        label = "Rapid" if mins >= 10 else "Blitz" if mins >= 3 else "Bullet"
        return f"{mins} min{inc_s} {label}"
    except Exception:
        return tc


def parse_game_meta(game):
    h = game.headers
    opening = h.get("Opening", "").strip()
    if not opening:
        eco_url = h.get("ECOUrl", "")
        if "/openings/" in eco_url:
            import re
            slug  = eco_url.rstrip("/").split("/")[-1]
            words = []
            for w in slug.split("-"):
                if re.match(r"^\d", w):
                    break
                words.append(w)
            opening = " ".join(words)
    return {
        "opening":     opening,
        "eco":         h.get("ECO", ""),
        "time_ctrl":   fmt_time_control(h.get("TimeControl", "")),
        "termination": h.get("Termination", ""),
    }

# ── Board drawing ─────────────────────────────────────────────────────────────

def draw_board(board, pieces, last_move=None, sq_size=80, flip=False):
    bpx = sq_size * 8
    img = Image.new("RGBA", (bpx, bpx), DARK_C)
    draw = ImageDraw.Draw(img)
    cf  = get_font(max(9, sq_size // 7))
    lsq = {last_move.from_square, last_move.to_square} if last_move else set()

    check_sq = None
    if board.is_check():
        k = board.king(board.turn)
        if k is not None:
            check_sq = k

    for rank in range(7, -1, -1):
        for file in range(8):
            sq  = chess.square(file, rank)
            if flip:
                x = (7 - file) * sq_size
                y = rank * sq_size
            else:
                x = file * sq_size
                y = (7 - rank) * sq_size
            isl = (file + rank) % 2 == 1

            if sq == check_sq:     col = CHECK_CLR
            elif sq in lsq:        col = HL_LIGHT if isl else HL_DARK
            else:                  col = LIGHT_SQ if isl else DARK_SQ
            draw.rectangle([x, y, x+sq_size, y+sq_size], fill=col)

            if sq == check_sq:
                b = 3
                draw.rectangle([x+b, y+b, x+sq_size-b, y+sq_size-b],
                                outline=(255, 80, 80), width=b)

            cc = DARK_SQ if isl else LIGHT_SQ
            if (file == 0 and not flip) or (file == 7 and flip):
                draw.text((x+3, y+2), str(rank+1), fill=cc, font=cf)
            if (rank == 0 and not flip) or (rank == 7 and flip):
                draw.text((x+sq_size-11, y+sq_size-15),
                          "abcdefgh"[file], fill=cc, font=cf)

            piece = board.piece_at(sq)
            if piece:
                pi = pieces.get((piece.color, piece.piece_type))
                if pi:
                    pw2, ph2 = pi.size
                    img.paste(pi, (x + (sq_size - pw2)//2,
                                   y + (sq_size - ph2)//2), pi)

    return img.convert("RGB")


def _badge_star(draw, cx, cy, r, fill):
    """Filled 5-point star centered at (cx, cy), outer radius r."""
    pts = []
    for i in range(10):
        angle = math.radians(i * 36 - 90)
        ri    = r if i % 2 == 0 else r * 0.42
        pts.append((cx + ri * math.cos(angle), cy + ri * math.sin(angle)))
    draw.polygon(pts, fill=fill)


def _badge_tick(draw, cx, cy, r, fill, lw):
    """Tick / checkmark ✓ centered at (cx, cy)."""
    p1 = (cx - r * 0.52, cy + r * 0.05)
    p2 = (cx - r * 0.05, cy + r * 0.50)
    p3 = (cx + r * 0.52, cy - r * 0.42)
    draw.line([p1, p2], fill=fill, width=lw)
    draw.line([p2, p3], fill=fill, width=lw)


def draw_annotation_badge(board_img, move, sq_size, tag, flip=False):
    """Overlay a colored icon badge at the destination square for notable moves.

    Good      → green circle + white tick ✓
    Best      → green circle + white star ★
    Great     → green circle + white !
    Brilliant → cyan circle  + white !!
    Inaccuracy→ yellow circle + dark ?!
    Mistake   → orange circle + white ?
    Blunder   → red circle    + white ??
    """
    if tag not in ANN_COLOR:
        return
    color = ANN_COLOR[tag]
    sq    = move.to_square
    file  = chess.square_file(sq)
    rank  = chess.square_rank(sq)

    if flip:
        bx = (7 - file) * sq_size
        by = rank * sq_size
    else:
        bx = file * sq_size
        by = (7 - rank) * sq_size

    r  = max(14, sq_size // 4)   # badge radius ~25% of square
    cx = bx + sq_size - r - 2
    cy = by + r + 2

    draw = ImageDraw.Draw(board_img)
    # Shadow outline then colored circle
    draw.ellipse([cx-r-2, cy-r-2, cx+r+2, cy+r+2], fill=(0, 0, 0))
    draw.ellipse([cx-r,   cy-r,   cx+r,   cy+r],   fill=color)

    lw    = max(2, r // 5)
    WHITE = (255, 255, 255)
    DARK  = (20,  20,  20)

    if tag == "Best":
        _badge_star(draw, cx, cy, r * 0.62, WHITE)
    elif tag == "Good":
        _badge_tick(draw, cx, cy, r, WHITE, lw)
    else:
        sym = ANN_SYMBOL.get(tag, "")
        if sym:
            txt_col = DARK if tag == "Inaccuracy" else WHITE
            fsize   = max(10, int(r * 0.85))
            f       = get_font(fsize, bold=True)
            draw.text((cx, cy), sym, fill=txt_col, font=f, anchor="mm")

# ── Confetti ──────────────────────────────────────────────────────────────────

def make_confetti_particles(W, H, count=200, seed=0):
    rng = random.Random(seed)
    return [{
        "x":     rng.randint(0, W),
        "y":     rng.randint(-H, H),
        "vx":    rng.uniform(-2, 2),
        "vy":    rng.uniform(8, 20),
        "w":     rng.randint(8, 20),
        "h":     rng.randint(4, 10),
        "color": rng.choice(CONFETTI_COLORS),
        "shape": rng.choice(["rect", "ellipse"]),
    } for _ in range(count)]


def draw_confetti(draw, particles, W, H, frame_idx):
    for p in particles:
        x = int(p["x"] + p["vx"] * frame_idx * 8) % W
        y = int(p["y"] + p["vy"] * frame_idx * 8) % H
        if p["shape"] == "rect":
            draw.rectangle([x, y, x+p["w"], y+p["h"]], fill=p["color"])
        else:
            draw.ellipse([x, y, x+p["w"], y+p["h"]], fill=p["color"])

# ── Move list (with annotation symbols) ──────────────────────────────────────

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


def draw_move_list(draw, pairs, cur_idx, px, py, pw, max_h, fonts,
                   annotations_by_ply=None):
    rh   = int(22 * (pw / 540))
    vis  = max(1, max_h // rh)
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
            draw.rectangle([px-4, y-2, px+pw, y+rh-4], fill=(35, 35, 25))

        draw.text((px, y), f"{mn}.", fill=GRAY_C, font=fonts["xs"])

        # White's move
        wc = AMBER if (iscur and iswh) else WHITE_C
        wf = fonts["sm_bold"] if (iscur and iswh) else fonts["sm"]
        draw.text((px+cnw, y), ws, fill=wc, font=wf)

        # Black's move
        if bs:
            bc = AMBER if (iscur and not iswh) else (200, 200, 200)
            bf = fonts["sm_bold"] if (iscur and not iswh) else fonts["sm"]
            draw.text((px+cnw+cww, y), bs, fill=bc, font=bf)

# ── Frame builders ────────────────────────────────────────────────────────────

def make_intro_frame(year, month, total_games):
    W, H = 1280, 720
    img  = Image.new("RGB", (W, H), DARK_C)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, W, 5], fill=AMBER)
    draw.rectangle([0, H-5, W, H], fill=AMBER)

    month_str = datetime(year, month, 1).strftime("%B %Y")

    draw.text((W//2, 175), "The Thinking Athlete",
              fill=AMBER, font=get_font(56, bold=True), anchor="mm")
    draw.text((W//2, 270), month_str,
              fill=WHITE_C, font=get_font(46), anchor="mm")
    draw.text((W//2, 340), f"ALL WINS  ·  {total_games} GAMES",
              fill=GRAY_C, font=get_font(30), anchor="mm")
    draw.rectangle([W//2-280, 378, W//2+280, 381], fill=AMBER)
    draw.text((W//2, 415), "chess.com  /  abhi15041984",
              fill=(75, 75, 80), font=get_font(22), anchor="mm")
    draw.text((W//2, H-30), "@indianthinkingathlete",
              fill=(55, 55, 60), font=get_font(18), anchor="mm")
    return img


def make_transition_frame(game_num, total_games, opp_name, opp_rating,
                           date_str, time_ctrl, opening, my_rating, side,
                           win_method, move_count, frame_idx=0):
    """
    5-frame animated transition:
      0 — Announcement (dark, large game number only)
      1 — VS screen (split: game# left, opponent right)
      2 — Full info card
      3 — Full info card (hold)
      4 — Full info card (slight dim-out into the game)
    """
    W, H = 1280, 720

    # ── Frame 0: pure announcement ───────────────────────────────────────────
    if frame_idx == 0:
        img  = Image.new("RGB", (W, H), (6, 6, 10))
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, W, 5], fill=AMBER)
        draw.rectangle([0, H-5, W, H], fill=AMBER)
        draw.text((W//2, H//2 - 55), "GAME",
                  fill=(70, 70, 78), font=get_font(52, bold=True), anchor="mm")
        draw.text((W//2, H//2 + 55), str(game_num),
                  fill=AMBER, font=get_font(160, bold=True), anchor="mm")
        draw.text((W-55, H-22), f"{game_num} / {total_games}",
                  fill=(55, 55, 62), font=get_font(16), anchor="rm")
        return img

    # ── Frame 1: VS split screen ──────────────────────────────────────────────
    if frame_idx == 1:
        img  = Image.new("RGB", (W, H), (10, 10, 16))
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, W, 5], fill=AMBER)
        draw.rectangle([0, H-5, W, H], fill=AMBER)
        # Left panel: game number
        draw.rectangle([0, 0, W//2 - 1, H], fill=(14, 14, 20))
        draw.rectangle([W//2 - 1, 60, W//2 + 1, H-60], fill=(45, 45, 50))
        draw.text((W//4, H//2 - 30), "GAME",
                  fill=(80, 80, 90), font=get_font(38, bold=True), anchor="mm")
        draw.text((W//4, H//2 + 40), str(game_num),
                  fill=AMBER, font=get_font(110, bold=True), anchor="mm")
        side_str  = "White" if side == "white" else "Black"
        side_col  = WHITE_C if side == "white" else (160, 160, 160)
        draw.text((W//4, H//2 + 105), f"Playing as {side_str}",
                  fill=side_col, font=get_font(20), anchor="mm")
        # Right panel: opponent
        opp_display = opp_name if len(opp_name) <= 18 else opp_name[:16] + "…"
        draw.text((3*W//4, H//2 - 60), "vs.",
                  fill=(90, 90, 100), font=get_font(30), anchor="mm")
        draw.text((3*W//4, H//2 + 10), opp_display,
                  fill=WHITE_C, font=get_font(54, bold=True), anchor="mm")
        draw.text((3*W//4, H//2 + 68), f"Rating  {opp_rating}",
                  fill=GRAY_C, font=get_font(28), anchor="mm")
        # Rating comparison bar
        bar_y = H//2 + 108
        bar_w = 260
        draw.rounded_rectangle([3*W//4 - bar_w//2, bar_y,
                                 3*W//4 + bar_w//2, bar_y + 10],
                                radius=5, fill=(40, 40, 46))
        my_frac = min(1.0, my_rating / max(opp_rating, 1))
        draw.rounded_rectangle([3*W//4 - bar_w//2, bar_y,
                                 int(3*W//4 - bar_w//2 + bar_w * my_frac), bar_y + 10],
                                radius=5, fill=AMBER)
        draw.text((3*W//4, bar_y + 22), f"My rating: {my_rating}",
                  fill=(110, 110, 120), font=get_font(16), anchor="mm")
        draw.text((W-55, H-22), f"{game_num} / {total_games}",
                  fill=(55, 55, 62), font=get_font(16), anchor="rm")
        draw.text((55, H-22), "The Thinking Athlete", fill=AMBER, font=get_font(16))
        return img

    # ── Frames 2-4: full info card ────────────────────────────────────────────
    img  = Image.new("RGB", (W, H), DARK_C)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, W, 6], fill=AMBER)
    draw.rectangle([0, H-6, W, H], fill=AMBER)
    draw.rectangle([0, 6, 5, H-6], fill=AMBER)
    draw.rectangle([W-5, 6, W, H-6], fill=AMBER)

    draw.text((W//2, 120), f"GAME  {game_num}",
              fill=AMBER, font=get_font(72, bold=True), anchor="mm")
    draw.rectangle([W//2 - 210, 160, W//2 + 210, 163], fill=AMBER)

    draw.text((W//2, 198), "vs.", fill=GRAY_C, font=get_font(26), anchor="mm")
    opp_display = opp_name if len(opp_name) <= 22 else opp_name[:20] + "…"
    draw.text((W//2, 258), opp_display,
              fill=WHITE_C, font=get_font(50, bold=True), anchor="mm")
    draw.text((W//2, 308), f"Rating: {opp_rating}",
              fill=GRAY_C, font=get_font(30), anchor="mm")

    draw.rectangle([40, 356, W-40, 358], fill=(50, 50, 55))
    parts = [date_str]
    if time_ctrl:
        parts.append(time_ctrl)
    if opening:
        short = opening[:34] + "…" if len(opening) > 37 else opening
        parts.append(short)
    draw.text((W//2, 376), "  |  ".join(parts),
              fill=GRAY_C, font=get_font(20), anchor="mm")

    side_str = "White" if side == "white" else "Black"
    draw.text((W//2, 412),
              f"Playing as {side_str}  ·  Won by {win_method} in {move_count} moves",
              fill=(110, 110, 118), font=get_font(18), anchor="mm")

    # Annotation legend strip
    leg_y = 456
    draw.rectangle([80, leg_y, W-80, leg_y+1], fill=(40, 40, 46))
    legend_tags = ["Brilliant", "Great", "Best", "Good", "Inaccuracy", "Mistake", "Blunder"]
    legend_labels = ["Brilliant", "Great", "Best", "Good", "Inaccuracy", "Mistake", "Blunder"]
    lx = 85
    step = (W - 170) // len(legend_tags)
    lby = leg_y + 18
    r_leg = 11
    WHITE = (255, 255, 255)
    DARK  = (20, 20, 20)
    for ltag, llabel in zip(legend_tags, legend_labels):
        col = ANN_COLOR[ltag]
        draw.ellipse([lx-r_leg-1, lby-r_leg-1, lx+r_leg+1, lby+r_leg+1], fill=(0,0,0))
        draw.ellipse([lx-r_leg,   lby-r_leg,   lx+r_leg,   lby+r_leg],   fill=col)
        lw_leg = max(2, r_leg // 5)
        if ltag == "Best":
            _badge_star(draw, lx, lby, r_leg * 0.62, WHITE)
        elif ltag == "Good":
            _badge_tick(draw, lx, lby, r_leg, WHITE, lw_leg)
        else:
            sym = ANN_SYMBOL[ltag]
            tc  = DARK if ltag == "Inaccuracy" else WHITE
            draw.text((lx, lby), sym, fill=tc,
                      font=get_font(max(7, r_leg - 2), bold=True), anchor="mm")
        draw.text((lx, lby + r_leg + 8), llabel,
                  fill=(90, 90, 98), font=get_font(11), anchor="mm")
        lx += step

    draw.text((W-55, H-22), f"{game_num} / {total_games}",
              fill=(60, 60, 65), font=get_font(16), anchor="rm")
    draw.text((55, H-22), "The Thinking Athlete", fill=AMBER, font=get_font(16))

    # Frame 4: slight dim into the game
    if frame_idx == 4:
        overlay = Image.new("RGB", (W, H), (0, 0, 0))
        img = Image.blend(img, overlay, 0.25)

    return img


def make_outro_frame(year, month, total_games):
    W, H = 1280, 720
    img  = Image.new("RGB", (W, H), DARK_C)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, W, 5], fill=AMBER)
    draw.rectangle([0, H-5, W, H], fill=AMBER)

    month_str = datetime(year, month, 1).strftime("%B %Y")
    draw.text((W//2, 175), f"{total_games} WINS",
              fill=AMBER, font=get_font(72, bold=True), anchor="mm")
    draw.text((W//2, 258), f"in {month_str}",
              fill=WHITE_C, font=get_font(44), anchor="mm")
    draw.rectangle([W//2-240, 296, W//2+240, 299], fill=AMBER)

    btn_y = 330
    draw.rounded_rectangle([W//2-180, btn_y, W//2+180, btn_y+64],
                            radius=8, fill=AMBER)
    draw.text((W//2, btn_y+32), "SUBSCRIBE",
              fill=DARK_C, font=get_font(36, bold=True), anchor="mm")
    draw.text((W//2, btn_y+82), "Hit the bell  ·  Never miss a game",
              fill=GRAY_C, font=get_font(22), anchor="mm")
    draw.text((W//2, H-30), "@indianthinkingathlete",
              fill=(55, 55, 60), font=get_font(18), anchor="mm")
    return img


def make_game_frame(board, pieces, move_pairs, cur_idx,
                    move=None, move_num=0, total=0, flip=False,
                    top_name="", top_rating=0, top_clk="--:--",
                    bot_name="", bot_rating=0, bot_clk="--:--",
                    meta=None, confetti_particles=None, confetti_fidx=0,
                    winner_text="", annotation_tag=None,
                    annotations_by_ply=None):
    W, H = 1280, 720
    img  = Image.new("RGB", (W, H), DARK_C)
    draw = ImageDraw.Draw(img)
    F    = make_fonts()

    draw.rectangle([0, 0, W, 4], fill=AMBER)
    draw.rectangle([0, H-4, W, H], fill=AMBER)

    sq = 680 // 8
    bi = draw_board(board, pieces, move, sq_size=sq, flip=flip)
    if annotation_tag and move:
        draw_annotation_badge(bi, move, sq, annotation_tag, flip=flip)
    board_y = (H - sq * 8) // 2
    img.paste(bi, (20, board_y))

    px, pw = 720, W - 720 - 20

    draw.text((px, 22), "The Thinking Athlete", fill=AMBER, font=F["lg"])
    draw.line([px, 52, W-20, 52], fill=AMBER, width=1)

    draw.text((px, 62),  "OPPONENT",   fill=GRAY_C,  font=F["xs"])
    draw.text((px, 76),  top_name,     fill=WHITE_C,  font=F["md"])
    draw.text((px, 97),  f"Rating: {top_rating}", fill=GRAY_C, font=F["sm"])
    draw.text((px+pw-60, 76), top_clk, fill=AMBER,   font=F["md"])
    draw.line([px, 118, W-20, 118], fill=GRAY_DK, width=1)

    draw.text((px, 126), "YOU ♟",     fill=AMBER,   font=F["xs"])
    draw.text((px, 140), bot_name,     fill=WHITE_C,  font=F["md"])
    draw.text((px, 161), f"Rating: {bot_rating}", fill=GRAY_C, font=F["sm"])
    draw.text((px+pw-60, 140), bot_clk, fill=AMBER,  font=F["md"])
    draw.line([px, 182, W-20, 182], fill=GRAY_DK, width=1)

    if meta:
        if meta.get("opening"):
            op = meta["opening"]
            eco = f"[{meta['eco']}] " if meta.get("eco") else ""
            if len(op) > 28:
                op = op[:26] + "…"
            draw.text((px, 190), f"{eco}{op}", fill=AMBER, font=F["sm"])
        if meta.get("time_ctrl"):
            draw.text((px, 206), meta["time_ctrl"], fill=GRAY_C, font=F["xs"])
        draw.line([px, 220, W-20, 220], fill=GRAY_DK, width=1)
        move_y = 228
    else:
        move_y = 190

    draw.text((px, move_y),     "MOVE",                        fill=GRAY_C, font=F["xs"])
    draw.text((px, move_y+16),  f"{move_num}  /  {total}",     fill=AMBER,  font=F["xl"])

    by2 = move_y + 48
    draw.rounded_rectangle([px, by2, px+pw, by2+8], radius=4, fill=GRAY_DK)
    if total > 0 and move_num > 0:
        draw.rounded_rectangle([px, by2, px+int(pw*move_num/total), by2+8],
                                radius=4, fill=AMBER)

    # Compact turn / check indicator drawn INSIDE the progress-bar row (right side)
    if board.is_check():
        draw.text((px + pw, by2 + 4), "⚠ CHECK!", fill=CHECK_CLR,
                  font=F["xs"], anchor="rm")
    else:
        tc   = (230, 230, 230) if board.turn == chess.WHITE else (150, 150, 150)
        turn = "● White" if board.turn == chess.WHITE else "● Black"
        draw.text((px + pw, by2 + 4), turn, fill=tc, font=F["xs"], anchor="rm")

    move_list_y = by2 + 22
    draw_move_list(draw, move_pairs, cur_idx, px, move_list_y, pw,
                   H - move_list_y - 20, F, annotations_by_ply=annotations_by_ply)

    draw.text((px, H-14), "@TheThinkingAthlete", fill=(55, 55, 60), font=F["xs"])

    if confetti_particles:
        draw_confetti(draw, confetti_particles, W, H, confetti_fidx)
        # Winner banner
        cy2 = H // 2
        draw.rectangle([0, cy2-70, W, cy2+70], fill=(0, 0, 0))
        draw.rectangle([0, cy2-70, W, cy2-66], fill=AMBER)
        draw.rectangle([0, cy2+66, W, cy2+70], fill=AMBER)
        draw.text((W//2, cy2-28), "GAME OVER", fill=GRAY_C,
                  font=F["md"], anchor="mm")
        draw.text((W//2, cy2+10), winner_text,  fill=AMBER,
                  font=F["xl"], anchor="mm")

    return img

# ── Stockfish analysis ────────────────────────────────────────────────────────

def analyze_with_stockfish(pgn_text, think_time=STOCKFISH_THINK):
    """
    Returns dict mapping 1-indexed ply → tag string.
    Returns {} if Stockfish is not available or analysis fails.
    Tags: Brilliant / Great / Best / Good / Inaccuracy / Mistake / Blunder
    """
    sf = shutil.which("stockfish")
    if not sf:
        return {}

    try:
        import chess.engine
        engine = chess.engine.SimpleEngine.popen_uci(sf)
    except Exception:
        return {}

    result = {}
    try:
        game  = chess.pgn.read_game(io.StringIO(pgn_text))
        if not game:
            return {}
        white    = game.headers.get("White", "")
        my_color = chess.WHITE if white.lower() == USERNAME.lower() else chess.BLACK
        board    = game.board()
        moves    = list(game.mainline_moves())
        limit    = chess.engine.Limit(time=think_time)

        for ply, move in enumerate(moves):
            mover = board.turn

            info_before = engine.analyse(board, limit)
            pv          = info_before.get("pv") or []
            best_move   = pv[0] if pv else None
            cp_before   = info_before["score"].pov(mover).score(mate_score=MATE_SCORE)

            board.push(move)

            if board.is_game_over():
                cp_after = MATE_SCORE if board.is_checkmate() else 0
            else:
                info_after = engine.analyse(board, limit)
                cp_after   = info_after["score"].pov(mover).score(mate_score=MATE_SCORE)

            # Clamp extremes so a missed checkmate 1 doesn't look like a -9000 blunder
            clamp     = lambda v: max(-MATE_SCORE // 2, min(MATE_SCORE // 2, v))
            delta     = clamp(cp_after) - clamp(cp_before)
            cp_loss   = max(0, -delta)

            if move == best_move:
                # Brilliant: best move that rescues a losing/equal position
                if cp_before is not None and cp_before < 100 and delta >= 200:
                    tag = "Brilliant"
                # Great: best move with significant positional improvement
                elif delta >= 50:
                    tag = "Great"
                else:
                    tag = "Best"
            elif cp_loss <= 30:
                tag = "Good"
            elif cp_loss <= 100:
                tag = "Inaccuracy"
            elif cp_loss <= 300:
                tag = "Mistake"
            else:
                tag = "Blunder"

            result[ply + 1] = tag   # 1-indexed

    except Exception as e:
        print(f"    ⚠️  Stockfish analysis error: {e}")
    finally:
        try:
            engine.quit()
        except Exception:
            pass

    return result

# ── Sound ─────────────────────────────────────────────────────────────────────

def classify_move(board, move):
    if board.is_castling(move):
        return "castle"
    if move.promotion:
        return "promote"
    if board.is_capture(move):
        return "capture"
    return "move"


def get_sound_paths():
    sounds = {
        "move":    os.path.join(SOUNDS_DIR, "move1.mp3"),
        "capture": os.path.join(SOUNDS_DIR, "capture.mp3"),
        "castle":  os.path.join(SOUNDS_DIR, "castle.mp3"),
        "promote": os.path.join(SOUNDS_DIR, "promote.mp3"),
    }
    for k, p in sounds.items():
        if not os.path.exists(p):
            print(f"  ❌ Missing sound file: {p}")
            sys.exit(1)
    return sounds


def find_bg_music():
    """Return path to background music or None."""
    candidates = [
        os.path.join(SOUNDS_DIR, "longform_bg.mp3"),
        os.path.join(SOUNDS_DIR, "track.mp3"),
    ]
    for p in candidates:
        if os.path.exists(p) and os.path.getsize(p) > 10_000:
            return p
    return None


def build_compilation_audio(sound_events, total_duration_sec, out_path):
    """
    sound_events: list of (frame_offset, sound_type)
    Builds a mixed audio track at the correct timestamps.

    Large compilations (100s of games) can produce 10,000+ sound events.
    Passing all of them as -i arguments to a single ffmpeg call exceeds the OS
    ARG_MAX limit (~262k bytes on macOS/Linux). We batch events into groups of
    BATCH_SIZE, write one intermediate AAC per batch, then mix all batches.
    """
    if not sound_events:
        return None

    BATCH_SIZE = 150
    sounds     = get_sound_paths()
    tmp_dir    = os.path.join(os.path.dirname(out_path) or "sounds", "_audio_batches")
    os.makedirs(tmp_dir, exist_ok=True)
    batch_files = []

    batches = [sound_events[i:i + BATCH_SIZE]
               for i in range(0, len(sound_events), BATCH_SIZE)]

    print(f"  🔊 Building audio: {len(sound_events)} events → {len(batches)} batches")

    # Use PCM WAV for all intermediate files — zero codec delay,
    # so sounds land at their exact frame boundaries.
    # AAC encode happens exactly once, in mux_with_audio.
    for b_idx, batch in enumerate(batches):
        tmp_path = os.path.join(tmp_dir, f"batch_{b_idx:04d}.wav")
        inputs, filters = [], []

        for j, (offset_frame, mtype) in enumerate(batch):
            path      = sounds[mtype]
            offset_ms = int(offset_frame * 1000 / FPS)
            inputs   += ["-i", path]
            filters.append(f"[{j}]adelay={offset_ms}|{offset_ms}[a{j}]")

        n   = len(batch)
        mix = "".join(f"[a{k}]" for k in range(n))
        filters.append(f"{mix}amix=inputs={n}:normalize=0:duration=longest[bout]")

        cmd = (["ffmpeg", "-y"] + inputs +
               ["-filter_complex", ";".join(filters),
                "-map", "[bout]",
                "-t", str(total_duration_sec),
                "-c:a", "pcm_s16le", tmp_path])
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode != 0:
            print(f"  ⚠️  Batch {b_idx} failed: {r.stderr.decode()[-200:]}")
            continue
        batch_files.append(tmp_path)

    if not batch_files:
        return None

    # out_path must be a .wav so the caller (mux_with_audio) does the single AAC encode
    if not out_path.endswith(".wav"):
        out_path = os.path.splitext(out_path)[0] + ".wav"

    if len(batch_files) == 1:
        shutil.move(batch_files[0], out_path)
    else:
        # Mix all batch WAV files — still lossless, zero extra delay
        inputs2, filters2 = [], []
        for k, bf in enumerate(batch_files):
            inputs2 += ["-i", bf]
            filters2.append(f"[{k}:a]anull[b{k}]")
        mix2 = "".join(f"[b{k}]" for k in range(len(batch_files)))
        filters2.append(
            f"{mix2}amix=inputs={len(batch_files)}:normalize=0:duration=longest[out]"
        )
        cmd2 = (["ffmpeg", "-y"] + inputs2 +
                ["-filter_complex", ";".join(filters2),
                 "-map", "[out]",
                 "-t", str(total_duration_sec),
                 "-c:a", "pcm_s16le", out_path])
        r2 = subprocess.run(cmd2, capture_output=True)
        if r2.returncode != 0:
            print(f"  ⚠️  Final audio mix failed: {r2.stderr.decode()[-300:]}")
            return None

    # Clean up temp batch files
    shutil.rmtree(tmp_dir, ignore_errors=True)

    return out_path


def mux_with_audio(video_path, audio_path, bg_music_path, output_path):
    """Mux video + move sounds (+ optional background music)."""
    if bg_music_path:
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", audio_path,
            "-i", bg_music_path,
            "-filter_complex",
            "[2:a]aloop=loop=-1:size=2147483647,volume=0.12[bgm];"
            "[1:a][bgm]amix=inputs=2:duration=first:normalize=0[aout]",
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-shortest",
            output_path,
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path, "-i", audio_path,
            "-filter_complex", "[1:a]apad[aout]",
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac", "-shortest",
            output_path,
        ]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        print(f"  ⚠️  Mux failed: {r.stderr.decode()[-200:]}")
        return False
    return True

# ── Video writer helper ───────────────────────────────────────────────────────

def open_writer(path):
    return imageio.get_writer(
        path, fps=FPS, codec="libx264",
        output_params=["-crf", "23", "-pix_fmt", "yuv420p"]
    )

# ── Chapter helpers ───────────────────────────────────────────────────────────

def fmt_timestamp(total_seconds):
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def save_chapters(chapters, path):
    with open(path, "w") as f:
        for sec, label in chapters:
            f.write(f"{fmt_timestamp(sec)} {label}\n")
    print(f"  📌 Chapters saved: {path}")

# ── Main compilation ──────────────────────────────────────────────────────────

def generate_compilation(games, year, month, run_stockfish=True):
    month_str  = datetime(year, month, 1).strftime("%B_%Y")
    out_dir    = os.path.join(OUTPUT_DIR, str(year), MONTH_NAMES[month])
    os.makedirs(out_dir, exist_ok=True)

    silent_path = os.path.join(out_dir, "compilation_silent.mp4")
    audio_path  = os.path.join(SOUNDS_DIR, "longform_track.wav")
    final_path  = os.path.join(out_dir, "compilation.mp4")
    chapters_path = os.path.join(out_dir, "chapters.txt")

    month_label = datetime(year, month, 1).strftime("%B %Y")
    print(f"\n🎬 Generating: {month_label}  ({len(games)} games)")

    download_pieces()
    land_pieces = load_pieces(680 // 8)

    # ── Optional Stockfish analysis ───────────────────────────────────────────
    game_annotations = {}
    if run_stockfish and shutil.which("stockfish"):
        print(f"\n🔬 Stockfish analysis ({STOCKFISH_THINK}s/position)...")
        for i, gd in enumerate(games):
            pgn_text = gd.get("pgn", "")
            if not pgn_text:
                continue
            sys.stdout.write(f"  [{i+1:02d}/{len(games)}] ... ")
            sys.stdout.flush()
            ann = analyze_with_stockfish(pgn_text)
            game_annotations[i] = ann
            blunders = sum(1 for t in ann.values() if t == "Blunder")
            print(f"{len(ann)} moves  ({blunders} blunders)")
    elif run_stockfish:
        print("  ⚠️  Stockfish not found — generating without move annotations")

    # ── Pre-parse metadata ────────────────────────────────────────────────────
    parsed = []
    for gd in games:
        pgn_text = gd.get("pgn", "")
        meta, game_obj, moves = {}, None, []
        if pgn_text:
            game_obj = chess.pgn.read_game(io.StringIO(pgn_text))
            if game_obj:
                meta  = parse_game_meta(game_obj)
                moves = list(game_obj.mainline_moves())

        side     = "white" if gd["white"]["username"].lower() == USERNAME.lower() else "black"
        opp_side = "black" if side == "white" else "white"
        opp_res  = gd[opp_side]["result"]
        win_map  = {"checkmated": "Checkmate", "resigned": "Resignation",
                    "timeout": "On Time", "timevsinsufficient": "On Time"}
        parsed.append({
            "game_obj":   game_obj,
            "moves":      moves,
            "meta":       meta,
            "side":       side,
            "opp_side":   opp_side,
            "my_name":    gd[side]["username"],
            "opp_name":   gd[opp_side]["username"],
            "my_rating":  gd[side]["rating"],
            "opp_rating": gd[opp_side]["rating"],
            "win_method": win_map.get(opp_res, "Win"),
            "wname":      gd["white"]["username"],
            "bname":      gd["black"]["username"],
            "date_str":   datetime.fromtimestamp(gd.get("end_time", 0)).strftime("%B %d, %Y"),
        })

    # ── Streaming video write ─────────────────────────────────────────────────
    print(f"\n🖼️  Writing frames to {silent_path} ...")
    writer       = open_writer(silent_path)
    sound_events = []    # (frame_offset, sound_type)
    chapters     = []    # (seconds, label)
    frame_cursor = 0

    def write(img):
        writer.append_data(np.array(img))

    # Intro
    chapters.append((0, f"{month_label} — All Wins"))
    for _ in range(INTRO_FRAMES):
        write(make_intro_frame(year, month, len(games)))
    frame_cursor += INTRO_FRAMES

    for i, p in enumerate(parsed):
        game_num   = i + 1
        game_obj   = p["game_obj"]
        moves      = p["moves"]
        meta       = p["meta"]
        opp_name   = p["opp_name"]
        opp_rating = p["opp_rating"]
        my_rating  = p["my_rating"]
        my_name    = p["my_name"]
        side       = p["side"]
        flip       = (side == "black")
        ann        = game_annotations.get(i, {})

        print(f"  [{game_num:02d}/{len(games)}] vs {opp_name} ({opp_rating})"
              f"  {len(moves)} moves", end="  ")

        if not game_obj or not moves:
            print("⚠️  skipped (no PGN)")
            continue

        dt_chapter = datetime.fromtimestamp(games[i].get("end_time", 0)).strftime("%b %d")

        # Transition card (animated: 5 distinct frames)
        chapters.append((frame_cursor, f"Game {game_num} — vs {opp_name} ({opp_rating})"))
        for fi in range(TRANSITION_FRAMES):
            write(make_transition_frame(
                game_num, len(games), opp_name, opp_rating,
                p["date_str"], meta.get("time_ctrl", ""),
                meta.get("opening", ""), my_rating,
                side, p["win_method"], len(moves),
                frame_idx=fi,
            ))
        frame_cursor += TRANSITION_FRAMES

        # Classify move sounds
        tb = game_obj.board()
        move_types = []
        for mv in moves:
            move_types.append(classify_move(tb, mv))
            tb.push(mv)

        # Opening hold
        board      = game_obj.board()
        move_pairs = format_move_pairs(moves)
        clocks     = parse_clocks(game_obj)
        winner_txt = (f"{p['wname']} wins!" if games[i]["white"]["result"] == "win"
                      else f"{p['bname']} wins!")
        confetti   = make_confetti_particles(1280, 720, count=200, seed=i)

        if side == "white":
            top_name, top_rating = opp_name, opp_rating
        else:
            top_name, top_rating = p["wname"], games[i]["white"]["rating"]
        if side == "white":
            bot_name, bot_rating = my_name, my_rating
        else:
            bot_name, bot_rating = p["bname"], games[i]["black"]["rating"]

        for _ in range(OPENING_HOLD):
            write(make_game_frame(
                board, land_pieces, move_pairs, 0,
                move=None, move_num=0, total=len(moves), flip=flip,
                top_name=top_name, top_rating=top_rating, top_clk="--:--",
                bot_name=bot_name, bot_rating=bot_rating, bot_clk="--:--",
                meta=meta, annotations_by_ply=ann,
            ))
        frame_cursor += OPENING_HOLD

        # Move frames
        for mi, mv in enumerate(moves):
            ply    = mi + 1
            tag    = ann.get(ply)
            wc, bc = get_clocks_at_move(clocks, ply)
            top_clk = bc if side == "white" else wc
            bot_clk = wc if side == "white" else bc

            board.push(mv)
            sound_events.append((frame_cursor, move_types[mi]))

            write(make_game_frame(
                board, land_pieces, move_pairs, ply,
                move=mv, move_num=ply, total=len(moves), flip=flip,
                top_name=top_name, top_rating=top_rating, top_clk=top_clk,
                bot_name=bot_name, bot_rating=bot_rating, bot_clk=bot_clk,
                meta=meta,
                annotation_tag=tag,
                annotations_by_ply=ann,
            ))
            frame_cursor += 1

        # Confetti
        for fi in range(CONFETTI_FRAMES):
            write(make_game_frame(
                board, land_pieces, move_pairs, len(moves),
                move=moves[-1] if moves else None,
                move_num=len(moves), total=len(moves), flip=flip,
                top_name=top_name, top_rating=top_rating, top_clk="--:--",
                bot_name=bot_name, bot_rating=bot_rating, bot_clk="--:--",
                meta=meta, annotations_by_ply=ann,
                confetti_particles=confetti, confetti_fidx=fi,
                winner_text=winner_txt,
            ))
        frame_cursor += CONFETTI_FRAMES

        notable = sum(1 for t in ann.values() if t in ("Blunder", "Mistake"))
        print(f"✅  {frame_cursor} frames so far  ({notable} notable moves)")

    # Outro
    for _ in range(OUTRO_FRAMES):
        write(make_outro_frame(year, month, len(games)))
    frame_cursor += OUTRO_FRAMES

    writer.close()
    total_secs = frame_cursor // FPS
    print(f"\n  ✅ Silent video: {frame_cursor} frames  ({total_secs}s / "
          f"{total_secs//60}m {total_secs%60}s)")
    print(f"  📦 File: {silent_path}")

    # ── Audio ─────────────────────────────────────────────────────────────────
    print(f"\n🔊 Building audio ({len(sound_events)} move sounds)...")
    audio = build_compilation_audio(sound_events, total_secs, audio_path)

    bg_music = find_bg_music()
    if bg_music:
        print(f"  🎵 Background music: {bg_music}")
    else:
        print("  ℹ️  No background music found.")
        print("     Add sounds/longform_bg.mp3 for music.")

    print(f"\n🔗 Muxing final video...")
    ok = mux_with_audio(silent_path, audio, bg_music, final_path)
    if ok:
        os.remove(silent_path)
        if audio and os.path.exists(audio):
            os.remove(audio)
        sz = os.path.getsize(final_path) / 1024 / 1024
        print(f"  ✅ {final_path}  ({sz:.1f} MB)")
    else:
        print(f"  ⚠️  Mux failed — keeping silent video: {silent_path}")
        final_path = silent_path

    # ── Chapters ──────────────────────────────────────────────────────────────
    save_chapters(chapters, chapters_path)

    # ── Summary JSON (for script generator) ───────────────────────────────────
    summary = {
        "year": year, "month": month,
        "total_games": len(games),
        "total_seconds": total_secs,
        "video_path": final_path,
        "chapters_path": chapters_path,
        "games": [
            {
                "game_num":     i + 1,
                "opp_name":     p["opp_name"],
                "opp_rating":   p["opp_rating"],
                "my_rating":    p["my_rating"],
                "side":         p["side"],
                "win_method":   p["win_method"],
                "move_count":   len(p["moves"]),
                "date":         p["date_str"],
                "opening":      p["meta"].get("opening", ""),
                "time_ctrl":    p["meta"].get("time_ctrl", ""),
                "has_brilliant": any(
                    v == "Brilliant"
                    for v in game_annotations.get(i, {}).values()
                ),
            }
            for i, p in enumerate(parsed) if p["game_obj"]
        ],
    }
    summary_path = os.path.join(out_dir, "compilation_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  📋 Summary: {summary_path}")

    return final_path, chapters_path, summary_path


def main():
    year  = int(os.environ.get("YEAR",  0) or 0)
    month = int(os.environ.get("MONTH", 0) or 0)

    parser = argparse.ArgumentParser()
    parser.add_argument("--year",  type=int)
    parser.add_argument("--month", type=int)
    parser.add_argument("--no-stockfish", action="store_true",
                        help="Skip Stockfish analysis (faster, no annotations)")
    parser.add_argument("--max-games", type=int, default=None,
                        help="Cap the number of games (default 50; 0 = no limit)")
    parser.add_argument("--min-accuracy", type=float, default=None,
                        help="Minimum my accuracy %% to include a game (default 80)")
    parser.add_argument("--no-refetch", action="store_true",
                        help="Skip re-fetching and use existing monthly_wins.json as-is")
    args, _ = parser.parse_known_args()

    if args.year:  year  = args.year
    if args.month: month = args.month
    run_sf       = not args.no_stockfish
    max_games    = args.max_games    if args.max_games    is not None else int(os.environ.get("MAX_GAMES",    50) or 50)
    min_accuracy = args.min_accuracy if args.min_accuracy is not None else float(os.environ.get("MIN_ACCURACY", 80) or 80)

    if not year or not month:
        print("❌ Provide YEAR and MONTH")
        print("   Example: python longform_generate_video.py --year 2026 --month 1")
        sys.exit(1)

    if not args.no_refetch:
        print(f"📥 Fetching {year}/{month:02d} (checkmate wins, accuracy ≥ {min_accuracy:.0f}%, max {max_games if max_games else '∞'} games)...")
        fetch_cmd = [
            sys.executable, "longform_fetch_month.py",
            "--year", str(year), "--month", str(month),
            "--min-accuracy", str(min_accuracy),
            "--max-games", str(max_games),
        ]
        result = subprocess.run(fetch_cmd, check=False)
        if result.returncode != 0 or not os.path.exists("monthly_wins.json"):
            print("❌ Fetch failed — see output above.")
            sys.exit(1)
    elif not os.path.exists("monthly_wins.json"):
        print("❌ monthly_wins.json not found. Remove --no-refetch or run longform_fetch_month.py first.")
        sys.exit(1)

    with open("monthly_wins.json") as f:
        games = json.load(f)

    if not games:
        print("❌ No games in monthly_wins.json")
        sys.exit(1)

    print(f"📖 Loaded {len(games)} games from monthly_wins.json")

    final, chapters, summary = generate_compilation(games, year, month,
                                                     run_stockfish=run_sf)

    print(f"\n🏁 Done!")
    print(f"   Video:    {final}")
    print(f"   Chapters: {chapters}")
    print(f"   Summary:  {summary}")
    print(f"\n▶️  Next: python longform_generate_script.py --year {year} --month {month}")


if __name__ == "__main__":
    main()
