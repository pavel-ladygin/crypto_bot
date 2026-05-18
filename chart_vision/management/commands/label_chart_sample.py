from django.core.management.base import BaseCommand, CommandError

from chart_vision.models import BybitKline
from chart_vision.services.bybit_client import normalize_interval
from chart_vision.services.labeling import (
    assign_trend_label,
    calculate_window_return,
)


class Command(BaseCommand):
    help = "Assign an MVP trend label to the latest saved BybitKline window."

    def add_arguments(self, parser):
        parser.add_argument("--symbol", default="BTCUSDT")
        parser.add_argument("--interval", default="D")
        parser.add_argument("--window", type=int, default=30)
        parser.add_argument("--threshold", type=float, default=0.03)

    def handle(self, *args, **options):
        symbol = options["symbol"].strip().upper()
        if not symbol:
            raise CommandError("--symbol must be a non-empty string.")

        window = options["window"]
        if window <= 0:
            raise CommandError("--window must be positive.")

        threshold = options["threshold"]
        if threshold < 0:
            raise CommandError("--threshold must be greater than or equal to 0.")

        try:
            interval = normalize_interval(options["interval"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        latest_klines = list(
            BybitKline.objects.filter(symbol=symbol, interval=interval)
            .order_by("-open_time")[:window]
        )

        if len(latest_klines) < window:
            raise CommandError(
                f"Not enough candles for {symbol} {interval}: "
                f"required={window}, available={len(latest_klines)}."
            )

        latest_klines.reverse()
        first = latest_klines[0]
        last = latest_klines[-1]
        close_first = float(first.close_price)
        close_last = float(last.close_price)
        window_return = calculate_window_return(close_first, close_last)
        label = assign_trend_label(close_first, close_last, threshold=threshold)

        self.stdout.write(f"symbol: {symbol}")
        self.stdout.write(f"interval: {interval}")
        self.stdout.write(f"window_start: {first.open_time}")
        self.stdout.write(f"window_end: {last.open_time}")
        self.stdout.write(f"close_first: {close_first}")
        self.stdout.write(f"close_last: {close_last}")
        self.stdout.write(f"window_return_percent: {window_return * 100:.4f}")
        self.stdout.write(f"label: {label}")

