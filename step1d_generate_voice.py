"""
STEP 1d — Generate Voiceover Audio from Commentary
The Thinking Athlete Pipeline

Reads commentary/game_XXX_commentary.json (from step1c) and produces one MP3
per commentary segment, plus a manifest.json with each clip's duration —
step2 uses those durations to know how long to hold the board on key moments.

Output:
    voice/game_XXX/intro.mp3
    voice/game_XXX/ply_042.mp3   (one per key moment)
    voice/game_XXX/outro.mp3
    voice/game_XXX/manifest.json

Requirements:
    pip install edge-tts
    brew install ffmpeg          # already installed for step2

Usage:
    python step1d_generate_voice.py          # game 0
    python step1d_generate_voice.py 3        # game at index 3
    python step1d_generate_voice.py --voices # list available Indian/English voices
"""

import asyncio
import json
import os
import subprocess
import sys

import edge_tts

# ── Config ────────────────────────────────────────────────────────────────────

VOICE          = "en-IN-PrabhatNeural"   # male, Indian English. Try en-IN-NeerjaNeural (female)
RATE           = "+0%"                   # e.g. "-10%" for slower, "+10%" for faster
COMMENTARY_DIR = "commentary"
OUT_DIR        = "voice"

# ── Helpers ───────────────────────────────────────────────────────────────────

def clip_duration(path):
    """Duration of an audio file in seconds, via ffprobe."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True, text=True,
    )
    return round(float(out.stdout.strip()), 2)

async def speak(text, path):
    await edge_tts.Communicate(text, VOICE, rate=RATE).save(path)

async def list_voices():
    voices = await edge_tts.list_voices()
    print("English voices you might like:\n")
    for v in voices:
        if v["Locale"].startswith(("en-IN", "en-GB", "en-US", "en-AU")):
            print(f"  {v['ShortName']:28s} {v['Gender']:7s} {v['Locale']}")

# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    if "--voices" in sys.argv:
        await list_voices()
        return

    game_idx = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    in_path  = os.path.join(COMMENTARY_DIR, f"game_{game_idx:03d}_commentary.json")

    if not os.path.exists(in_path):
        print(f"❌ {in_path} not found — run step1c_generate_commentary.py first!")
        sys.exit(1)

    with open(in_path) as f:
        script = json.load(f)

    out_dir = os.path.join(OUT_DIR, f"game_{game_idx:03d}")
    os.makedirs(out_dir, exist_ok=True)

    # Build the list of segments: intro, one per key moment, outro
    segments = [{"name": "intro", "ply": None, "text": script["intro"]}]
    for line in script["lines"]:
        segments.append({
            "name": f"ply_{line['ply']:03d}",
            "ply":  line["ply"],
            "text": line["text"],
        })
    segments.append({"name": "outro", "ply": None, "text": script["outro"]})

    print(f"🎙️  Voice: {VOICE}  |  {len(segments)} clips\n")

    manifest = []
    for seg in segments:
        path = os.path.join(out_dir, f"{seg['name']}.mp3")
        await speak(seg["text"], path)
        dur = clip_duration(path)
        manifest.append({
            "name":     seg["name"],
            "ply":      seg["ply"],
            "file":     f"{seg['name']}.mp3",
            "duration": dur,
            "text":     seg["text"],
        })
        print(f"  ✅ {seg['name']:10s} {dur:5.1f}s  \"{seg['text'][:55]}...\"")

    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    total = sum(m["duration"] for m in manifest)
    print(f"\n{'═'*55}")
    print(f"  Total voiceover: {total:.0f}s across {len(manifest)} clips")
    print(f"  ✅ Saved to {out_dir}/ (+ manifest.json)")
    print(f"{'═'*55}")
    print(f"\n💡 Listen before proceeding:  open {out_dir}/intro.mp3")
    print(f"   Different voice? Run:  python step1d_generate_voice.py --voices")

if __name__ == "__main__":
    asyncio.run(main())
