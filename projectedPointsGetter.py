import requests
from bs4 import BeautifulSoup
import json
import time

FANTASYPROS_URLS = {
    "QB": "https://www.fantasypros.com/nfl/projections/qb.php",
    "RB": "https://www.fantasypros.com/nfl/projections/rb.php",
    "WR": "https://www.fantasypros.com/nfl/projections/wr.php",
    "TE": "https://www.fantasypros.com/nfl/projections/te.php",
    "K":  "https://www.fantasypros.com/nfl/projections/k.php",
    "DST": "https://www.fantasypros.com/nfl/projections/dst.php"
}

def fetch_fantasypros_week(week, scoring="ppr"):
    """
    Fetch projections from FantasyPros for all positions for a given week.
    For RB, WR, TE, adds projected receptions to PPR score.
    Returns:
        dict: { player_name: {week: projected_points} }
    """
    all_players = {}

    for pos, url in FANTASYPROS_URLS.items():
        print(f"Fetching {pos} projections for week {week}...")

        full_url = f"{url}?week={week}&scoring={scoring}&range=week"
        r = requests.get(full_url, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(r.text, "html.parser")
        table = soup.find("table", {"class": "table"})

        if table is None:
            print(f"Warning: No table found for {pos}")
            continue

        headers = [th.text.strip().lower() for th in table.find("thead").find_all("th")]

        for row in table.find("tbody").find_all("tr"):
            cols = row.find_all("td")
            if len(cols) < 2:
                continue

            name = cols[0].text.strip()
            try:
                pts = float(cols[headers.index("fantasy points")].text.strip())
            except:
                pts = 0.0

            # Add projected receptions for PPR scoring
            if pos in ["RB", "WR", "TE"]:
                try:
                    rec_index = headers.index("rec")  # column for receptions
                    rec = float(cols[rec_index].text.strip())
                except:
                    rec = 0.0
                pts += rec  # add receptions to points

            if name not in all_players:
                all_players[name] = {}

            all_players[name][str(week)] = pts

        time.sleep(1)  # avoid rate limiting

    return all_players

def fetch_all_weeks(max_week=17):
    """
    Fetches weekly projections for all weeks and merges them into a dict.
    """
    final = {}

    for week in range(1, max_week + 1):
        week_data = fetch_fantasypros_week(week)
        for player, week_proj in week_data.items():
            if player not in final:
                final[player] = {}
            final[player].update(week_proj)

    return final

if __name__ == "__main__":
    max_week = 17
    print("Fetching ALL weekly projections with PPR scoring...")

    data = fetch_all_weeks(max_week=max_week)

    with open("fantasypros_projections_ppr.json", "w") as f:
        json.dump(data, f, indent=4)

    print("Saved → fantasypros_projections_ppr.json")
