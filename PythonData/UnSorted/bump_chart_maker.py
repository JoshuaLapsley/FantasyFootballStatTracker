import json
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt

# ----------------------------
# Load data
# ----------------------------

BASE_DIR = Path(__file__).resolve().parent
json_path = BASE_DIR / "league_stats_output" / "bump_chart_long.json"

with open(json_path, "r") as f:
    data = json.load(f)

df = pd.DataFrame(data)

# ----------------------------
# Output directory
# Assumes this script is somewhere such that:
# ../Website/src
# is the desired destination.
# ----------------------------
output_dir = (BASE_DIR / ".." / "Website" / "girderma-gridiron-website" / "src").resolve()
output_dir.mkdir(parents=True, exist_ok=True)

# ----------------------------
# Create one chart per season
# ----------------------------
for season in sorted(df["season"].unique()):

    season_df = df[df["season"] == season]

    rankings = (
        season_df
        .pivot(index="week", columns="team", values="rank")
        .sort_index()
    )

    fig, ax = plt.subplots(figsize=(16, 10))

    for team in rankings.columns:
        ax.plot(
            rankings.index,
            rankings[team],
            marker="o",
            linewidth=2,
        )

        ax.text(
            rankings.index.max() + 0.25,
            rankings.loc[rankings.index.max(), team],
            team,
            fontsize=9,
            va="center"
        )

    ax.invert_yaxis()

    ax.set_title(f"{season} Fantasy League Standings", fontsize=18)
    ax.set_xlabel("Week")
    ax.set_ylabel("Rank")

    ax.set_xticks(rankings.index)
    ax.set_yticks(range(1, len(rankings.columns) + 1))

    ax.grid(axis="y", linestyle="--", alpha=0.3)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.set_xlim(rankings.index.min(), rankings.index.max() + 2)

    plt.tight_layout()

    # Save as JPEG
    outfile = output_dir / f"bump_chart_{season}.jpg"
    fig.savefig(outfile, format="jpeg", dpi=300, bbox_inches="tight")
    plt.close(fig)

    print(f"Saved {outfile}")