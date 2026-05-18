from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from chart_vision.models import BybitKline
from chart_vision.services.bybit_client import normalize_interval
from chart_vision.services.chart_renderer import (
    klines_queryset_to_dataframe,
    render_candlestick_chart,
)


class Command(BaseCommand):
    help = "Render a PNG candlestick chart from the latest saved BybitKline candles."

    def add_arguments(self, parser):
        parser.add_argument("--symbol", default="BTCUSDT")
        parser.add_argument("--interval", default="D")
        parser.add_argument("--window", type=int, default=30)
        parser.add_argument("--output", default="media/chart_vision/sample_chart.png")

    def handle(self, *args, **options):
        symbol = options["symbol"].strip().upper()
        if not symbol:
            raise CommandError("--symbol must be a non-empty string.")

        if options["window"] <= 0:
            raise CommandError("--window must be positive.")

        try:
            interval = normalize_interval(options["interval"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        latest_klines = list(
            BybitKline.objects.filter(symbol=symbol, interval=interval)
            .order_by("-open_time")[: options["window"]]
        )

        if len(latest_klines) < options["window"]:
            raise CommandError(
                f"Not enough candles for {symbol} {interval}: "
                f"required={options['window']}, available={len(latest_klines)}."
            )

        latest_klines.reverse()
        dataframe = klines_queryset_to_dataframe(latest_klines)
        output_path = render_candlestick_chart(
            dataframe,
            Path(options["output"]),
            title=f"{symbol} {interval}",
            show_volume=True,
        )

        self.stdout.write(self.style.SUCCESS(f"Chart saved to: {output_path}"))

