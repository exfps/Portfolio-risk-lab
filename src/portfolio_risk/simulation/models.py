"""Return-generating models behind one interface.

Every model is fitted to validated historical simple returns and then produces simulated
asset-return paths with shape ``(n_paths, n_periods, n_assets)``. Nothing downstream needs
to know which statistical model produced them.

Conventions
-----------
* Returns are simple returns for one period of the frequency the model was fitted on.
* ``drift="historical"`` keeps the historical average return. Averages estimated from a few
  years of data are very noisy, so ``drift="zero"`` removes the average and isolates risk.
* Parametric models floor simulated returns at -100% so a wealth path cannot go negative.
"""

from __future__ import annotations

from typing import Literal, Protocol

import numpy as np
import numpy.typing as npt
import pandas as pd

from portfolio_risk.errors import ConfigurationError

Drift = Literal["historical", "zero"]
Array = npt.NDArray[np.float64]
FLOOR = -1.0


class ReturnModel(Protocol):
    name: str

    def fit(self, returns: pd.DataFrame) -> ReturnModel: ...

    def simulate(self, n_paths: int, n_periods: int, rng: np.random.Generator) -> Array: ...


def _check_drift(drift: str) -> None:
    if drift not in ("historical", "zero"):
        raise ConfigurationError(f"drift must be 'historical' or 'zero'; got {drift!r}.")


def _factor(covariance: Array) -> Array:
    """A matrix ``A`` with ``A @ A.T == covariance``, valid for singular matrices.

    Cholesky fails when assets are perfectly correlated, which happens with duplicated
    series. The eigen-decomposition works for any symmetric positive semi-definite matrix.
    Tiny negative eigenvalues caused by rounding are set to zero.
    """
    values, vectors = np.linalg.eigh(covariance)
    return np.asarray(vectors * np.sqrt(np.clip(values, 0.0, None)), dtype=np.float64)


class _Fitted:
    def __init__(self) -> None:
        self._mean: Array | None = None

    def _need(self) -> Array:
        if self._mean is None:
            raise ConfigurationError("Model must be fitted before simulating.")
        return self._mean


class Gaussian(_Fitted):
    """Multivariate normal returns with the historical covariance: ``R ~ N(mu, Sigma)``."""

    name = "Gaussian"

    def __init__(self, drift: Drift = "historical") -> None:
        super().__init__()
        _check_drift(drift)
        self.drift = drift
        self._factor: Array | None = None

    def fit(self, returns: pd.DataFrame) -> Gaussian:
        data = returns.to_numpy(dtype=np.float64)
        self._mean = np.zeros(data.shape[1]) if self.drift == "zero" else data.mean(axis=0)
        self._factor = _factor(np.atleast_2d(np.cov(data, rowvar=False)))
        return self

    def simulate(self, n_paths: int, n_periods: int, rng: np.random.Generator) -> Array:
        mean = self._need()
        if self._factor is None:
            raise ConfigurationError("Fit the model before simulating.")
        z = rng.standard_normal((n_paths, n_periods, mean.size))
        out: Array = z @ self._factor.T
        out += mean
        return np.maximum(out, FLOOR, out=out)


class StudentT(_Fitted):
    """Multivariate Student-t returns scaled to match the historical covariance.

    ``R = mu + sqrt((nu - 2) / W) * A Z`` with ``Z`` standard normal, ``W`` chi-squared with
    ``nu`` degrees of freedom and ``A A' = Sigma``. The ``(nu - 2)`` factor makes the
    covariance equal ``Sigma`` rather than ``nu / (nu - 2) * Sigma``. One ``W`` is drawn per
    path and period and shared by all assets, so extreme days hit assets together.
    """

    name = "Student-t"

    def __init__(self, df: float = 5.0, drift: Drift = "historical") -> None:
        super().__init__()
        _check_drift(drift)
        if not df > 2.0:
            raise ConfigurationError(f"Degrees of freedom must exceed 2; got {df}.")
        self.df = float(df)
        self.drift = drift
        self._factor: Array | None = None

    def fit(self, returns: pd.DataFrame) -> StudentT:
        data = returns.to_numpy(dtype=np.float64)
        self._mean = np.zeros(data.shape[1]) if self.drift == "zero" else data.mean(axis=0)
        self._factor = _factor(np.atleast_2d(np.cov(data, rowvar=False)))
        return self

    def simulate(self, n_paths: int, n_periods: int, rng: np.random.Generator) -> Array:
        mean = self._need()
        if self._factor is None:
            raise ConfigurationError("Fit the model before simulating.")
        z = rng.standard_normal((n_paths, n_periods, mean.size))
        w = rng.chisquare(self.df, size=(n_paths, n_periods, 1))
        out: Array = z @ self._factor.T
        out *= np.sqrt((self.df - 2.0) / w)
        out += mean
        return np.maximum(out, FLOOR, out=out)


class Bootstrap(_Fitted):
    """Resample whole historical rows with replacement.

    Every asset in a simulated period comes from the same historical day, which keeps the
    cross-asset relationships. Serial dependence is not kept: each day is drawn independently.
    """

    name = "Historical bootstrap"

    def __init__(self, drift: Drift = "historical") -> None:
        super().__init__()
        _check_drift(drift)
        self.drift = drift
        self._data: Array | None = None

    def fit(self, returns: pd.DataFrame) -> Bootstrap:
        data = returns.to_numpy(dtype=np.float64)
        if self.drift == "zero":
            data = data - data.mean(axis=0)
        self._data = data
        self._mean = data.mean(axis=0)
        return self

    def simulate(self, n_paths: int, n_periods: int, rng: np.random.Generator) -> Array:
        self._need()
        if self._data is None:
            raise ConfigurationError("Fit the model before simulating.")
        picks = rng.integers(0, len(self._data), size=(n_paths, n_periods))
        return np.asarray(np.maximum(self._data[picks], FLOOR), dtype=np.float64)


class BlockBootstrap(_Fitted):
    """Resample runs of consecutive historical rows (circular moving blocks).

    Blocks keep some volatility clustering and short-term dependence. The history is treated
    as circular, so a block that starts near the end continues from the first observation;
    that creates one artificial join. The last block of a path is cut to the horizon.
    """

    name = "Block bootstrap"

    def __init__(self, block_length: int = 21, drift: Drift = "historical") -> None:
        super().__init__()
        _check_drift(drift)
        if block_length < 1:
            raise ConfigurationError(f"Block length must be at least 1; got {block_length}.")
        self.block_length = int(block_length)
        self.drift = drift
        self._data: Array | None = None

    def fit(self, returns: pd.DataFrame) -> BlockBootstrap:
        data = returns.to_numpy(dtype=np.float64)
        if self.block_length > len(data):
            raise ConfigurationError(
                f"Block length {self.block_length} exceeds the {len(data)} observations."
            )
        if self.drift == "zero":
            data = data - data.mean(axis=0)
        self._data = data
        self._mean = data.mean(axis=0)
        return self

    def simulate(self, n_paths: int, n_periods: int, rng: np.random.Generator) -> Array:
        self._need()
        if self._data is None:
            raise ConfigurationError("Fit the model before simulating.")
        length = self.block_length
        blocks = -(-n_periods // length)
        starts = rng.integers(0, len(self._data), size=(n_paths, blocks, 1))
        picks = (starts + np.arange(length)) % len(self._data)
        picks = picks.reshape(n_paths, blocks * length)[:, :n_periods]
        return np.asarray(np.maximum(self._data[picks], FLOOR), dtype=np.float64)


MODELS: dict[str, type[Gaussian] | type[StudentT] | type[Bootstrap] | type[BlockBootstrap]] = {
    "gaussian": Gaussian,
    "student_t": StudentT,
    "bootstrap": Bootstrap,
    "block_bootstrap": BlockBootstrap,
}


def make_model(key: str, **params: float | str) -> ReturnModel:
    """Build a model by registry key, e.g. ``make_model("student_t", df=6)``."""
    try:
        cls = MODELS[key]
    except KeyError:
        raise ConfigurationError(f"Unknown model {key!r}; choose from {sorted(MODELS)}.") from None
    try:
        return cls(**params)  # type: ignore[arg-type]
    except TypeError as error:
        raise ConfigurationError(f"Bad parameters for {key!r}: {error}") from error
