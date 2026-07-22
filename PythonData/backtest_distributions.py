from player_distribution_fitting2 import (
    FittedPositionModel,
    PositionDataset,
    hierarchical_model,
    stats_t_rvs,
)
from typing import Optional
import numpy as np
import jax
import jax.numpy as jnp
from numpyro.infer import Predictive
import matplotlib.pyplot as plt
import pandas as pd
import pickle


def run_posterior_predictive(model: FittedPositionModel, seed: int = 0) -> np.ndarray:
    dataset = model.dataset
    samples = model.posterior_samples()
    predictive = Predictive(hierarchical_model, samples, return_sites=["y"])
    rng_key = jax.random.PRNGKey(seed)
    ppc = predictive(
        rng_key,
        X=jnp.asarray(dataset.X),
        player_idx=jnp.asarray(dataset.player_idx),
        n_players=len(dataset.player_id_to_idx),
    )
    return np.asarray(ppc["y"])


def ppc_summary_table(model: FittedPositionModel, ppc_y: np.ndarray) -> pd.DataFrame:
    y_real = model.dataset.y

    def stats_of(y):
        return {
            "mean": np.mean(y),
            "std": np.std(y),
            "pct_under_5": np.mean(y < 5),
            "pct_over_25": np.mean(y > 25),
            "pct_zero": np.mean(y == 0),
            "max": np.max(y),
        }

    real_stats = stats_of(y_real)
    sim_stats = {k: [] for k in real_stats}
    for row in ppc_y:
        s = stats_of(row)
        for k, v in s.items():
            sim_stats[k].append(v)

    rows = []
    for k, real_val in real_stats.items():
        sim_vals = np.array(sim_stats[k])
        p_value = np.mean(sim_vals >= real_val)
        rows.append({
            "stat": k,
            "real": real_val,
            "sim_mean": sim_vals.mean(),
            "sim_5%": np.percentile(sim_vals, 5),
            "sim_95%": np.percentile(sim_vals, 95),
            "p_value": p_value,
        })
    return pd.DataFrame(rows)


def plot_ppc_overlay(model: FittedPositionModel, ppc_y: np.ndarray, n_sim_draws_to_show: int = 50):
    y_real = model.dataset.y
    fig, ax = plt.subplots(figsize=(9, 5))
    bins = np.linspace(0, max(y_real.max(), ppc_y.max()), 40)
    rng = np.random.default_rng(0)
    sample_rows = rng.choice(ppc_y.shape[0], size=min(n_sim_draws_to_show, ppc_y.shape[0]), replace=False)
    for i, row_idx in enumerate(sample_rows):
        ax.hist(
            ppc_y[row_idx], bins=bins, histtype="step", color="steelblue", alpha=0.15,
            label="simulated" if i == 0 else None, density=True,
        )
    ax.hist(y_real, bins=bins, histtype="step", color="black", linewidth=2, label="real", density=True)
    ax.set_xlabel("fantasy points")
    ax.set_ylabel("density")
    ax.set_title(f"{model.dataset.position}: real vs posterior-predictive simulated distributions")
    ax.legend()
    return fig


def get_player_actual_points(dataset: PositionDataset, player_id: str) -> np.ndarray:
    idx = dataset.player_id_to_idx.get(player_id)
    if idx is None:
        return np.array([])
    mask = dataset.player_idx == idx
    return dataset.y[mask]


def plot_player_distribution(
    model: FittedPositionModel,
    player_id: str,
    feature_row: Optional[np.ndarray] = None,
    n_draws: int = 5000,
    seed: int = 0,
):
    """
    Plots a player's simulated weekly-score distribution (using their
    posterior-fitted random effects, at either a supplied feature_row or
    their fill-value average usage) as a filled histogram, with their
    actual observed weekly scores overlaid as a rug + vertical lines so you
    can see how well the fitted shape matches what he's actually done.
    """
    dataset = model.dataset
    name = dataset.idx_to_name.get(dataset.player_id_to_idx.get(player_id), player_id)

    sim_points = model.sample_points(player_id, feature_row=feature_row, n_draws=n_draws, seed=seed)
    actual = get_player_actual_points(dataset, player_id)

    fig, ax = plt.subplots(figsize=(9, 5))
    bins = np.linspace(
        min(sim_points.min(), actual.min(initial=0)) - 1,
        max(sim_points.max(), actual.max(initial=0)) + 1,
        40,
    )

    ax.hist(sim_points, bins=bins, density=True, color="steelblue", alpha=0.5,
            label=f"fitted distribution (n={n_draws} draws)")

    if len(actual) > 0:
        ax.plot(actual, np.zeros_like(actual) - 0.002, "|", color="black", markersize=20,
                markeredgewidth=2, label=f"actual weekly scores (n={len(actual)})")
        ax.axvline(actual.mean(), color="black", linestyle="--", linewidth=1.5,
                    label=f"actual mean ({actual.mean():.1f})")

    sim_mean = sim_points.mean()
    ax.axvline(sim_mean, color="steelblue", linestyle="--", linewidth=1.5,
                label=f"fitted mean ({sim_mean:.1f})")

    ax.set_xlabel("fantasy points")
    ax.set_ylabel("density")
    ax.set_title(f"{name} ({dataset.position}) — actual vs. fitted weekly distribution")
    ax.legend(loc="upper right", fontsize=9)
    return fig


class LoadedModel(FittedPositionModel):
    """
    Reconstructs a FittedPositionModel from pickled (dataset, samples) so
    the plotting/sampling methods (sample_points, player_week_distribution)
    work identically post-load, without needing the original MCMC object.
    """
    def __init__(self, dataset, samples):
        self.dataset = dataset
        self.mcmc = None  # not available after loading from pickle
        self._samples = samples

    def posterior_samples(self):
        return self._samples


if __name__ == "__main__":
    with open("fitted_models.pkl", "rb") as f:
        saved = pickle.load(f)

    models = {pos: LoadedModel(v["dataset"], v["samples"]) for pos, v in saved.items()}

    ppc_y = run_posterior_predictive(models["QB"], seed=0)
    print(ppc_summary_table(models["QB"], ppc_y))
    fig = plot_ppc_overlay(models["QB"], ppc_y)
    fig.savefig("qb_ppc.png", dpi=150)
    print("Wrote qb_ppc.png")

    '''# Player-specific actual vs. fitted comparison. Swap in a real player_id
    # from your dataset -- e.g. grep model.dataset.idx_to_name for the name
    # you want, then look up idx_to_player_id[idx].
    qb_model = models["QB"]

    name_to_id = {v: k for k, v in qb_model.dataset.idx_to_player_id.items()}
    # name_to_id maps idx -> nothing useful directly; better:
    id_by_name = {
        name: qb_model.dataset.idx_to_player_id[idx]
        for idx, name in qb_model.dataset.idx_to_name.items()
    }
    example_player_id = id_by_name["Josh Allen"]  # swap in whoever you want

    fig2 = plot_player_distribution(qb_model, player_id=example_player_id)
    fig2.savefig("player_dist.png", dpi=150)
    print(f"Wrote player_dist.png for player_id={example_player_id}")
    '''

