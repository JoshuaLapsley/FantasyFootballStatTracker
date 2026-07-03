from pathlib import Path
import json
import re
from collections import defaultdict
import numpy as np
import matplotlib.pyplot as plt

BASE_DIR = Path("league_stats_output")

output_dir = (
    BASE_DIR / ".." / ".." / "Website" / "girderma-gridiron-website" / "src" / "histograms"
).resolve()
output_dir.mkdir(parents=True, exist_ok=True)

week_re = re.compile(r"week_(\d+)")

# =========================================================
# TEAM -> NICKNAME MAP
# =========================================================
TEAM_TO_NICKNAME = {
    "Ozzy Stick": "Ben", "Mahomes Alone": "Josh_Rubik", "Tsuga\u2019s Tuck Shop": "Caleb", "Revy\u2019s Konstruction": "Connor", "Supernova\u2019s Studs": "Gavin_Brodie", "Spirally Things": "Levi", "Hunter\u2019s Hunters": "Hunter", "Omaha Beach Real Estate": "Andrew", "Flows Aggressive Insurance": "Zach", "Go With The Flow": "Zach", "Wicked Wah-Bams": "Nate", "The Sage's Playmakers": "Josh_Sage", "Sparty's Sigmas": "Jackson", "For Pitts and Giggles": "Zach", "The Hunters": "Hunter", "Lawrence & Order": "Andrew", "Oscorps Buns": "Ben", "Bumpin Brasnos": "Ben", "Room 40": "Josh_Rubik", "No Punts Intented": "Josh_Rubik", "Hungry Hungry Hokk": "Nate", "Deej-lanta Falcons": "DJ", "Pad D's": "Sam_Paddy", "Girder\u2019s Grippers": "Sam_Girder", "Ma\u00eetre Magic": "Levi", "Bumpin Brasnos": "Levi"
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

            pf = stats.get("points_for")
            pa = stats.get("points_against")

            if pf is None or pa is None:
                continue

            points_for[nickname].append(pf)
            points_against[nickname].append(pa)

print(f"[DEBUG] Groups found: {len(points_for)}")

# =========================================================
# COMMON BINS
# =========================================================
all_pf = np.concatenate([np.array(v) for v in points_for.values()])
all_pa = np.concatenate([np.array(v) for v in points_against.values()])

global_min = min(all_pf.min(), all_pa.min())
global_max = max(all_pf.max(), all_pa.max())

bins = np.arange(
    (global_min // 5) * 5,
    ((global_max // 5) + 2) * 5,
    5,
)

bin_centers = (bins[:-1] + bins[1:]) / 2

# =========================================================
# LEAGUE AVERAGE HISTOGRAMS
# =========================================================
pf_counts, _ = np.histogram(all_pf, bins=bins)
pa_counts, _ = np.histogram(all_pa, bins=bins)

pf_proportions = pf_counts / pf_counts.sum()
pa_proportions = pa_counts / pa_counts.sum()


# =========================================================
# PLOTTING
# =========================================================
def safe_filename(name):
    return "".join(c if c.isalnum() or c in " _-" else "_" for c in name).strip()


def plot_hist(values, avg_line, title, path):
    if not values:
        return

    values = np.array(values)

    plt.figure(figsize=(8, 5))

    plt.hist(values, bins=bins, edgecolor="black")

    plt.plot(
        bin_centers,
        avg_line,
        color="red",
        linewidth=2.5,
        marker="o",
        markersize=4,
        label="League Average",
    )

    plt.title(title)
    plt.xlabel("Points")
    plt.ylabel("Frequency")
    plt.legend()

    plt.tight_layout()
    plt.savefig(path, dpi=300)
    plt.close()


# =========================================================
# OUTPUT
# =========================================================
for nickname in points_for:

    fname = safe_filename(nickname)

    # Scale the league-average histogram to the number of games this manager played
    expected_pf = pf_proportions * len(points_for[nickname])
    expected_pa = pa_proportions * len(points_against[nickname])

    plot_hist(
        points_for[nickname],
        expected_pf,
        f"{nickname} - Points For (Weeks 1–14, All Seasons)",
        output_dir / f"{fname}_points_for.png",
    )

    plot_hist(
        points_against[nickname],
        expected_pa,
        f"{nickname} - Points Against (Weeks 1–14, All Seasons)",
        output_dir / f"{fname}_points_against.png",
    )