"""
STEP 1c — Generate Voiceover Commentary from Analysis
The Thinking Athlete Pipeline

Reads analysis/game_XXX_analysis.json (from step1b) and asks Claude to write
a spoken commentary script in the Thinking Athlete voice:
  - 1 intro line (plays over the opening moves)
  - 1 line per key moment (tagged to its ply, for audio sync in step2)
  - 1 outro line (plays over the checkmate/result)

Output: commentary/game_XXX_commentary.json

Requirements:
    export ANTHROPIC_API_KEY="..."     # already in your ~/.zshrc per README
    pip install requests               # already installed

Usage:
    python step1c_generate_commentary.py        # game 0
    python step1c_generate_commentary.py 3      # game at index 3
"""

import json
import os
import sys
import requests

# ── Config ────────────────────────────────────────────────────────────────────

MODEL        = "claude-sonnet-4-6"
MAX_TOKENS   = 2000
ANALYSIS_DIR = "analysis"
OUT_DIR      = "commentary"

VOICE_GUIDE = """
You are writing a voiceover script for "The Thinking Athlete" — a chess YouTube
channel run by Abhishek, a 42-year-old developer from Hyderabad climbing the
chess.com ladder (Road to 1000). He reviews his own wins.

Voice rules:
- First person ("I", "my opponent"). Calm confidence, warm coach energy.
- Think out loud: "Here I'm eyeing the d-file because..."
- Brutally honest about his own mistakes — vulnerability builds trust.
  When HE blunders, own it plainly, maybe with light self-humour.
- Never pretend to be a GM. He's a learner narrating honestly.
- Occasionally (max once per game) a fitness/running analogy — it's his brand.
- Each line must be speakable in under 10 seconds (roughly 25 words max).
- Plain spoken English. No chess jargon a beginner wouldn't know without
  a quick gloss. Say moves naturally: "bishop takes f2, check" not "Bxf2+".
"""

# ── Prompt building ───────────────────────────────────────────────────────────

def build_prompt(analysis):
    km_set  = set(analysis["key_moments"])
    moments = [m for m in analysis["moves"] if m["ply"] in km_set]

    lines = []
    for m in moments:
        who = "I" if m["player"] == "me" else "My opponent"
        lines.append(
            f"- ply {m['ply']} (move {m['move_num']}): {who} played {m['san']} "
            f"[{m['tag']}]. Eval swing: {m['delta']:+d} centipawns. "
            f"Engine preferred: {m['best_alt']}. "
            f"{'CHECKMATE — game over.' if m['is_checkmate'] else ''}"
        )

    game_summary = (
        f"I played as {analysis['played_as']} "
        f"({analysis['white']} vs {analysis['black']}). "
        f"I won. My accuracy: {analysis['my_accuracy']}%, "
        f"opponent's: {analysis['opp_accuracy']}%. "
        f"Total half-moves: {len(analysis['moves'])}."
    )

    return f"""{VOICE_GUIDE}

GAME SUMMARY:
{game_summary}

KEY MOMENTS (write exactly one commentary line for each):
{chr(10).join(lines)}

Write the full commentary script. Respond ONLY with valid JSON, no markdown
fences, no preamble, in exactly this shape:
{{
  "intro": "one line setting up the game, spoken over the opening moves",
  "lines": [
    {{"ply": <ply number>, "text": "commentary line for that moment"}}
  ],
  "outro": "one closing line: the takeaway/lesson + a soft ask to subscribe"
}}
The "lines" array must contain one entry per key moment above, in ply order,
using the exact ply numbers given."""

# ── Claude API call ───────────────────────────────────────────────────────────

def call_claude(prompt):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("❌ ANTHROPIC_API_KEY not set. Run:  source ~/.zshrc")
        sys.exit(1)

    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": MODEL,
            "max_tokens": MAX_TOKENS,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=120,
    )
    resp.raise_for_status()
    text = "".join(b.get("text", "") for b in resp.json()["content"])
    # Strip accidental markdown fences before parsing
    text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    game_idx = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    in_path  = os.path.join(ANALYSIS_DIR, f"game_{game_idx:03d}_analysis.json")

    if not os.path.exists(in_path):
        print(f"❌ {in_path} not found — run step1b_analyze_game_v2.py first!")
        sys.exit(1)

    with open(in_path) as f:
        analysis = json.load(f)

    print(f"🎙️  Generating commentary: {analysis['white']} vs {analysis['black']}")
    print(f"   Key moments: {len(analysis['key_moments'])}  |  Model: {MODEL}\n")

    script = call_claude(build_prompt(analysis))

    # Sanity check: every line's ply must exist in the analysis
    valid_plies = {m["ply"] for m in analysis["moves"]}
    for line in script["lines"]:
        if line["ply"] not in valid_plies:
            print(f"⚠️  Claude referenced unknown ply {line['ply']} — check output")

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"game_{game_idx:03d}_commentary.json")
    with open(out_path, "w") as f:
        json.dump(script, f, indent=2, ensure_ascii=False)

    print(f"{'═'*60}")
    print(f"🎬 COMMENTARY SCRIPT")
    print(f"{'═'*60}")
    print(f"\n[INTRO]  {script['intro']}\n")
    for line in script["lines"]:
        print(f"[ply {line['ply']:2d}] {line['text']}\n")
    print(f"[OUTRO]  {script['outro']}")
    print(f"{'═'*60}")
    print(f"\n✅ Saved: {out_path}")
    print(f"   Next: TTS (step1d) turns these lines into audio.")

if __name__ == "__main__":
    main()
