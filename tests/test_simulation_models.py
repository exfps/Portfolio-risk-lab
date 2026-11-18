"""Simulation models: statistical properties, resampling rules and reproducibility."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from portfolio_risk.errors import ConfigurationError, DataValidationError, InsufficientDataError
from portfolio_risk.simulation import (
    BlockBootstrap,
    Bootstrap,
    Gaussian,
    StudentT,
    make_model,
    prepare_returns,
)


def history(rows: int = 500, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    cov = np.array([[1.0, 0.6], [0.6, 2.0]]) * 1e-4
    data = rng.multivariate_normal([0.0004, 0.0002], cov, size=rows)
    index = pd.bdate_range("2020-01-01", periods=rows)
    return pd.DataFrame(data, index=index, columns=["A", "B"])


def flat(sim: np.ndarray) -> np.ndarray:
    return sim.reshape(-1, sim.shape[-1])


# ---------------------------------------------------------------- preparation


def test_prepare_rejects_short_nan_and_total_loss() -> None:
    good = history()
    with pytest.raises(InsufficientDataError):
        prepare_returns(good.iloc[:30])
    bad = good.copy()
    bad.iloc[3, 0] = np.nan
    with pytest.raises(DataValidationError, match="NaN"):
        prepare_returns(bad)
    bad.iloc[3, 0] = -1.0
    with pytest.raises(DataValidationError, match="100%"):
        prepare_returns(bad)


def test_prepare_warns_about_short_and_constant_series() -> None:
    short = history(100)
    short["C"] = 0.001
    notes = prepare_returns(short).warnings
    assert any("100 observations" in n for n in notes)
    assert any("Constant" in n and "C" in n for n in notes)


def test_prepare_reports_the_estimation_window() -> None:
    assert "500 observations" in prepare_returns(history()).window


# ------------------------------------------------------------------- Gaussian


def test_gaussian_matches_target_mean_and_covariance() -> None:
    data = history()
    sim = flat(Gaussian().fit(data).simulate(4000, 100, np.random.default_rng(7)))
    np.testing.assert_allclose(sim.mean(axis=0), data.mean().to_numpy(), atol=5e-5)
    np.testing.assert_allclose(np.cov(sim, rowvar=False), np.cov(data.T), rtol=0.03)


def test_zero_drift_removes_the_mean() -> None:
    sim = flat(Gaussian("zero").fit(history()).simulate(4000, 100, np.random.default_rng(7)))
    np.testing.assert_allclose(sim.mean(axis=0), 0.0, atol=5e-5)


def test_output_shape_is_paths_periods_assets() -> None:
    for key in ("gaussian", "student_t", "bootstrap", "block_bootstrap"):
        out = make_model(key).fit(history()).simulate(7, 30, np.random.default_rng(0))
        assert out.shape == (7, 30, 2), key


def test_perfectly_correlated_assets_do_not_break_the_factorisation() -> None:
    data = history()
    data["B"] = data["A"]
    sim = Gaussian().fit(data).simulate(50, 20, np.random.default_rng(0))
    assert np.isfinite(sim).all()
    np.testing.assert_allclose(sim[..., 0], sim[..., 1], atol=1e-12)


def test_single_asset_is_supported() -> None:
    sim = Gaussian().fit(history()[["A"]]).simulate(10, 5, np.random.default_rng(0))
    assert sim.shape == (10, 5, 1)


# ------------------------------------------------------------------ Student-t


def test_student_t_matches_covariance_and_has_fat_tails() -> None:
    data = history()
    rng = np.random.default_rng(11)
    t = flat(StudentT(df=8, drift="zero").fit(data).simulate(6000, 100, rng))
    g = flat(Gaussian("zero").fit(data).simulate(6000, 100, np.random.default_rng(11)))
    np.testing.assert_allclose(np.cov(t, rowvar=False), np.cov(data.T), rtol=0.06)
    excess = ((t[:, 0] - t[:, 0].mean()) ** 4).mean() / t[:, 0].var() ** 2 - 3.0
    assert excess > 0.8  # theory: 6 / (nu - 4) = 1.5
    sd = np.sqrt(np.cov(data.T)[0, 0])
    assert (np.abs(t[:, 0]) > 4 * sd).mean() > 3 * (np.abs(g[:, 0]) > 4 * sd).mean()


def test_student_t_requires_more_than_two_degrees_of_freedom() -> None:
    with pytest.raises(ConfigurationError, match="exceed 2"):
        StudentT(df=2.0)


def test_extreme_draws_are_floored_at_minus_one_hundred_percent() -> None:
    data = history() * 40
    sim = StudentT(df=3).fit(data).simulate(2000, 50, np.random.default_rng(0))
    assert sim.min() >= -1.0


# ------------------------------------------------------------------ bootstrap


def test_bootstrap_only_returns_observed_rows_and_keeps_rows_intact() -> None:
    data = history(80)
    sim = flat(Bootstrap().fit(data).simulate(200, 40, np.random.default_rng(3)))
    observed = {tuple(row) for row in data.to_numpy()}
    assert {tuple(row) for row in sim} <= observed


def test_bootstrap_zero_drift_demeans_history() -> None:
    sim = flat(Bootstrap("zero").fit(history()).simulate(3000, 100, np.random.default_rng(3)))
    np.testing.assert_allclose(sim.mean(axis=0), 0.0, atol=5e-5)


# ------------------------------------------------------------- block bootstrap


def test_block_bootstrap_keeps_consecutive_observations_inside_blocks() -> None:
    rows = 90
    index = pd.bdate_range("2021-01-01", periods=rows)
    data = pd.DataFrame({"A": np.arange(rows) / 1000.0}, index=index)  # each row unique
    out = BlockBootstrap(block_length=10).fit(data).simulate(50, 35, np.random.default_rng(5))
    position = np.rint(out[..., 0] * 1000).astype(int)
    steps = np.diff(position, axis=1) % rows
    inside_block = np.ones(34, dtype=bool)
    inside_block[9::10] = False  # a new block starts after every tenth period
    assert (steps[:, inside_block] == 1).all()


def test_block_bootstrap_cuts_the_final_block_to_the_horizon() -> None:
    out = BlockBootstrap(block_length=21).fit(history()).simulate(5, 50, np.random.default_rng(0))
    assert out.shape[1] == 50


def test_block_length_is_validated() -> None:
    with pytest.raises(ConfigurationError):
        BlockBootstrap(block_length=0)
    with pytest.raises(ConfigurationError, match="exceeds"):
        BlockBootstrap(block_length=1000).fit(history(100))


# ---------------------------------------------------- reproducibility / registry


@pytest.mark.parametrize("key", ["gaussian", "student_t", "bootstrap", "block_bootstrap"])
def test_same_seed_gives_identical_paths_and_different_seed_differs(key: str) -> None:
    model = make_model(key).fit(history())
    a = model.simulate(20, 15, np.random.default_rng(42))
    b = model.simulate(20, 15, np.random.default_rng(42))
    c = model.simulate(20, 15, np.random.default_rng(43))
    np.testing.assert_array_equal(a, b)
    assert not np.array_equal(a, c)


def test_registry_rejects_unknown_models_parameters_and_unfitted_use() -> None:
    with pytest.raises(ConfigurationError, match="Unknown model"):
        make_model("heston")
    with pytest.raises(ConfigurationError, match="Bad parameters"):
        make_model("gaussian", df=5)
    with pytest.raises(ConfigurationError, match="fitted"):
        Gaussian().simulate(1, 1, np.random.default_rng(0))
    with pytest.raises(ConfigurationError, match="drift"):
        Gaussian("sideways")  # type: ignore[arg-type]
