"""Create automatic uptrend, downtrend, and sideways labels."""

from __future__ import annotations

import math


def _as_finite_float(value: float, field_name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be a finite number.") from exc

    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be a finite number.")

    return number


def _validate_threshold(threshold: float) -> float:
    threshold_value = _as_finite_float(threshold, "threshold")
    if threshold_value < 0:
        raise ValueError("threshold must be greater than or equal to 0.")
    return threshold_value


def calculate_window_return(close_first: float, close_last: float) -> float:
    """Return the visible-window price change as a fraction."""
    first = _as_finite_float(close_first, "close_first")
    last = _as_finite_float(close_last, "close_last")

    if first == 0:
        raise ValueError("close_first must not be 0.")

    return (last - first) / first


def assign_trend_label(
    close_first: float,
    close_last: float,
    threshold: float = 0.03,
) -> str:
    """Assign uptrend, downtrend, or sideways from the visible chart window."""
    threshold_value = _validate_threshold(threshold)
    window_return = calculate_window_return(close_first, close_last)

    if window_return >= threshold_value:
        return "uptrend"
    if window_return <= -threshold_value:
        return "downtrend"
    return "sideways"


def assign_future_return_label(
    close_current: float,
    close_future: float,
    threshold: float = 0.02,
) -> str:
    """Assign a label from future return; useful for later prediction datasets."""
    current = _as_finite_float(close_current, "close_current")
    future = _as_finite_float(close_future, "close_future")
    threshold_value = _validate_threshold(threshold)

    if current == 0:
        raise ValueError("close_current must not be 0.")

    future_return = (future - current) / current

    if future_return >= threshold_value:
        return "uptrend"
    if future_return <= -threshold_value:
        return "downtrend"
    return "sideways"
