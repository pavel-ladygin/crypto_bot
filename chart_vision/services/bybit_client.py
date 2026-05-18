"""Load Bybit OHLCV/Kline data for chart vision datasets and analysis."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import requests


class BybitClientError(Exception):
    """Base exception for Bybit client failures."""


class BybitAPIError(BybitClientError):
    """Raised when Bybit returns an API-level error."""


def normalize_interval(interval: str) -> str:
    """Normalize a human-friendly interval into Bybit's Kline interval format."""
    if not isinstance(interval, str) or not interval.strip():
        raise ValueError("Interval must be a non-empty string.")

    interval_key = interval.strip().lower()
    interval_map = {
        "d": "D",
        "1d": "D",
        "day": "D",
        "daily": "D",
        "4h": "240",
        "240": "240",
        "1h": "60",
        "60": "60",
        "15m": "15",
        "15": "15",
        "5m": "5",
        "5": "5",
    }

    try:
        return interval_map[interval_key]
    except KeyError as exc:
        supported = ", ".join(sorted(interval_map))
        raise ValueError(
            f"Unsupported Bybit interval '{interval}'. Supported values: {supported}."
        ) from exc


def to_milliseconds(dt: datetime) -> int:
    """Convert a datetime to a UTC timestamp in milliseconds."""
    if not isinstance(dt, datetime):
        raise TypeError("dt must be a datetime instance.")

    if dt.tzinfo is None or dt.utcoffset() is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    return int(dt.timestamp() * 1000)


def _parse_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None

    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise BybitAPIError(f"Could not parse decimal value from {value!r}.") from exc


def _required_decimal(value: Any, field_name: str) -> Decimal:
    parsed = _parse_decimal(value)
    if parsed is None:
        raise BybitAPIError(f"Missing required Kline field '{field_name}'.")
    return parsed


def _parse_kline_item(item: list[Any], symbol: str, interval: str) -> dict:
    if not isinstance(item, list):
        raise BybitAPIError(f"Unexpected Kline item format: {item!r}.")

    if len(item) < 5:
        raise BybitAPIError(f"Kline item is too short: {item!r}.")

    try:
        open_time = datetime.fromtimestamp(int(item[0]) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OSError) as exc:
        raise BybitAPIError(f"Could not parse Kline start time from {item[0]!r}.") from exc

    return {
        "symbol": symbol,
        "interval": interval,
        "open_time": open_time,
        "open": _required_decimal(item[1], "openPrice"),
        "high": _required_decimal(item[2], "highPrice"),
        "low": _required_decimal(item[3], "lowPrice"),
        "close": _required_decimal(item[4], "closePrice"),
        "volume": _parse_decimal(item[5]) if len(item) > 5 else None,
        "turnover": _parse_decimal(item[6]) if len(item) > 6 else None,
    }


class BybitKlineClient:
    def __init__(
        self,
        base_url: str = "https://api.bybit.com",
        timeout: int = 15,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.session = requests.Session()

    def get_klines(
        self,
        symbol: str,
        interval: str = "D",
        category: str = "spot",
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> list[dict]:
        """Fetch Kline candles from Bybit and return normalized candle dictionaries."""
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("symbol must be a non-empty string.")
        if not category or not category.strip():
            raise ValueError("category must be a non-empty string.")
        if limit < 1 or limit > 1000:
            raise ValueError("limit must be between 1 and 1000.")

        normalized_interval = normalize_interval(interval)
        params: dict[str, Any] = {
            "category": category.strip(),
            "symbol": normalized_symbol,
            "interval": normalized_interval,
            "limit": limit,
        }

        if start is not None:
            params["start"] = to_milliseconds(start)
        if end is not None:
            params["end"] = to_milliseconds(end)

        url = f"{self.base_url}/v5/market/kline"
        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
                if response.status_code >= 500 or response.status_code == 429:
                    raise BybitClientError(
                        f"Temporary Bybit HTTP error {response.status_code}: {response.text[:300]}"
                    )
                if 400 <= response.status_code < 500:
                    raise BybitAPIError(
                        f"Bybit HTTP error {response.status_code}: {response.text[:300]}"
                    )

                response.raise_for_status()
                payload = response.json()
                ret_code = payload.get("retCode")

                if str(ret_code) != "0":
                    ret_msg = payload.get("retMsg", "Unknown Bybit API error")
                    raise BybitAPIError(f"Bybit API error {ret_code}: {ret_msg}")

                raw_items = payload.get("result", {}).get("list", [])
                if raw_items is None:
                    raw_items = []
                if not isinstance(raw_items, list):
                    raise BybitAPIError("Bybit response field result.list is not a list.")

                candles = [
                    _parse_kline_item(item, normalized_symbol, normalized_interval)
                    for item in raw_items
                ]
                return sorted(candles, key=lambda candle: candle["open_time"])

            except BybitAPIError:
                raise
            except (requests.RequestException, ValueError, BybitClientError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(self.retry_delay)

        raise BybitClientError(
            f"Failed to fetch Bybit klines for {normalized_symbol} "
            f"{normalized_interval} after {self.max_retries} attempts: {last_error}"
        )
