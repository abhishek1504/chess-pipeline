"""
STEP 2b (v4) — Add Voiceover Commentary to the Landscape Video
The Thinking Athlete Pipeline

Takes the finished landscape.mp4 (from step2, UNMODIFIED) and produces
landscape_commentary.mp4 in the same game folder.

v4 approach — sync correct by construction:
  1. Extract every frame of the source as a numbered PNG (1 frame = 1 second).
  2. Build the new video as an explicit frame schedule: normal moves appear
     once; key moments repeat for the length of their voice clip.
  3. Record each sound/voice offset WHILE building the schedule, so audio
     and video can never drift apart.

Source video layout (step2, FPS=1):
  frames 0,1            opening position
  frame  2+i            board after move i (0-based) → ply i+1
  last 5 frames         confetti

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

OPENING_FRAMES  = 2
CONFETTI_FRAMES = 5
SOUNDS_DIR      = "sounds"
VIDEOS_DIR      = "videos"
MOVE_SOUND_VOL  = 0.6    # duck the click sounds under the voice
VOICE_VOL       = 1.4

ENC = ["-c:v", "libx264", "-crf", "23", "-pix_fmt", "yuv420p", "-r", "1"]

# ── Helpers ───────────────────────────────────────────────────────────────────

def run(cmd, err_label):
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        print(f"  ❌ {err_label} failed:\n{r.stderr.decode()[-400:]}")
        sys.exit(1)

def find_landscape(game_idx, game_data):
    hits = glob.glob(os.path.join(VIDEOS_DIR, "*", "*",
                                  f"game_{game_idx:03d}_*", "landscape.mp4"))
    if hits:
        return hits[0]
    white = game_data["white"]["username"]
    black = game_data["black"]["username"]
    hits = glob.glob(os.path.join(VIDEOS_DIR, "*", "*",
                                  f"game_*_{white}_vs_{black}", "landscape.mp4"))
    if hits:
        print(f"  ℹ️  Matched by player names: {os.path.dirname(hits[0])}")
        return hits[0]
    print(f"❌ No landscape.mp4 for game {game_idx} ({white} vs {black}) — run step2 first!")
    sys.exit(1)

def move_sound_types(pgn_text):
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

    src   = find_landscape(game_idx, games[game_idx])
    out   = os.path.join(os.path.dirname(src), "landscape_commentary.mp4")
    types = move_sound_types(games[game_idx]["pgn"])
    n     = len(types)

    intro = next((m for m in manifest if m["name"] == "intro"), None)
    outro = next((m for m in manifest if m["name"] == "outro"), None)
    plies = {m["ply"]: m for m in manifest if m["ply"] is not None}

    # ── 1. Extract every source frame as a PNG ────────────────────────────────
    tmp = tempfile.mkdtemp()
    print("  🖼️  Extracting frames...")
    run(["ffmpeg", "-y", "-i", src, "-vsync", "0",
         os.path.join(tmp, "f_%04d.png")], "frame extraction")
    frames = sorted(glob.glob(os.path.join(tmp, "f_*.png")))
    expected = OPENING_FRAMES + n + CONFETTI_FRAMES
    if len(frames) != expected:
        print(f"  ⚠️  Expected {expected} frames, got {len(frames)} — "
              f"check OPENING_FRAMES/CONFETTI_FRAMES match your step2.")
    # frame index -> file (0-based, so frames[2+i] = board after move i)

    # ── 2. Build the frame schedule + audio events in one pass ───────────────
    schedule = []                                  # list of frame indices, 1s each
    events   = []                                  # (offset_sec, filepath, volume)
    sounds   = {k: os.path.join(SOUNDS_DIR, v)
                for k, v in [("move", "move1.mp3"), ("capture", "capture.mp3"),
                             ("castle", "castle.mp3"), ("promote", "promote.mp3")]}

    def now():
        return len(schedule)                       # current second of new video

    # Opening — hold the start position long enough for the intro line
    opening_secs = OPENING_FRAMES
    if intro:
        opening_secs = max(OPENING_FRAMES, math.ceil(intro["duration"]) + 1)
        events.append((0.3, os.path.join(voice_dir, intro["file"]), VOICE_VOL))
    schedule.append(0)
    schedule.extend([1] * (opening_secs - 1))

    # Moves — key moments repeat for the length of their voice clip
    holds = 0
    for i in range(n):
        ply, fidx = i + 1, OPENING_FRAMES + i
        events.append((now(), sounds[types[i]], MOVE_SOUND_VOL))
        schedule.append(fidx)
        if ply in plies:
            seg = plies[ply]
            events.append((now() - 1 + 0.2,
                           os.path.join(voice_dir, seg["file"]), VOICE_VOL))
            schedule.extend([fidx] * math.ceil(seg["duration"]))
            holds += 1

    # Confetti — hold the last frame long enough for the outro
    if outro:
        events.append((now() + 0.3, os.path.join(voice_dir, outro["file"]), VOICE_VOL))
    for c in range(CONFETTI_FRAMES):
        schedule.append(OPENING_FRAMES + n + c)
    if outro:
        extra = max(0, math.ceil(outro["duration"]) + 1 - CONFETTI_FRAMES)
        schedule.extend([schedule[-1]] * extra)

    total = len(schedule)
    print(f"🎬 {os.path.basename(os.path.dirname(src))}")
    print(f"   {n} moves | {holds} commentary holds | video {expected}s → {total}s")

    # ── 3. Encode video from the schedule (concat demuxer on images) ─────────
    last_valid = len(frames) - 1
    listfile = os.path.join(tmp, "list.txt")
    with open(listfile, "w") as f:
        for idx in schedule:
            f.write(f"file '{frames[min(idx, last_valid)]}'\nduration 1\n")
        f.write(f"file '{frames[min(schedule[-1], last_valid)]}'\n")  # concat quirk
    silent = os.path.join(tmp, "silent.mp4")
    print("  🎞️  Encoding video...")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listfile] + ENC + [silent],
        "encode")

    # ── 4. Build audio track from the recorded events ─────────────────────────
    print("  🔊 Building audio...")
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
         "-t", str(total), "-c:a", "aac", audio], "audio build")

    # ── 5. Mux ────────────────────────────────────────────────────────────────
    run(["ffmpeg", "-y", "-i", silent, "-i", audio,
         "-filter_complex", "[1:a]apad[aout]",
         "-map", "0:v", "-map", "[aout]",
         "-c:v", "copy", "-c:a", "aac", "-shortest", out], "mux")
    shutil.rmtree(tmp, ignore_errors=True)

    mb = os.path.getsize(out) / 1024 / 1024
    print(f"\n✅ {out}  ({mb:.1f}MB, {total}s)")
    print(f"   Original landscape.mp4 untouched.")

if __name__ == "__main__":
    main()
