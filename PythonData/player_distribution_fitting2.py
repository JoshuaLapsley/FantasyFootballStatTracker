from __future__ import annotations
from numpyro.diagnostics import summary as numpyro_summary

import os

# Must be set BEFORE jax is imported/initialized anywhere, or it has no
# effect. This tells JAX to expose N logical CPU devices so MCMC chains
# actually run in parallel instead of falling back to sequential, which is
# what the "not enough devices" warning means.
os.environ.setdefault("XLA_FLAGS", "--xla_force_host_platform_device_count=4")

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd
import jax
import jax.numpy as jnp
import numpyro
import numpyro.distributions as dist
from numpyro.infer import MCMC, NUTS, init_to_median
from sklearn.preprocessing import StandardScaler

numpyro.set_host_device_count(4)
import pickle

def save_models(models: dict[str, "FittedPositionModel"], path: str = "fitted_models.pkl"):
    # mcmc objects don't pickle cleanly with their internal jax state in
    # some numpyro versions, so we save the posterior samples + dataset
    # instead of the raw MCMC object.
    to_save = {
        pos: {"dataset": model.dataset, "samples": model.posterior_samples()}
        for pos, model in models.items()
    }
    with open(path, "wb") as f:
        pickle.dump(to_save, f)

CACHE_PATH = "weekly_player_stats.parquet"


def load_weekly_data(
    years: list[int] = [2020, 2021, 2022, 2023, 2024],
    cache_path: str = CACHE_PATH,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """
    Loads nflverse weekly player stats, cached locally as parquet so you
    aren't re-downloading ~5 seasons of CSVs from GitHub on every run.
    Set force_refresh=True (or delete the cache file) to pull fresh data,
    e.g. once a new season's data is available. Requires `pyarrow`
    (`pip install pyarrow`) for parquet read/write.
    """
    if os.path.exists(cache_path) and not force_refresh:
        return pd.read_parquet(cache_path)

    dfs = []
    for year in years:
        url = (
            "https://github.com/nflverse/nflverse-data/releases/download/"
            f"player_stats/player_stats_{year}.csv"
        )
        dfs.append(pd.read_csv(url))

    weekly = pd.concat(dfs, ignore_index=True)
    weekly = weekly.rename(columns={"player_name": "name", "fantasy_points_ppr": "points"})

    # Only the four skill positions relevant to a fantasy lineup.
    weekly = weekly[weekly["position"].isin(["QB", "RB", "WR", "TE"])].copy()

    # nflverse only includes rows for players who recorded stats that
    # week, so every row here represents a game actually played.
    weekly["played"] = True
    weekly["week"] = weekly["week"].astype(int)
    weekly["season"] = weekly["season"].astype(int)
    weekly["points"] = weekly["points"].fillna(0.0).astype(float)

    weekly.to_parquet(cache_path, index=False)
    return weekly


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------
# These are the raw usage columns we'll turn into *rolling, lagged* covariates
# per position. Note we deliberately do NOT use the current week's own
# target_share / carries / etc. directly as covariates for that same week's
# points: those are outcomes of the same game, not something known beforehand.
# Using rolling averages of *prior* weeks instead means the fitted model can
# also be used prospectively (e.g. plugged into your Monte Carlo simulator to
# generate a distribution for an upcoming week), not just to describe the
# past. If you only care about retrospective description, you could use
# contemporaneous values instead, but the leakage tradeoff is worth being
# deliberate about.
POSITION_FEATURES: dict[str, list[str]] = {
    "QB": ["attempts", "passing_air_yards", "carries", "rushing_yards", "passing_epa"],
    "RB": ["carries", "targets", "target_share", "air_yards_share"],
    "WR": ["targets", "target_share", "air_yards_share", "receiving_air_yards"],
    "TE": ["targets", "target_share", "air_yards_share", "receiving_air_yards"],
}


def add_rolling_features(
    df: pd.DataFrame,
    feature_cols: list[str],
    window: int = 8,
) -> pd.DataFrame:
    """
    For each raw stat column, adds a `{col}_roll` column: the trailing mean
    over the previous `window` games, shifted so the current week's own
    value is excluded. First game(s) for a player will be NaN here (nothing
    to look back on yet) -- these get filled in `build_position_dataset`
    with the position-level average, which is itself a sensible "we know
    nothing about this player yet" prior for the covariates.
    """
    df = df.sort_values(["player_id", "season", "week"]).copy()
    for col in feature_cols:
        df[f"{col}_roll"] = df.groupby("player_id")[col].transform(
            lambda s: s.shift(1).rolling(window, min_periods=1).mean()
        )
    return df


@dataclass
class PositionDataset:
    """Everything the model needs for one position, plus enough metadata to
    map results back to real players and to featurize a new/future row."""

    position: str
    feature_cols: list[str]
    X: np.ndarray  # standardized covariates, shape (n_obs, n_features)
    y: np.ndarray  # fantasy points, shape (n_obs,)
    player_idx: np.ndarray  # integer player index per row, shape (n_obs,)
    player_id_to_idx: dict[str, int]
    idx_to_player_id: dict[int, str]
    idx_to_name: dict[int, str]
    scaler: StandardScaler
    feature_fill_values: pd.Series  # position-level means, used to fill NaNs


def build_position_dataset(df: pd.DataFrame, position: str, window: int = 8) -> PositionDataset:
    raw_cols = POSITION_FEATURES[position]
    roll_cols = [f"{c}_roll" for c in raw_cols]

    pos_df = df[df["position"] == position].copy()
    pos_df = add_rolling_features(pos_df, raw_cols, window=window)

    # Fill each rookie's/early-season NaNs with the position-wide average of
    # that rolling feature (computed once, from the whole dataset). This is
    # a deliberately simple default -- it just says "assume typical position
    # usage until we've actually observed this player."
    fill_values = pos_df[roll_cols].mean()
    pos_df[roll_cols] = pos_df[roll_cols].fillna(fill_values)

    pos_df = pos_df.dropna(subset=["points"]).reset_index(drop=True)

    # Stable per-position player indexing.
    player_ids = pos_df["player_id"].astype(str)
    unique_ids = sorted(player_ids.unique())
    player_id_to_idx = {pid: i for i, pid in enumerate(unique_ids)}
    idx_to_player_id = {i: pid for pid, i in player_id_to_idx.items()}
    idx_to_name = (
        pos_df.groupby(player_ids)["player_display_name"].first().to_dict()
    )
    idx_to_name = {player_id_to_idx[pid]: name for pid, name in idx_to_name.items()}

    player_idx = player_ids.map(player_id_to_idx).to_numpy()

    scaler = StandardScaler()
    X = scaler.fit_transform(pos_df[roll_cols].to_numpy())
    y = pos_df["points"].to_numpy()

    return PositionDataset(
        position=position,
        feature_cols=roll_cols,
        X=X,
        y=y,
        player_idx=player_idx,
        player_id_to_idx=player_id_to_idx,
        idx_to_player_id=idx_to_player_id,
        idx_to_name=idx_to_name,
        scaler=scaler,
        feature_fill_values=fill_values,
    )

def mcmc_summary_to_df(model: "FittedPositionModel", prob: float = 0.9) -> pd.DataFrame:
    """
    Same numbers as mcmc.print_summary(), as a tidy DataFrame instead of a
    terminal table. Vector sites (beta_mu, z_mu, ...) get expanded into one
    row per element, e.g. 'beta_mu[0]', matching the printed output. For
    z_mu/z_sigma specifically, also attaches the real player name/id so you
    don't have to manually cross-reference the index.
    """
    samples = model.mcmc.get_samples(group_by_chain=True)
    stats = numpyro_summary(samples, prob=prob)

    lower_pct = f"{(1 - prob) / 2 * 100:.1f}%"
    upper_pct = f"{(1 + prob) / 2 * 100:.1f}%"

    rows = []
    for name, site_stats in stats.items():
        if name == "nu":  # deterministic; drop to match exclude_deterministic=True
            continue
        mean_arr = np.asarray(site_stats["mean"])
        for idx in np.ndindex(mean_arr.shape) if mean_arr.shape else [()]:
            idx_str = ",".join(map(str, idx))
            row = {
                "parameter": f"{name}[{idx_str}]" if idx_str else name,
                "mean": float(np.asarray(site_stats["mean"])[idx]),
                "std": float(np.asarray(site_stats["std"])[idx]),
                "median": float(np.asarray(site_stats["median"])[idx]),
                lower_pct: float(np.asarray(site_stats[lower_pct])[idx]),
                upper_pct: float(np.asarray(site_stats[upper_pct])[idx]),
                "n_eff": float(np.asarray(site_stats["n_eff"])[idx]),
                "r_hat": float(np.asarray(site_stats["r_hat"])[idx]),
            }
            if name in ("z_mu", "z_sigma") and idx:
                player_i = idx[0]
                row["player_id"] = model.dataset.idx_to_player_id.get(player_i)
                row["player_name"] = model.dataset.idx_to_name.get(player_i)
            rows.append(row)

    return pd.DataFrame(rows)
# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
# Covariate-augmented hierarchical model, one fit per position:
#
#   mu_i,t    = mu_pos          + X_i,t @ beta_mu    + b_mu[i]
#   sigma_i,t = exp(log_sigma_pos + X_i,t @ beta_sigma + b_sigma[i])
#   y_i,t ~ StudentT(nu, mu_i,t, sigma_i,t)
#
# b_mu[i], b_sigma[i] are player-specific random intercepts, drawn from
# Normal(0, tau_mu) / Normal(0, tau_sigma) respectively -- this is exactly
# the partial-pooling layer: tau_mu/tau_sigma (learned from the data, shared
# across all players at a position) control how much a player's own data
# is allowed to pull him away from what his covariates alone would predict.
# Players with few games contribute a weak likelihood signal, so their
# posterior b_i stays close to 0 (i.e. "no meaningfully different from what
# his usage stats already suggest"); players with many games get to move
# further per unit of z if their own scores actually warrant it.
#
# Student-t (rather than Normal) is used for the likelihood to get fatter
# tails for free -- fantasy scoring has real boom weeks -- with a single
# shared degrees-of-freedom parameter `nu` per position. If you find
# residuals are still meaningfully skewed (not just fat-tailed) after
# fitting this, that's the signal to move to a Skew-Normal or an explicit
# bust/normal-week mixture next.
def hierarchical_model(X: jnp.ndarray, player_idx: jnp.ndarray, n_players: int, y: Optional[jnp.ndarray] = None):
    n_features = X.shape[1]

    mu_pos = numpyro.sample("mu_pos", dist.Normal(10.0, 10.0))
    beta_mu = numpyro.sample("beta_mu", dist.Normal(0.0, 1.0).expand([n_features]).to_event(1))
    tau_mu = numpyro.sample("tau_mu", dist.HalfNormal(5.0))

    log_sigma_pos = numpyro.sample("log_sigma_pos", dist.Normal(np.log(7.0), 1.0))
    beta_sigma = numpyro.sample("beta_sigma", dist.Normal(0.0, 0.5).expand([n_features]).to_event(1))
    tau_sigma = numpyro.sample("tau_sigma", dist.HalfNormal(1.0))

    # Student-t degrees of freedom, reparameterized as 1 + Exponential(1/29)
    # (the standard "robust regression" prior recommended in the Stan user
    # guide) rather than a plain Gamma. A plain Gamma(6, 0.5) puts real prior
    # mass near very small nu (close to Cauchy), and that region of the
    # posterior has extremely sharp curvature -- it's the likely cause of
    # the tiny step sizes / max-tree-depth chains you saw. This
    # reparameterization keeps nu >= 1 and still lets the data pull it low
    # if the position genuinely has fat tails, without the sampler having to
    # navigate that stiff region by default.
    nu_offset = numpyro.sample("nu_offset", dist.Exponential(1.0 / 29.0))
    nu = numpyro.deterministic("nu", 1.0 + nu_offset)

    # Non-centered parameterization (z * tau instead of directly sampling
    # Normal(0, tau)) -- standard trick that makes NUTS sample much more
    # efficiently for hierarchical models, especially with many low-data
    # players where tau and the b_i's would otherwise be tightly coupled.
    with numpyro.plate("players", n_players):
        z_mu = numpyro.sample("z_mu", dist.Normal(0.0, 1.0))
        z_sigma = numpyro.sample("z_sigma", dist.Normal(0.0, 1.0))

    b_mu = z_mu * tau_mu
    b_sigma = z_sigma * tau_sigma

    mu = mu_pos + X @ beta_mu + b_mu[player_idx]
    sigma = jnp.exp(log_sigma_pos + X @ beta_sigma + b_sigma[player_idx])

    with numpyro.plate("obs", X.shape[0]):
        numpyro.sample("y", dist.StudentT(nu, mu, sigma), obs=y)


@dataclass
class FittedPositionModel:
    dataset: PositionDataset
    mcmc: MCMC

    def posterior_samples(self) -> dict[str, np.ndarray]:
        return self.mcmc.get_samples()

    def player_week_distribution(
        self,
        player_id: str,
        feature_row: Optional[np.ndarray] = None,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Returns posterior draws of (mu, sigma, nu) for one player-week,
        given a raw (unstandardized) feature row in the same order as
        `dataset.feature_cols` (e.g. that player's most recent rolling
        stats, for a "what's his distribution going into next week" query).
        If `feature_row` is omitted, uses the position-level average
        (dataset.feature_fill_values), i.e. "a typical week at this
        position with no player-specific usage information."

        For a player_id NOT seen in training (e.g. a rookie who hasn't
        played yet), the random intercept b_i is drawn fresh from
        Normal(0, tau) per posterior sample -- this correctly reflects
        "we don't know this player's personal deviation yet, only how much
        players at this position typically deviate."
        """
        samples = self.posterior_samples()
        n_draws = samples["mu_pos"].shape[0]

        if feature_row is None:
            feature_row = self.dataset.feature_fill_values.to_numpy()
        x_std = self.dataset.scaler.transform(feature_row.reshape(1, -1))[0]

        mu_pos = samples["mu_pos"]
        beta_mu = samples["beta_mu"]
        tau_mu = samples["tau_mu"]
        log_sigma_pos = samples["log_sigma_pos"]
        beta_sigma = samples["beta_sigma"]
        tau_sigma = samples["tau_sigma"]
        nu = samples["nu"]

        idx = self.dataset.player_id_to_idx.get(player_id)
        if idx is not None:
            b_mu = samples["z_mu"][:, idx] * tau_mu
            b_sigma = samples["z_sigma"][:, idx] * tau_sigma
        else:
            rng = np.random.default_rng(hash(player_id) % (2**32))
            b_mu = rng.normal(size=n_draws) * tau_mu
            b_sigma = rng.normal(size=n_draws) * tau_sigma

        mu = mu_pos + beta_mu @ x_std + b_mu
        sigma = np.exp(log_sigma_pos + beta_sigma @ x_std + b_sigma)
        return mu, sigma, nu

    def sample_points(
        self,
        player_id: str,
        feature_row: Optional[np.ndarray] = None,
        n_draws: int = 1,
        seed: int = 0,
    ) -> np.ndarray:
        """
        Draws simulated fantasy point totals for one player-week. Each draw
        first picks a random posterior sample of (mu, sigma, nu) -- so
        parameter uncertainty about *this player's own distribution* is
        propagated, not just the distribution's own randomness -- and then
        samples a Student-t point total from it. This is what you'd call
        from inside the Monte Carlo season simulator.
        """
        mu, sigma, nu = self.player_week_distribution(player_id, feature_row)
        rng = np.random.default_rng(seed)
        draw_idx = rng.integers(0, len(mu), size=n_draws)
        t_samples = stats_t_rvs(nu[draw_idx], rng)
        return mu[draw_idx] + sigma[draw_idx] * t_samples


def stats_t_rvs(nu: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Standard Student-t draws, one per element of nu (vectorized df)."""
    from scipy import stats

    return stats.t.rvs(df=nu, random_state=rng)


def fit_position_model(
    dataset: PositionDataset,
    num_warmup: int = 1000,
    num_samples: int = 1000,
    num_chains: int = 4,
    seed: int = 0,
) -> FittedPositionModel:
    kernel = NUTS(
        hierarchical_model,
        init_strategy=init_to_median,
        max_tree_depth=10,  # caps worst-case steps/sample at 2^10 - 1 = 1023,
                            # so a stiff chain slows down rather than stalling
    )
    mcmc = MCMC(
        kernel,
        num_warmup=num_warmup,
        num_samples=num_samples,
        num_chains=num_chains,
        progress_bar=True,
    )
    mcmc.run(
        jax.random.PRNGKey(seed),
        X=jnp.asarray(dataset.X),
        player_idx=jnp.asarray(dataset.player_idx),
        n_players=len(dataset.player_id_to_idx),
        y=jnp.asarray(dataset.y),
    )
    return FittedPositionModel(dataset=dataset, mcmc=mcmc)


def fit_all_positions(
    df: pd.DataFrame,
    positions: list[str] = ["QB", "RB", "WR", "TE"],
    window: int = 8,
    **fit_kwargs,
) -> dict[str, FittedPositionModel]:
    fitted = {}
    for pos in positions:
        dataset = build_position_dataset(df, pos, window=window)
        fitted[pos] = fit_position_model(dataset, **fit_kwargs)
    return fitted


if __name__ == "__main__":
    weekly = load_weekly_data()
    models = fit_all_positions(weekly, num_warmup=500, num_samples=500, num_chains=2)

    for pos, model in models.items():
        df_summary = mcmc_summary_to_df(model)
        df_summary.to_csv(f"{pos}_summary.csv", index=False)
        print(f"Wrote {pos}_summary.csv")

    save_models(models)
    print("Wrote fitted_models.pkl")