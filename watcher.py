import requests, json, os, time
from datetime import datetime, timedelta, timezone

USERNAME    = os.environ.get("CHESS_USERNAME", "abhi15041984")
HEADERS     = {"User-Agent": "TheThinkingAthlete/1.0"}
OUTPUT_FILE = "won_games.json"
ABANDONMENT = {"abandoned", "timeout", "timevsinsufficient"}

def get_my_side(g):
    return "white" if g["white"]["username"].lower() == USERNAME.lower() else "black"

def is_real_win(g):
    s = get_my_side(g)
    opp = "black" if s == "white" else "white"
    return g[s]["result"] == "win" and g[opp]["result"] not in ABANDONMENT

def main():
    now = datetime.now(timezone.utc)
    cutoff_ts = (now - timedelta(hours=24)).timestamp()
    archives = requests.get(f"https://api.chess.com/pub/player/{USERNAME}/games/archives", headers=HEADERS).json()["archives"]
    all_games = []
    for url in archives[-2:]:
        games = requests.get(url, headers=HEADERS, timeout=15).json().get("games", [])
        all_games.extend(games)
        time.sleep(0.5)
    wins = sorted([g for g in all_games if g.get("end_time",0) >= cutoff_ts and is_real_win(g)],
                  key=lambda g: g.get("end_time",0), reverse=True)
    print(f"✅ Found {len(wins)} real wins in last 24h")
    json.dump(wins, open(OUTPUT_FILE,"w"), indent=2)

if __name__ == "__main__":
    main()
