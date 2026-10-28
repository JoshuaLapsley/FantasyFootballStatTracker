"""
One-off analysis: how normal are individual players' weekly fantasy
point totals, really? This directly checks the distributional
assumption behind CurrentSeason/CalculateWAR.py's WAR formula (which
treats a player-week's contribution as feeding into a Normal(mu,
sigma=33*sqrt(2)) margin model).

Uses nflverse weekly player stats for the 2023, 2024, and 2025 regular
seasons, restricted to QB/RB/WR/TE (the positions WAR is computed for).
2023-2024 come from the existing local cache
(weekly_player_stats.parquet, built by player_distribution_fitting*.py
from the OLD "player_stats" nflverse release). That release is
deprecated as of 2025-08-01 and has no 2025 data, so 2025 is pulled
separately from the new "stats_player" release
(stats_player_week_2025.csv), which uses a slightly different column
set but the same fantasy_points_ppr field.

Does NOT modify weekly_player_stats.parquet -- writes its own separate
cache (nflverse_2025_weekly_cache.csv) so it doesn't disturb whatever
player_distribution_fitting*.py already depends on.

For each position, reports:
  - skewness, excess kurtosis (0 = normal for both)
  - Shapiro-Wilk test (on a capped random sample -- it's not valid/
    reliable much above a few thousand rows) and D'Agostino-Pearson
    test (chi2-based, fine at full sample size) for normality
  - % of games with 0 points (a normal distribution has no special
    mass at any single value, so a big spike at 0 is itself evidence
    against normality, independent of the moment-based tests)
  - a histogram with a fitted normal curve overlaid, saved per position
"""

import os

import numpy as np
import pandas as pd
from scipy import stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OLD_CACHE_PATH = os.path.join(SCRIPT_DIR, "weekly_player_stats.parquet")
NEW_2025_CACHE_PATH = os.path.join(SCRIPT_DIR, "nflverse_2025_weekly_cache.csv")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "normality_check_output")

POSITIONS = ["QB", "RB", "WR", "TE"]


def load_2023_2024() -> pd.DataFrame:
    """From the existing local parquet cache (old 'player_stats'
    nflverse release), which already covers 2020-2024. Filter down to
    2023-2024 only, regular season."""
    df = pd.read_parquet(OLD_CACHE_PATH)
    df = df[df["season"].isin([2023, 2024])]
    df = df[df["season_type"] == "REG"]
    return df[["player_id", "name", "position", "season", "week", "points"]].rename(
        columns={"name": "player_display_name"}
    )


def load_2025(force_refresh: bool = False) -> pd.DataFrame:
    """
    From the new 'stats_player' nflverse release (the old 'player_stats'
    release has no 2025 data -- deprecated 2025-08-01). Cached locally
    as its own CSV, separate from weekly_player_stats.parquet.
    """
    if os.path.exists(NEW_2025_CACHE_PATH) and not force_refresh:
        df = pd.read_csv(NEW_2025_CACHE_PATH)
    else:
        url = (
            "https://github.com/nflverse/nflverse-data/releases/download/"
            "stats_player/stats_player_week_2025.csv"
        )
        df = pd.read_csv(url, low_memory=False)
        df.to_csv(NEW_2025_CACHE_PATH, index=False)

    df = df[df["season_type"] == "REG"]
    df = df[df["position"].isin(POSITIONS)].copy()
    df["points"] = df["fantasy_points_ppr"].fillna(0.0).astype(float)
    df["season"] = df["season"].astype(int)
    df["week"] = df["week"].astype(int)
    return df[["player_id", "player_display_name", "position", "season", "week", "points"]]


def load_all_seasons() -> pd.DataFrame:
    df_23_24 = load_2023_2024()
    df_25 = load_2025()
    combined = pd.concat([df_23_24, df_25], ignore_index=True)
    return combined


def analyze_position(df: pd.DataFrame, position: str) -> dict:
    values = df.loc[df["position"] == position, "points"].dropna().to_numpy()
    n = len(values)

    skewness = stats.skew(values)
    excess_kurtosis = stats.kurtosis(values)  # Fisher definition, 0 = normal
    zero_pct = float(np.mean(values == 0.0)) * 100
    mean, sd = float(np.mean(values)), float(np.std(values))

    # Shapiro-Wilk is not reliable/valid for very large n (scipy caps
    # around 5000 and significance becomes trivially small anyway at
    # this scale) -- run it on a fixed random subsample for a readable
    # p-value, in addition to the full-sample moment-based checks.
    rng = np.random.default_rng(42)
    sample_size = min(5000, n)
    sample = rng.choice(values, size=sample_size, replace=False)
    shapiro_stat, shapiro_p = stats.shapiro(sample)

    # D'Agostino-Pearson omnibus test (skewness + kurtosis combined into
    # a chi2 statistic) -- valid at full sample size, unlike Shapiro-Wilk.
    dagostino_stat, dagostino_p = stats.normaltest(values)

    return {
        "position": position,
        "n": n,
        "mean": mean,
        "sd": sd,
        "skewness": skewness,
        "excess_kurtosis": excess_kurtosis,
        "zero_pct": zero_pct,
        "shapiro_n": sample_size,
        "shapiro_stat": shapiro_stat,
        "shapiro_p": shapiro_p,
        "dagostino_stat": dagostino_stat,
        "dagostino_p": dagostino_p,
        "values": values,
    }


def plot_position(result: dict, output_path: str) -> None:
    values = result["values"]
    mean, sd = result["mean"], result["sd"]

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(values, bins=60, density=True, color="#60A5FA", alpha=0.75, edgecolor="white",
            label="Actual weekly points")

    x = np.linspace(values.min(), values.max(), 400)
    ax.plot(x, stats.norm.pdf(x, mean, sd), color="#DC2626", linewidth=2,
            label=f"Normal(\u03bc={mean:.1f}, \u03c3={sd:.1f}) fit")

    ax.set_title(
        f"{result['position']} weekly PPR points, 2023-2025 (n={result['n']:,})\n"
        f"skew={result['skewness']:.2f}  excess kurtosis={result['excess_kurtosis']:.2f}  "
        f"zero-score weeks={result['zero_pct']:.1f}%"
    )
    ax.set_xlabel("Fantasy points (PPR)")
    ax.set_ylabel("Density")
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    df = load_all_seasons()
    print(f"Loaded {len(df):,} player-weeks across seasons {sorted(df['season'].unique())}\n")

    results = []
    for pos in POSITIONS:
        result = analyze_position(df, pos)
        results.append(result)

        img_path = os.path.join(OUTPUT_DIR, f"{pos}_distribution.png")
        plot_position(result, img_path)

        print(f"=== {pos} (n={result['n']:,}) ===")
        print(f"  mean={result['mean']:.2f}  sd={result['sd']:.2f}")
        print(f"  skewness={result['skewness']:.3f}  (0 = symmetric like a normal)")
        print(f"  excess kurtosis={result['excess_kurtosis']:.3f}  (0 = normal-tailed; "
              f">0 = fatter tails/more extreme outliers than normal)")
        print(f"  zero-point weeks: {result['zero_pct']:.1f}%")
        print(f"  Shapiro-Wilk (n={result['shapiro_n']:,} subsample): "
              f"stat={result['shapiro_stat']:.4f}  p={result['shapiro_p']:.2e}")
        print(f"  D'Agostino-Pearson (full sample): "
              f"stat={result['dagostino_stat']:.1f}  p={result['dagostino_p']:.2e}")
        print(f"  Saved -> {img_path}\n")

    print("=" * 72)
    print("Summary (all tests): p < 0.05 rejects normality. Given how large n is\n"
          "here, even tiny/practically-irrelevant deviations from normal will\n"
          "produce a significant p-value -- skewness/kurtosis magnitudes and the\n"
          "histograms are more informative than the p-values themselves.")
    print("=" * 72)
    for r in results:
        verdict = "REJECT normality" if r["dagostino_p"] < 0.05 else "fail to reject normality"
        print(f"  {r['position']:<4} skew={r['skewness']:+.2f}  "
              f"exkurt={r['excess_kurtosis']:+.2f}  zero%={r['zero_pct']:5.1f}%  "
              f"D'Agostino p={r['dagostino_p']:.2e}  -> {verdict}")


if __name__ == "__main__":
    main()
