"""
STEP 2b — Add Voiceover Commentary to the Landscape Video
The Thinking Athlete Pipeline

Takes the finished landscape.mp4 (from step2, UNMODIFIED) and produces
landscape_commentary.mp4 in the same game folder:

  - Holds the opening position while the intro line plays
  - Freezes the board on each key moment for the length of its voice clip
  - Holds the confetti while the outro plays
  - Rebuilds audio: move/capture/castle sounds at their new times + voiceover

Relies on step2's fixed timing (FPS=1):
  seconds [0,2)          opening hold
  second  [2+i, 3+i)     board after move i (0-based)  → ply i+1
  last 5 seconds         confetti

Requirements: ffmpeg (installed), outputs of step1b/1c/1d for the same game.

Usage:
    python step2b_add_commentary.py          # game 0
    python step2b_add_commentary.py 3        # game at index 3
"""

import chess
import chess.pgn
import glob
import io
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile

# ── Config (matches step2) ────────────────────────────────────────────────────

FPS             = 1
OPENING_HOLD    = 2      # seconds of start position in step2's output
CONFETTI_SECS   = 5      # CONFETTI_FRAMES in step2
SOUNDS_DIR      = "sounds"
VIDEOS_DIR      = "videos"
MOVE_SOUND_VOL  = 0.6    # duck the click sounds under the voice
VOICE_VOL       = 1.4

ENC = ["-c:v", "libx264", "-crf", "23", "-pix_fmt", "yuv420p", "-r", str(FPS)]

# ── Small helpers ─────────────────────────────────────────────────────────────

def run(cmd, err_label):
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        print(f"  ❌ {err_label} failed:\n{r.stderr.decode()[-400:]}")
        sys.exit(1)

def find_landscape(game_idx):
    """Locate videos/YYYY/MM_Month/game_XXX_*/landscape.mp4 for this index."""
    hits = glob.glob(os.path.join(VIDEOS_DIR, "*", "*",
                                  f"game_{game_idx:03d}_*", "landscape.mp4"))
    if not hits:
        print(f"❌ No landscape.mp4 found for game index {game_idx} — run step2 first!")
        sys.exit(1)
    return hits[0]

def move_sound_types(pgn_text):
    """Same classification as step2: one sound name per half-move."""
    game  = chess.pgn.read_game(io.StringIO(pgn_text))
    board = game.board()
    types = []
    for mv in game.mainline_moves():
        if board.is_castling(mv):     types.append("castle")
        elif mv.promotion:            types.append("promote")
        elif board.is_capture(mv):    types.append("capture")
        else:                         types.append("move")
        board.push(mv)
    return types

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    game_idx = int(sys.argv[1]) if len(sys.argv) > 1 else 0

    # Load all the inputs
    with open("won_games.json") as f:
        games = json.load(f)
    if game_idx >= len(games):
        print(f"❌ won_games.json has only {len(games)} games."); sys.exit(1)

    manifest_path = os.path.join("voice", f"game_{game_idx:03d}", "manifest.json")
    if not os.path.exists(manifest_path):
        print(f"❌ {manifest_path} not found — run step1d first!"); sys.exit(1)
    with open(manifest_path) as f:
        manifest = json.load(f)
    voice_dir = os.path.dirname(manifest_path)

    src = find_landscape(game_idx)
    out = os.path.join(os.path.dirname(src), "landscape_commentary.mp4")

    types      = move_sound_types(games[game_idx]["pgn"])
    n_moves    = len(types)
    total_orig = OPENING_HOLD + n_moves + CONFETTI_SECS

    intro = next((m for m in manifest if m["name"] == "intro"), None)
    outro = next((m for m in manifest if m["name"] == "outro"), None)
    plies = {m["ply"]: m for m in manifest if m["ply"] is not None}

    # ── 1. Plan the freeze insertions ────────────────────────────────────────
    # Each insertion: (boundary_sec_in_original, hold_secs, freeze_frame_at)
    inserts = []
    if intro:
        extra = max(0, math.ceil(intro["duration"]) + 1 - OPENING_HOLD)
        if extra:
            inserts.append((OPENING_HOLD, extra, 0.5))          # hold start position
    for ply, seg in sorted(plies.items()):
        if ply > n_moves:
            continue
        boundary = OPENING_HOLD + ply                            # end of that move's second
        inserts.append((boundary, math.ceil(seg["duration"]), boundary - 0.5))
    if outro:
        extra = max(0, math.ceil(outro["duration"]) + 1 - CONFETTI_SECS)
        if extra:
            inserts.append((total_orig, extra, total_orig - 0.5))  # hold last confetti frame

    def new_time(t_orig):
        """Map an original timestamp to the extended timeline."""
        return t_orig + sum(d for b, d, _ in inserts if b <= t_orig)

    total_new = total_orig + sum(d for _, d, _ in inserts)
    print(f"🎬 {os.path.basename(os.path.dirname(src))}")
    print(f"   {n_moves} moves | video {total_orig}s → {total_new}s "
          f"({len(inserts)} holds)\n")

    # ── 2. Cut + freeze + concat the video (silent) ──────────────────────────
    tmp = tempfile.mkdtemp()
    seg_paths, cursor = [], 0.0

    def add_copy(a, b):
        if b - a <= 0: return
        p = os.path.join(tmp, f"seg_{len(seg_paths):02d}.mp4")
        run(["ffmpeg", "-y", "-i", src, "-ss", str(a), "-to", str(b), "-an"] + ENC + [p],
            f"cut {a}-{b}")
        seg_paths.append(p)

    def add_freeze(at, dur):
        png = os.path.join(tmp, f"fz_{len(seg_paths):02d}.png")
        run(["ffmpeg", "-y", "-ss", str(at), "-i", src, "-frames:v", "1", png],
            f"frame @{at}")
        p = os.path.join(tmp, f"seg_{len(seg_paths):02d}.mp4")
        run(["ffmpeg", "-y", "-loop", "1", "-i", png, "-t", str(dur), "-an"] + ENC + [p],
            f"freeze @{at}")
        seg_paths.append(p)

    for boundary, dur, freeze_at in inserts:
        add_copy(cursor, boundary)
        add_freeze(freeze_at, dur)
        cursor = boundary
        print(f"  🧊 hold {dur:2d}s at original t={boundary}s")
    add_copy(cursor, total_orig)

    listfile = os.path.join(tmp, "list.txt")
    with open(listfile, "w") as f:
        for p in seg_paths:
            f.write(f"file '{p}'\n")
    silent = os.path.join(tmp, "silent.mp4")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listfile] + ENC + [silent],
        "concat")

    # ── 3. Rebuild the audio: move sounds + voice, at NEW timestamps ─────────
    sounds = {n: os.path.join(SOUNDS_DIR, f)
              for n, f in [("move", "move1.mp3"), ("capture", "capture.mp3"),
                           ("castle", "castle.mp3"), ("promote", "promote.mp3")]}

    events = []                                   # (offset_sec, filepath, volume)
    for i, t in enumerate(types):                 # move i lands at orig 2+i
        events.append((new_time(OPENING_HOLD + i), sounds[t], MOVE_SOUND_VOL))
    if intro:
        events.append((0.3, os.path.join(voice_dir, intro["file"]), VOICE_VOL))
    for ply, seg in plies.items():
        events.append((new_time(OPENING_HOLD + ply - 1) + 0.2,
                       os.path.join(voice_dir, seg["file"]), VOICE_VOL))
    if outro:
        events.append((new_time(OPENING_HOLD + n_moves) + 0.3,
                       os.path.join(voice_dir, outro["file"]), VOICE_VOL))

    inputs, filters = [], []
    for i, (off, path, vol) in enumerate(events):
        ms = int(off * 1000)
        inputs += ["-i", path]
        filters.append(f"[{i}]volume={vol},adelay={ms}|{ms}[a{i}]")
    mix = "".join(f"[a{i}]" for i in range(len(events)))
    filters.append(f"{mix}amix=inputs={len(events)}:normalize=0:duration=longest[out]")

    audio = os.path.join(tmp, "track.aac")
    run(["ffmpeg", "-y"] + inputs +
        ["-filter_complex", ";".join(filters), "-map", "[out]",
         "-t", str(total_new), "-c:a", "aac", audio], "audio build")

    # ── 4. Mux ────────────────────────────────────────────────────────────────
    run(["ffmpeg", "-y", "-i", silent, "-i", audio,
         "-filter_complex", "[1:a]apad[aout]",
         "-map", "0:v", "-map", "[aout]",
         "-c:v", "copy", "-c:a", "aac", "-shortest", out], "mux")
    shutil.rmtree(tmp, ignore_errors=True)

    mb = os.path.getsize(out) / 1024 / 1024
    print(f"\n✅ {out}  ({mb:.1f}MB, {total_new}s)")
    print(f"   Original landscape.mp4 left untouched — compare them side by side.")

if __name__ == "__main__":
    main()
