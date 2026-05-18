from datetime import datetime, timedelta, timezone

from django.core.management.base import BaseCommand, CommandError

from chart_vision.models import BybitKline
from chart_vision.services.bybit_client import (
    BybitKlineClient,
    normalize_interval,
)


class Command(BaseCommand):
    help = "Download public Bybit Kline candles and save them into BybitKline."

    def add_arguments(self, parser):
        parser.add_argument(
            "--symbols",
            nargs="+",
            default=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
            help="Bybit symbols to download, e.g. BTCUSDT ETHUSDT SOLUSDT.",
        )
        parser.add_argument("--interval", default="D", help="Bybit interval, e.g. D, 4H, 1H, 15m.")
        parser.add_argument("--days", type=int, default=1000, help="How many days back to request.")
        parser.add_argument("--category", default="spot", help="Bybit product category, e.g. spot.")
        parser.add_argument("--limit", type=int, default=1000, help="Bybit API limit, 1..1000.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Fetch and report candles without saving them.",
        )

    def handle(self, *args, **options):
        symbols = [symbol.strip().upper() for symbol in options["symbols"] if symbol.strip()]
        if not symbols:
            raise CommandError("--symbols must contain at least one symbol.")

        days = options["days"]
        if days <= 0:
            raise CommandError("--days must be positive.")

        limit = options["limit"]
        if limit < 1 or limit > 1000:
            raise CommandError("--limit must be between 1 and 1000.")

        category = options["category"].strip()
        if not category:
            raise CommandError("--category must be a non-empty string.")

        try:
            interval = normalize_interval(options["interval"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        dry_run = options["dry_run"]
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        client = BybitKlineClient()

        total_received = 0
        total_created = 0
        total_updated = 0
        total_skipped = 0
        total_errors = 0

        self.stdout.write(
            f"Downloading Bybit klines: symbols={', '.join(symbols)}, "
            f"interval={interval}, category={category}, days={days}, dry_run={dry_run}"
        )

        for symbol in symbols:
            received = 0
            created = 0
            updated = 0
            skipped = 0

            try:
                candles = client.get_klines(
                    symbol=symbol,
                    interval=interval,
                    category=category,
                    start=start,
                    end=end,
                    limit=limit,
                )
                received = len(candles)
                total_received += received

                if not candles:
                    self.stdout.write(
                        self.style.WARNING(f"{symbol}: Bybit returned an empty Kline list.")
                    )

                for candle in candles:
                    if dry_run:
                        skipped += 1
                        continue

                    try:
                        _obj, was_created = BybitKline.objects.update_or_create(
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
                    except Exception as exc:
                        skipped += 1
                        self.stderr.write(
                            self.style.WARNING(
                                f"{symbol}: skipped candle {candle.get('open_time')}: {exc}"
                            )
                        )
                        continue

                    if was_created:
                        created += 1
                    else:
                        updated += 1

                total_created += created
                total_updated += updated
                total_skipped += skipped

                self.stdout.write(
                    self.style.SUCCESS(
                        f"{symbol}: received={received}, created={created}, "
                        f"updated={updated}, skipped={skipped}, error=no"
                    )
                )

            except Exception as exc:
                total_errors += 1
                self.stderr.write(
                    self.style.ERROR(
                        f"{symbol}: received={received}, created={created}, "
                        f"updated={updated}, skipped={skipped}, error={exc}"
                    )
                )

        self.stdout.write(
            "Total: "
            f"received={total_received}, created={total_created}, "
            f"updated={total_updated}, skipped={total_skipped}, errors={total_errors}"
        )

