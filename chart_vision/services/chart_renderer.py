"""Render candlestick charts in a Bybit-like visual style."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd


_PRICE_COLUMN_ALIASES = {
    "open_price": "open",
    "high_price": "high",
    "low_price": "low",
    "close_price": "close",
}


def _prepare_ohlcv_dataframe(ohlcv: pd.DataFrame) -> pd.DataFrame:
    if ohlcv.empty:
        raise ValueError("OHLCV dataframe is empty.")

    dataframe = ohlcv.copy()
    dataframe = dataframe.rename(
        columns={
            source: target
            for source, target in _PRICE_COLUMN_ALIASES.items()
            if source in dataframe.columns and target not in dataframe.columns
        }
    )

    required_columns = ["open_time", "open", "high", "low", "close"]
    missing_columns = [column for column in required_columns if column not in dataframe.columns]
    if missing_columns:
        raise ValueError(
            "OHLCV dataframe is missing required columns: "
            + ", ".join(missing_columns)
        )

    dataframe["open_time"] = (
        pd.to_datetime(dataframe["open_time"], utc=True).dt.tz_convert(None)
    )
    dataframe = dataframe.sort_values("open_time")

    numeric_columns = ["open", "high", "low", "close"]
    if "volume" in dataframe.columns:
        numeric_columns.append("volume")

    for column in numeric_columns:
        dataframe[column] = pd.to_numeric(dataframe[column], errors="coerce")

    dataframe = dataframe.dropna(subset=["open", "high", "low", "close"])
    if dataframe.empty:
        raise ValueError("OHLCV dataframe has no valid rows after cleaning.")

    return dataframe


def render_candlestick_chart(
    ohlcv: pd.DataFrame,
    output_path: str | Path,
    title: str | None = None,
    show_volume: bool = True,
    image_size: tuple[int, int] = (800, 450),
) -> Path:
    """Render a dark Bybit/TradingView-style candlestick chart into a PNG file."""
    dataframe = _prepare_ohlcv_dataframe(ohlcv)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    has_volume = bool(
        show_volume
        and "volume" in dataframe.columns
        and dataframe["volume"].notna().any()
    )

    plot_dataframe = dataframe.set_index("open_time")
    plot_dataframe = plot_dataframe.rename(
        columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        }
    )

    market_colors = mpf.make_marketcolors(
        up="#00C176",
        down="#EF454A",
        edge="inherit",
        wick="inherit",
        volume={"up": "#00C176", "down": "#EF454A"},
    )
    style = mpf.make_mpf_style(
        base_mpf_style="nightclouds",
        marketcolors=market_colors,
        facecolor="#111418",
        figcolor="#111418",
        gridcolor="#2A2E39",
        gridstyle="-",
        rc={
            "axes.labelcolor": "#A7B1BC",
            "axes.edgecolor": "#2A2E39",
            "xtick.color": "#A7B1BC",
            "ytick.color": "#A7B1BC",
            "font.size": 8,
        },
    )

    dpi = 100
    width, height = image_size
    fig_size = (width / dpi, height / dpi)

    fig, _axes = mpf.plot(
        plot_dataframe,
        type="candle",
        volume=has_volume,
        style=style,
        title=title or "",
        figsize=fig_size,
        tight_layout=True,
        returnfig=True,
        warn_too_much_data=10000,
    )

    try:
        fig.savefig(
            output,
            dpi=dpi,
            bbox_inches="tight",
            pad_inches=0.04,
            facecolor=fig.get_facecolor(),
        )
    finally:
        plt.close(fig)

    return output


def klines_queryset_to_dataframe(queryset: Iterable) -> pd.DataFrame:
    """Convert BybitKline records into a renderer-friendly OHLCV dataframe."""
    if hasattr(queryset, "order_by") and hasattr(queryset, "values"):
        rows = list(
            queryset.order_by("open_time").values(
                "open_time",
                "open_price",
                "high_price",
                "low_price",
                "close_price",
                "volume",
            )
        )
    else:
        rows = [
            {
                "open_time": item.open_time,
                "open_price": item.open_price,
                "high_price": item.high_price,
                "low_price": item.low_price,
                "close_price": item.close_price,
                "volume": item.volume,
            }
            for item in queryset
        ]

    dataframe = pd.DataFrame(rows)
    if dataframe.empty:
        return pd.DataFrame(columns=["open_time", "open", "high", "low", "close", "volume"])

    dataframe = dataframe.rename(columns=_PRICE_COLUMN_ALIASES)
    return dataframe[["open_time", "open", "high", "low", "close", "volume"]]
