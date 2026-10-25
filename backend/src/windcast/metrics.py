"""Error statistics. Errors are forecast minus actual in MW: positive means the wind came in below forecast."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass


def quantile(sorted_values: Sequence[float], q: float) -> float:
    """Linear interpolation between closest ranks (NumPy's default, Hyndman-Fan type 7)."""
    if not sorted_values:
        raise ValueError("quantile of an empty sequence")
    if not 0.0 <= q <= 1.0:
        raise ValueError(f"q must be in [0, 1], got {q}")
    position = (len(sorted_values) - 1) * q
    lower, upper = math.floor(position), math.ceil(position)
    weight = position - lower
    return float(sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * weight)


@dataclass(frozen=True, slots=True)
class ErrorStats:
    n: int
    mean_error_mw: float
    mae_mw: float
    rmse_mw: float
    p10_mw: float
    p50_mw: float
    p90_mw: float
    shortfall_share: float

    @property
    def p10_p90_width_mw(self) -> float:
        return self.p90_mw - self.p10_mw


def error_stats(errors: Iterable[float]) -> ErrorStats:
    """Bias, MAE, RMSE, P10/P50/P90 and the share of periods with a shortfall (error > 0)."""
    values = sorted(float(e) for e in errors)
    n = len(values)
    if n == 0:
        raise ValueError("no errors to summarise")
    return ErrorStats(
        n=n,
        mean_error_mw=math.fsum(values) / n,
        mae_mw=math.fsum(abs(v) for v in values) / n,
        rmse_mw=math.sqrt(math.fsum(v * v for v in values) / n),
        p10_mw=quantile(values, 0.10),
        p50_mw=quantile(values, 0.50),
        p90_mw=quantile(values, 0.90),
        shortfall_share=sum(1 for v in values if v > 0) / n,
    )


def mae(errors: Iterable[float]) -> float:
    values = [abs(float(e)) for e in errors]
    if not values:
        raise ValueError("no errors")
    return math.fsum(values) / len(values)


def rmse(errors: Iterable[float]) -> float:
    values = [float(e) for e in errors]
    if not values:
        raise ValueError("no errors")
    return math.sqrt(math.fsum(v * v for v in values) / len(values))


def mean(values: Iterable[float]) -> float:
    items = [float(v) for v in values]
    if not items:
        raise ValueError("mean of nothing")
    return math.fsum(items) / len(items)


def pearson(x: Sequence[float], y: Sequence[float]) -> float:
    if len(x) != len(y) or len(x) < 2:
        raise ValueError("need two equal-length sequences of at least two values")
    mx, my = mean(x), mean(y)
    sxy = math.fsum((a - mx) * (b - my) for a, b in zip(x, y, strict=True))
    sxx = math.fsum((a - mx) ** 2 for a in x)
    syy = math.fsum((b - my) ** 2 for b in y)
    return sxy / math.sqrt(sxx * syy)
