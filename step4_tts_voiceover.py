"""
STEP 4 — Synced TTS Voiceover + Like/Share/Subscribe Animation
The Thinking Athlete Pipeline

Reads commentary.json from each game folder.
For each key move:
  - Generates a TTS audio clip
  - Holds that video frame long enough for audio to finish
  - Inserts silence on normal moves (just the tak sound)
Adds Like/Share/Subscribe animation in final frames.
Produces landscape_final.mp4 + portrait_final.mp4.

Requirements:
    pip install gtts edge-tts pillow numpy imageio imageio-ffmpeg
    brew install ffmpeg
"""

import os
import sys
import json
import glob
import re
import asyncio
import subprocess
import tempfile
import shutil
import wave
import struct
import math
import random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import imageio

# ── Config ────────────────────────────────────────────────────────────────────
VIDEOS_DIR   = "videos"
TTS_ENGINE   = "gtts"           # "gtts" or "edge-tts"
GTTS_LANG    = "en"
GTTS_TLD     = "co.in"          # Indian English
EDGE_VOICE   = "en-IN-NeerjaNeural"
FPS          = 24               # Output FPS — smoother than 1fps source
NORMAL_HOLD  = 1.5              # seconds per normal move
LSS_DURATION = 4.0              # seconds for Like/Share/Subscribe animation
# ─────────────────────────────────────────────────────────────────────────────

AMBER  = (239, 159, 39)
WHITE  = (255, 255, 255)
DARK   = (13,  13,  15)
GRAY   = (136, 136, 136)
RED    = (255, 50,  50)
CONFETTI_COLORS = [
    (255,215,0),(255,69,0),(50,205,50),(30,144,255),
    (238,130,238),(255,165,0),(0,255,200),(239,159,39),
]

# ── Fonts ─────────────────────────────────────────────────────────────────────

def get_font(size, bold=False):
    for p in ["/System/Library/Fonts/Helvetica.ttc", "/Library/Fonts/Arial.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
              else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        if os.path.exists(p):
            try: return ImageFont.truetype(p, size)
            except: continue
    return ImageFont.load_default()

# ── TTS ───────────────────────────────────────────────────────────────────────

def clean_for_tts(text):
    """Make chess notation TTS-friendly."""
    piece_map = {"N":"Knight ","B":"Bishop ","R":"Rook ","Q":"Queen ","K":"King "}
    def expand(m):
        s = m.group(0)
        for sym, name in piece_map.items():
            if s.startswith(sym) and len(s) > 1:
                s = name + s[1:]; break
        s = re.sub(r'([a-h])([1-8])', r'\1 \2', s)
        s = s.replace("x", " takes ").replace("+","check").replace("#","checkmate")
        return s
    text = re.sub(r'\b([NBRQK]?[a-h]?[1-8]?x?[a-h][1-8][+#]?)\b', expand, text)
    text = text.replace("O-O-O","queenside castle").replace("O-O","kingside castle")
    text = re.sub(r'[*_]', '', text)
    return text

def tts_gtts(text, path):
    from gtts import gTTS
    gTTS(text=clean_for_tts(text), lang=GTTS_LANG, tld=GTTS_TLD, slow=False).save(path)
    return True

async def tts_edge_async(text, path):
    import edge_tts
    await edge_tts.Communicate(clean_for_tts(text), EDGE_VOICE).save(path)

def tts_edge(text, path):
    asyncio.run(tts_edge_async(text, path))
    return True

def generate_tts(text, path):
    try:
        if TTS_ENGINE == "gtts": return tts_gtts(text, path)
        else: return tts_edge(text, path)
    except:
        try:
            if TTS_ENGINE == "gtts": return tts_edge(text, path)
            else: return tts_gtts(text, path)
        except Exception as e:
            print(f"  ❌ TTS failed: {e}"); return False

def get_audio_duration(path):
    """Get duration of an audio file in seconds using ffprobe."""
    cmd = ["ffprobe","-v","error","-show_entries","format=duration",
           "-of","default=noprint_wrappers=1:nokey=1", path]
    r = subprocess.run(cmd, capture_output=True, text=True)
    try: return float(r.stdout.strip())
    except: return 1.0

# ── Like/Share/Subscribe overlay ──────────────────────────────────────────────

def draw_lss_overlay(img, progress, W, H):
    """
    Draw animated Like/Share/Subscribe bar.
    progress: 0.0 → 1.0 (animation progress)
    Slides up from bottom, pulses at 0.5.
    """
    draw     = ImageDraw.Draw(img)
    f_lg     = get_font(max(18, W//40), bold=True)
    f_sm     = get_font(max(13, W//60))

    bar_h    = max(80, H//10)
    # Slide in from bottom
    ease     = min(1.0, progress * 2.5)   # fast slide in
    slide_y  = int(H - bar_h * ease)

    # Background bar
    draw.rectangle([0, slide_y, W, slide_y + bar_h], fill=(0, 0, 0))
    draw.rectangle([0, slide_y, W, slide_y + 3], fill=AMBER)

    # Pulse scale at mid-animation
    pulse = 1.0 + 0.08 * math.sin(progress * math.pi * 3)

    # Items
    items = [
        ("👍", "LIKE",      RED),
        ("🔗", "SHARE",     WHITE),
        ("🔔", "SUBSCRIBE", AMBER),
    ]

    item_w  = W // 3
    icon_sz = int(max(20, W//30) * pulse)
    f_icon  = get_font(icon_sz, bold=True)
    f_lbl   = get_font(max(10, W//60))

    for idx, (icon, label, color) in enumerate(items):
        cx = item_w * idx + item_w // 2
        cy = slide_y + bar_h // 2

        # Separator line
        if idx > 0:
            draw.line([item_w * idx, slide_y + 10,
                       item_w * idx, slide_y + bar_h - 10],
                      fill=(60, 60, 60), width=1)

        draw.text((cx, cy - 6), icon,  fill=color, font=f_icon, anchor="mm")
        draw.text((cx, cy + icon_sz//2 + 4), label, fill=color,
                  font=f_lbl, anchor="mm")

    # Channel name
    draw.text((W//2, slide_y + bar_h - 12),
              "@ChessAthleteAbhishek", fill=GRAY, font=f_sm, anchor="mm")

    return img

# ── Build final video ─────────────────────────────────────────────────────────

def extract_frames_from_video(video_path, fps=FPS):
    """Read all frames from a video file."""
    reader = imageio.get_reader(video_path)
    frames = [frame for frame in reader]
    reader.close()
    return frames

def get_frame_for_halfmove(source_frames, half_move, total_half_moves):
    """
    Map a half-move index to a source frame.
    Source video has: 2 opening frames + 1 frame per move + confetti frames.
    """
    opening_frames = 2
    confetti_frames = 5

    if half_move == 0:
        return source_frames[0]
    elif half_move == 99999:
        return source_frames[-1]
    else:
        idx = opening_frames + (half_move - 1)
        idx = min(idx, len(source_frames) - confetti_frames - 1)
        return source_frames[max(0, idx)]

def build_synced_video(source_frames, commentary, total_half_moves,
                       audio_clips, output_path, W, H):
    """
    Build final video with:
    - Per-move frames held for the duration of their TTS audio
    - Normal moves held for NORMAL_HOLD seconds
    - Like/Share/Subscribe animation in last LSS_DURATION seconds
    - All audio clips concatenated in sync
    """
    tmpdir = tempfile.mkdtemp()
    try:
        # Build frame timeline
        # commentary dict: half_move → {commentary, hold_seconds, audio_path, audio_dur}
        comm_by_hm = {c["half_move"]: c for c in commentary}

        timeline    = []   # list of (frame, duration_seconds)

        # Intro
        if 0 in comm_by_hm:
            c   = comm_by_hm[0]
            dur = c.get("audio_dur", c.get("hold_seconds", 3))
            timeline.append((source_frames[0], dur))

        # Moves
        for hm in range(1, total_half_moves + 1):
            frame = get_frame_for_halfmove(source_frames, hm, total_half_moves)
            if hm in comm_by_hm:
                c   = comm_by_hm[hm]
                dur = max(c.get("hold_seconds", 2), c.get("audio_dur", 0) + 0.3)
            else:
                dur = NORMAL_HOLD
            timeline.append((frame, dur))

        # Confetti frames (from source, animated)
        confetti_frame = source_frames[-3]   # one of the confetti frames
        timeline.append((confetti_frame, 2.0))

        # LSS animation frames
        lss_frame_count = int(LSS_DURATION * FPS)
        base_frame      = source_frames[-1]
        for fi in range(lss_frame_count):
            progress  = fi / lss_frame_count
            frame_img = Image.fromarray(base_frame).copy()
            frame_img = draw_lss_overlay(frame_img, progress, W, H)
            timeline.append((np.array(frame_img), 1.0 / FPS))

        # Write video
        print(f"    📽️  Writing {sum(int(d*FPS) for _,d in timeline)} frames...")
        vid_tmp = os.path.join(tmpdir, "video_only.mp4")
        writer  = imageio.get_writer(vid_tmp, fps=FPS, codec="libx264",
                                     output_params=["-crf","23","-pix_fmt","yuv420p"])
        for frame, dur in timeline:
            n_frames = max(1, int(dur * FPS))
            arr      = np.array(frame) if not isinstance(frame, np.ndarray) else frame
            for _ in range(n_frames):
                writer.append_data(arr)
        writer.close()

        # Build audio timeline
        audio_tmp  = os.path.join(tmpdir, "audio.aac")
        build_synced_audio(timeline, comm_by_hm, tmpdir, audio_tmp)

        # Mux
        cmd = ["ffmpeg", "-y",
               "-i", vid_tmp, "-i", audio_tmp,
               "-c:v", "copy", "-c:a", "aac", "-shortest", output_path]
        subprocess.run(cmd, capture_output=True)

        print(f"    ✅ {os.path.basename(output_path)}")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

def build_synced_audio(timeline, comm_by_hm, tmpdir, output_path):
    """
    Build audio track with TTS clips placed at exact timestamps.
    Silence between clips (move sounds already baked into source video).
    """
    # Calculate cumulative timestamps
    timestamps = []
    t = 0.0
    for i, (frame, dur) in enumerate(timeline):
        timestamps.append(t)
        t += dur
    total_dur = t

    # Build ffmpeg inputs + filter for placing each audio clip
    inputs  = []
    filters = []
    n       = 0

    for i, (frame, dur) in enumerate(timeline):
        # Find which half_move this corresponds to
        # timeline[0] = intro, timeline[1..N] = moves, rest = confetti/lss
        if i == 0:
            hm = 0
        elif i <= sum(1 for _ in timeline) - int(LSS_DURATION * FPS) - 2:
            hm = i
        else:
            hm = None

        if hm is not None and hm in comm_by_hm:
            c = comm_by_hm[hm]
            ap = c.get("audio_path", "")
            if ap and os.path.exists(ap):
                offset_ms = int(timestamps[i] * 1000)
                inputs  += ["-i", ap]
                filters.append(f"[{n}]adelay={offset_ms}|{offset_ms}[a{n}]")
                n += 1

    if n == 0:
        # No audio clips — generate silence
        cmd = ["ffmpeg", "-y", "-f", "lavfi",
               "-i", f"anullsrc=r=44100:cl=mono:d={total_dur}",
               "-c:a", "aac", output_path]
        subprocess.run(cmd, capture_output=True)
        return

    mix     = "".join(f"[a{i}]" for i in range(n))
    filters.append(f"{mix}amix=inputs={n}:normalize=0:duration=longest[out]")

    cmd = (["ffmpeg", "-y"] + inputs +
           ["-filter_complex", ";".join(filters),
            "-map", "[out]",
            "-t", str(total_dur),
            "-c:a", "aac", output_path])
    subprocess.run(cmd, capture_output=True)

# ── Process one game folder ───────────────────────────────────────────────────

def process_game(game_dir):
    commentary_path = os.path.join(game_dir, "commentary.json")
    land_path       = os.path.join(game_dir, "landscape.mp4")
    port_path       = os.path.join(game_dir, "portrait.mp4")
    land_final      = os.path.join(game_dir, "landscape_final.mp4")
    port_final      = os.path.join(game_dir, "portrait_final.mp4")

    if os.path.exists(land_final) and os.path.exists(port_final):
        print(f"  ⏭️  Already done, skipping.")
        return True

    missing = [f for f in [commentary_path, land_path, port_path]
               if not os.path.exists(f)]
    if missing:
        print(f"  ⚠️  Missing: {[os.path.basename(f) for f in missing]}")
        return False

    with open(commentary_path) as f:
        data        = json.load(f)
    commentary      = data["commentary"]
    total_half_moves = None  # will infer from source video

    # Generate TTS for each commentary item
    print(f"  🎙️  Generating {len(commentary)} audio clips...")
    tmpdir = tempfile.mkdtemp()
    try:
        for c in commentary:
            audio_path = os.path.join(tmpdir, f"clip_{c['half_move']}.mp3")
            ok         = generate_tts(c["commentary"], audio_path)
            if ok:
                dur = get_audio_duration(audio_path)
                c["audio_path"] = audio_path
                c["audio_dur"]  = dur
            else:
                c["audio_path"] = ""
                c["audio_dur"]  = c.get("hold_seconds", 2.0)

        comm_by_hm = {c["half_move"]: c for c in commentary}

        # Process landscape
        print(f"  🎬 Building landscape_final.mp4...")
        land_frames = extract_frames_from_video(land_path)
        total_hm    = len(land_frames) - 2 - 5  # minus opening + confetti
        W, H        = land_frames[0].shape[1], land_frames[0].shape[0]
        build_synced_video(land_frames, commentary, total_hm,
                           comm_by_hm, land_final, W, H)

        # Process portrait
        print(f"  🎬 Building portrait_final.mp4...")
        port_frames = extract_frames_from_video(port_path)
        W2, H2      = port_frames[0].shape[1], port_frames[0].shape[0]
        build_synced_video(port_frames, commentary, total_hm,
                           comm_by_hm, port_final, W2, H2)

        return True

    except Exception as e:
        print(f"  ❌ Error: {e}")
        import traceback; traceback.print_exc()
        return False
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    game_folders = sorted(glob.glob(os.path.join(VIDEOS_DIR, "*", "*", "game_*")))

    ready = [g for g in game_folders
             if os.path.exists(os.path.join(g, "commentary.json"))
             and os.path.exists(os.path.join(g, "landscape.mp4"))]

    if not ready:
        print("❌ No game folders ready — run step2 and step3 first!")
        sys.exit(1)

    print(f"🎙️  Processing {len(ready)} games\n")
    print(f"   Voice: Indian English ({'gTTS' if TTS_ENGINE == 'gtts' else 'Edge TTS'})")
    print(f"   FPS: {FPS} | Normal move hold: {NORMAL_HOLD}s\n")

    success = 0
    for game_dir in ready:
        name = os.path.basename(game_dir)
        print(f"🎮 {name}")
        if process_game(game_dir):
            success += 1
        print()

    print(f"🏁 Done! {success}/{len(ready)} games processed.")
    print(f"\n📂 Final videos in each game folder:")
    print(f"   landscape_final.mp4 → YouTube")
    print(f"   portrait_final.mp4  → Instagram Reels / YouTube Shorts")

if __name__ == "__main__":
    main()
