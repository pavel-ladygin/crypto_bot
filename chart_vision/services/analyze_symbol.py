"""Perform end-to-end Bybit symbol analysis with chart vision."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from django.conf import settings

from chart_vision.models import BybitKline, ChartVisionResult
from chart_vision.services.bybit_client import (
    BybitClientError,
    BybitKlineClient,
    normalize_interval,
)


def _get_latest_klines(symbol: str, interval: str, window: int) -> list[BybitKline]:
    klines = list(
        BybitKline.objects.filter(symbol=symbol, interval=interval)
        .order_by("-open_time")[:window]
    )
    klines.reverse()
    return klines


def _download_recent_klines(symbol: str, interval: str) -> int:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=120)
    client = BybitKlineClient()

    try:
        candles = client.get_klines(
            symbol=symbol,
            interval=interval,
            category="spot",
            start=start,
            end=end,
            limit=1000,
        )
    except BybitClientError as exc:
        raise RuntimeError(f"Could not fetch recent Bybit candles: {exc}") from exc

    saved = 0
    for candle in candles:
        BybitKline.objects.update_or_create(
            symbol=candle["symbol"],
            interval=candle["interval"],
            open_time=candle["open_time"],
            defaults={
                "open_price": candle["open"],
                "high_price": candle["high"],
                "low_price": candle["low"],
                "close_price": candle["close"],
                "volume": candle["volume"],
                "turnover": candle["turnover"],
                "source": "bybit",
            },
        )
        saved += 1

    return saved


def _generated_chart_paths(symbol: str, interval: str) -> tuple[Path, str]:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{symbol}_{interval}_{timestamp}.png"
    media_root = Path(getattr(settings, "MEDIA_ROOT", Path(settings.BASE_DIR) / "media"))
    output_dir = media_root / "chart_vision" / "generated"
    image_field_path = f"chart_vision/generated/{filename}"
    return output_dir / filename, image_field_path


def analyze_bybit_symbol_chart(
    symbol: str,
    interval: str = "D",
    window: int = 30,
    save_result: bool = True,
    user=None,
) -> dict:
    """Render and classify the latest Bybit chart window for a symbol."""
    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise ValueError("symbol must be a non-empty string.")
    if window <= 1:
        raise ValueError("window must be greater than 1.")

    normalized_interval = normalize_interval(interval)
    klines = _get_latest_klines(normalized_symbol, normalized_interval, window)

    if len(klines) < window:
        _download_recent_klines(normalized_symbol, normalized_interval)
        klines = _get_latest_klines(normalized_symbol, normalized_interval, window)

    if len(klines) < window:
        raise ValueError(
            f"Not enough Bybit candles for {normalized_symbol} {normalized_interval}: "
            f"required={window}, available={len(klines)}."
        )

    from chart_vision.services.chart_renderer import (
        klines_queryset_to_dataframe,
        render_candlestick_chart,
    )
    from chart_vision.services.predictor import ChartVisionPredictor

    dataframe = klines_queryset_to_dataframe(klines)
    output_path, image_field_path = _generated_chart_paths(
        normalized_symbol,
        normalized_interval,
    )
    render_candlestick_chart(
        dataframe,
        output_path,
        title=f"{normalized_symbol} {normalized_interval}",
        show_volume=True,
    )

    predictor = ChartVisionPredictor()
    prediction = predictor.predict_image(output_path)
    probabilities = prediction["probabilities"]
    result_id = None

    if save_result:
        result = ChartVisionResult.objects.create(
            user=user,
            symbol=normalized_symbol,
            interval=normalized_interval,
            source=ChartVisionResult.SOURCE_GENERATED,
            image=image_field_path,
            predicted_label=prediction["predicted_label"],
            confidence=prediction["confidence"],
            probability_uptrend=probabilities.get("uptrend"),
            probability_downtrend=probabilities.get("downtrend"),
            probability_sideways=probabilities.get("sideways"),
            model_version="chart_resnet18_v1",
        )
        result_id = result.id

    return {
        "symbol": normalized_symbol,
        "interval": normalized_interval,
        "image_path": str(output_path),
        "predicted_label": prediction["predicted_label"],
        "confidence": prediction["confidence"],
        "probabilities": probabilities,
        "source": "generated",
        "result_id": result_id,
    }
