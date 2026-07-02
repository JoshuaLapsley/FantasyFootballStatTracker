from pathlib import Path
import json
import re
from collections import defaultdict
import numpy as np
import matplotlib.pyplot as plt

BASE_DIR = Path("league_stats_output")

output_dir = (BASE_DIR / ".." / ".." / "Website" / "girderma-gridiron-website" / "src" / "histograms").resolve()
output_dir.mkdir(parents=True, exist_ok=True)

week_re = re.compile(r"week_(\d+)")

# =========================================================
# TEAM -> NICKNAME MAP (FILL THIS IN)
# =========================================================
TEAM_TO_NICKNAME = {
    "Ozzy Stick": "Ben", "Mahomes Alone": "Josh_Rubik", "Tsuga\u2019s Tuck Shop": "Caleb", "Revy\u2019s Konstruction": "Connor", "Supernova\u2019s Studs": "Gavin Brodie", "Spirally Things": "Levi", "Hunter\u2019s Hunters": "Hunter", "Omaha Beach Real Estate": "Andrew", "Flows Aggressive Insurance": "Zach", "Go With The Flow": "Zach", "Wicked Wah-Bams": "Nate", "The Sage's Playmakers": "Josh_Sage", "Sparty's Sigmas": "Jackson", "For Pitts and Giggles": "Zach", "The Hunters": "Hunter", "Lawrence & Order": "Andrew", "Oscorps Buns": "Ben", "Bumpin Brasnos": "Ben", "Room 40": "Josh_Rubik", "No Punts Intented": "Josh_Rubik", "Hungry Hungry Hokk": "Nate", "Deej-lanta Falcons": "DJ", "Pad D's": "Sam_Paddy", "Girder\u2019s Grippers": "Sam_Girder", "Ma\u00eetre Magic": "Levi", "Bumpin Brasnos": "Levi"
}

def resolve_nickname(team_name):
    return TEAM_TO_NICKNAME.get(team_name, team_name)

# pooled stats per nickname
points_for = defaultdict(list)
points_against = defaultdict(list)

# =========================================================
# LOAD DATA
# =========================================================
for season_dir in BASE_DIR.iterdir():
    if not season_dir.is_dir():
        continue

    file_path = season_dir / "weekly_points.json"
    if not file_path.exists():
        continue

    print(f"[DEBUG] Loading {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for team_name, weeks in data.items():

        nickname = resolve_nickname(team_name)

        for week, stats in weeks.items():

            m = week_re.match(week)
            if not m:
                continue

            week_num = int(m.group(1))
            if week_num > 14:
                continue

            # IMPORTANT: no team_name lookup here
            pf = stats.get("points_for")
            pa = stats.get("points_against")

            if pf is None or pa is None:
                continue

            points_for[nickname].append(pf)
            points_against[nickname].append(pa)

print(f"[DEBUG] Groups found: {len(points_for)}")

# =========================================================
# PLOTTING
# =========================================================
def safe_filename(name):
    return "".join(c if c.isalnum() or c in " _-" else "_" for c in name).strip()

def plot_hist(values, title, path):
    if not values:
        return

    values = np.array(values)

    bins = np.arange(
        (values.min() // 5) * 5,
        ((values.max() // 5) + 2) * 5,
        5
    )

    plt.figure()
    plt.hist(values, bins=bins, edgecolor="black")
    plt.title(title)
    plt.xlabel("Points")
    plt.ylabel("Frequency")
    plt.tight_layout()
    plt.savefig(path)
    plt.close()

# =========================================================
# OUTPUT
# =========================================================
for nickname in points_for:

    fname = safe_filename(nickname)

    plot_hist(
        points_for[nickname],
        f"{nickname} - Points For (Weeks 1–14, All Seasons)",
        output_dir / f"{fname}_points_for.png"
    )

    plot_hist(
        points_against[nickname],
        f"{nickname} - Points Against (Weeks 1–14, All Seasons)",
        output_dir / f"{fname}_points_against.png"
    )