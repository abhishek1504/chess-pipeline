"""
longform_generate_script.py — YouTube Metadata for Monthly Compilation
The Thinking Athlete Pipeline — Long-Form Content

Reads compilation_summary.json and chapters.txt produced by longform_generate_video.py
and writes a script.txt with YouTube-ready title, description, hashtags, and tags.

Usage:
    python longform_generate_script.py --year 2026 --month 1
"""

import json
import os
import re
import sys
import argparse
from datetime import datetime

USERNAME       = "abhi15041984"
CHANNEL        = "Indian Thinking Athlete"
CHANNEL_HANDLE = "@indianthinkingathlete"
EMAIL          = "thinkingathleteindia@gmail.com"
OUTPUT_DIR     = "longform"
NEXT_MILESTONE = int(os.environ.get("NEXT_MILESTONE", "1200"))
PREV_MILESTONE = int(os.environ.get("PREV_MILESTONE", "1000"))

MONTH_NAMES = {
    1:"01_January", 2:"02_February", 3:"03_March", 4:"04_April",
    5:"05_May",     6:"06_June",     7:"07_July",  8:"08_August",
    9:"09_September",10:"10_October",11:"11_November",12:"12_December",
}


def fmt_timestamp(total_seconds):
    h = total_seconds // 3600
    m = (total_seconds % 3600) // 60
    s = total_seconds % 60
    return (f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}")


def generate_title(year, month, total_games, avg_rating, has_brilliants=False):
    month_str  = datetime(year, month, 1).strftime("%B %Y")
    brilliance = " | Brilliancies Included" if has_brilliants else ""
    return (
        f"Every Checkmate Win I Had in {month_str} | "
        f"{total_games} Games | Rated {avg_rating}{brilliance} | "
        f"Road to {NEXT_MILESTONE} ♟️"
    )[:100]


def generate_description(year, month, games_info, chapters_text, total_secs,
                          has_brilliants=False):
    month_str  = datetime(year, month, 1).strftime("%B %Y")
    n          = len(games_info)
    total_mins = total_secs // 60
    total_h    = total_mins // 60
    total_m    = total_mins % 60
    dur_str    = f"{total_h}h {total_m}m" if total_h else f"{total_m} minutes"

    # Win-type breakdown
    win_types = {}
    openings  = []
    blitz_count = rapid_count = bullet_count = 0
    avg_acc   = []
    for g in games_info:
        win_types[g.get("win_method", "Win")] = win_types.get(g.get("win_method","Win"),0) + 1
        op = g.get("opening", "")
        if op:
            openings.append(op)
        tc = g.get("time_ctrl", "").lower()
        if "blitz" in tc:   blitz_count  += 1
        elif "rapid" in tc: rapid_count  += 1
        elif "bullet" in tc: bullet_count += 1
        if g.get("accuracy"):
            avg_acc.append(g["accuracy"])

    win_breakdown = " · ".join(f"{v} by {k}" for k, v in win_types.items())
    top_openings  = list(dict.fromkeys(openings))[:5]
    openings_str  = "\n".join(f"  • {op}" for op in top_openings)
    acc_line      = (f"Average accuracy: {sum(avg_acc)/len(avg_acc):.1f}%"
                     if avg_acc else "")

    game_list = "\n".join(
        f"  Game {g['game_num']:02d}  vs {g['opp_name']:20s} ({g['opp_rating']})  "
        f"{g['win_method']} in {g['move_count']} moves  "
        f"{'as White' if g['side']=='white' else 'as Black'}"
        + (f"  [{g['opening']}]" if g.get("opening") else "")
        for g in games_info
    )

    brilliance_line = (
        "\nThis month includes brilliant moves — sacrificial or counter-intuitive "
        "plays that flipped the position.\n"
        if has_brilliants else ""
    )

    chapters_section = f"\n{chapters_text.strip()}\n" if chapters_text.strip() else ""

    desc = f"""Every single checkmate win I had in {month_str} — compiled into one video. {dur_str} of real chess at the {PREV_MILESTONE}–{NEXT_MILESTONE} rating level on chess.com.

No cherry-picking. No editing out the ugly games. Every qualifying win from the month, with move-quality annotations (Brilliant !! · Great ! · Best ✓ · Inaccuracy ?! · Mistake ? · Blunder ??).
{brilliance_line}
📊 STATS THIS MONTH
──────────────────────
Games:           {n}
Duration:        {dur_str}
Win breakdown:   {win_breakdown or str(n) + " wins"}
{acc_line}
Format mix:      {blitz_count} Blitz · {rapid_count} Rapid · {bullet_count} Bullet

🎯 OPENINGS FEATURED
──────────────────────
{openings_str or "  (various openings)"}

📋 ALL GAMES ({n} wins)
──────────────────────
{game_list}

⏱️ CHAPTERS
──────────────────────
{chapters_section}

──────────────────────
👤 ABOUT ME
I'm Abhishek — software developer, distance runner, and chess player who started at 42.
Currently rated ~{NEXT_MILESTONE - 80} on chess.com. Learning in public. Improving every month.

This channel documents the real grind from beginner to serious club player.
If you are learning chess as an adult or picked it up late — this is for you.

🔔 Subscribe and hit the bell so you never miss a monthly compilation.
{CHANNEL_HANDLE}  |  chess.com: {USERNAME}  |  {EMAIL}

──────────────────────
{CHANNEL} — Chess. Discipline. The Grind.
──────────────────────"""

    return desc[:4900]


def generate_hashtags(year, month, games_info):
    blitz_count = rapid_count = bullet_count = 0
    openings    = []
    for g in games_info:
        tc = g.get("time_ctrl", "").lower()
        if "blitz" in tc:    blitz_count  += 1
        elif "rapid" in tc:  rapid_count  += 1
        elif "bullet" in tc: bullet_count += 1
        if g.get("opening"):
            openings.append(g["opening"])

    month_str  = datetime(year, month, 1).strftime("%B").lower()
    month_year = datetime(year, month, 1).strftime("%B%Y").lower()

    # Core chess reach tags
    tags = [
        "#chess", "#chesscom", "#chessgame", "#chesscompilation",
        "#chessmoves", "#chessstrategy", "#chessanalysis",
        "#learnchess", "#chessimprovement", "#chessbeginners",
        "#adultthatplayschess", "#chessforbeginners", "#chesslessons",
        "#chessindian", "#chessindia", "#indianchess",
        f"#roadto{NEXT_MILESTONE}", "#chessprogress", "#chessjourney",
        "#checkmate", "#brilliantmove", "#chessmontage",
        f"#{month_str}chess", f"#{month_year}chess",
        "#thinkingathlete", "#indianthinkingathlete",
    ]

    # Time-control tags
    if blitz_count >= rapid_count and blitz_count >= bullet_count:
        tags.append("#blitzchess")
    if rapid_count > 0:
        tags.append("#rapidchess")
    if bullet_count > 0:
        tags.append("#bulletchess")

    # Opening-specific tags (up to 4)
    for op in list(dict.fromkeys(openings))[:4]:
        slug = "#" + re.sub(r"[^a-z0-9]", "", op.lower().split(":")[0].replace(" ", ""))
        if len(slug) > 4 and slug not in tags:
            tags.append(slug)

    # Deduplicate preserving order
    seen, out = set(), []
    for t in tags:
        if t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)

    return " ".join(out[:30])


def generate_tags_list(year, month, games_info):
    """Comma-separated tags for the YouTube API tags field (no # prefix)."""
    month_str = datetime(year, month, 1).strftime("%B %Y")
    openings  = list({g["opening"] for g in games_info if g.get("opening")})[:6]
    base = [
        "chess", "chess.com", "chess game", "chess compilation",
        "chess improvement", "learn chess", "chess for beginners",
        "chess India", "Indian chess", "adult chess player",
        "chess moves", "brilliant move", "chess strategy", "checkmate",
        f"road to {NEXT_MILESTONE}", "chess journey", "chess progress",
        f"chess {month_str}", "blitz chess", "chess analysis",
        "thinking athlete", "Indian thinking athlete",
    ] + openings
    return ", ".join(base)


def generate_thumbnail_copy(year, month, total_games, avg_rating):
    month_str = datetime(year, month, 1).strftime("%B").upper()
    return (
        f"Thumbnail suggestion:\n"
        f"  Main text:  '{month_str} WINS'\n"
        f"  Sub text:   '{total_games} CHECKMATES · RATED {avg_rating}'\n"
        f"  Style:      Dark background, amber/gold text, chess board or piece in BG\n"
        f"  Optional:   Add a frame from a brilliant move with the '!!' badge visible"
    )


def main():
    year  = int(os.environ.get("YEAR",  0) or 0)
    month = int(os.environ.get("MONTH", 0) or 0)

    parser = argparse.ArgumentParser()
    parser.add_argument("--year",  type=int)
    parser.add_argument("--month", type=int)
    args, _ = parser.parse_known_args()

    if args.year:  year  = args.year
    if args.month: month = args.month

    if not year or not month:
        print("❌ Provide --year and --month")
        sys.exit(1)

    out_dir       = os.path.join(OUTPUT_DIR, str(year), MONTH_NAMES[month])
    summary_path  = os.path.join(out_dir, "compilation_summary.json")
    chapters_path = os.path.join(out_dir, "chapters.txt")
    script_path   = os.path.join(out_dir, "script.txt")

    if not os.path.exists(summary_path):
        print(f"❌ {summary_path} not found — run longform_generate_video.py first!")
        sys.exit(1)

    with open(summary_path) as f:
        summary = json.load(f)

    chapters_text = ""
    if os.path.exists(chapters_path):
        with open(chapters_path) as f:
            chapters_text = f.read()

    games_info   = summary["games"]
    total_games  = summary["total_games"]
    total_secs   = summary["total_seconds"]
    avg_rating   = (sum(g["my_rating"] for g in games_info) // len(games_info)
                    if games_info else 0)
    has_brilliants = any(g.get("has_brilliant") for g in games_info)

    month_str = datetime(year, month, 1).strftime("%B %Y")
    print(f"📝 Generating YouTube metadata for {month_str} compilation...")
    print(f"   {total_games} games  |  {total_secs//60}m {total_secs%60}s  "
          f"|  avg rating: {avg_rating}"
          + ("  |  🌟 has brilliants" if has_brilliants else ""))

    title     = generate_title(year, month, total_games, avg_rating, has_brilliants)
    desc      = generate_description(year, month, games_info, chapters_text,
                                     total_secs, has_brilliants)
    hashtags  = generate_hashtags(year, month, games_info)
    tags_list = generate_tags_list(year, month, games_info)
    thumbnail = generate_thumbnail_copy(year, month, total_games, avg_rating)

    content = f"""{'='*68}
MONTHLY COMPILATION: {month_str}
Games: {total_games}  |  Duration: {total_secs//60}m {total_secs%60}s  |  Avg rating: {avg_rating}
Video: {summary.get('video_path', 'compilation.mp4')}
{'='*68}

🎬 YOUTUBE TITLE
{'─'*50}
{title}

📋 YOUTUBE DESCRIPTION  (copy everything below the line)
{'─'*50}
{desc}

#️⃣  HASHTAGS  (add at end of description)
{'─'*50}
{hashtags}

🏷️  YOUTUBE TAGS  (paste into Tags field in Studio)
{'─'*50}
{tags_list}

🖼️  THUMBNAIL COPY
{'─'*50}
{thumbnail}

📌 CHAPTERS  (already included in description above)
{'─'*50}
{chapters_text}
"""

    with open(script_path, "w") as f:
        f.write(content)

    print(f"\n✅ Script saved: {script_path}")
    print(f"   Title:    {title[:72]}…")
    print(f"   Hashtags: {len(hashtags.split())} tags")
    print(f"\n▶️  Next: python longform_upload_youtube.py --year {year} --month {month}")


if __name__ == "__main__":
    main()
