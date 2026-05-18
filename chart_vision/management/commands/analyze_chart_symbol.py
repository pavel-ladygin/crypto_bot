from django.core.management.base import BaseCommand, CommandError

from chart_vision.services.analyze_symbol import analyze_bybit_symbol_chart


class Command(BaseCommand):
    help = "Run end-to-end chart vision analysis for a Bybit symbol."

    def add_arguments(self, parser):
        parser.add_argument("--symbol", required=True)
        parser.add_argument("--interval", default="D")
        parser.add_argument("--window", type=int, default=30)
        parser.add_argument("--no-save", action="store_true")

    def handle(self, *args, **options):
        try:
            result = analyze_bybit_symbol_chart(
                symbol=options["symbol"],
                interval=options["interval"],
                window=options["window"],
                save_result=not options["no_save"],
            )
        except FileNotFoundError as exc:
            raise CommandError(str(exc)) from exc
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        probabilities = result["probabilities"]
        self.stdout.write(f"symbol: {result['symbol']}")
        self.stdout.write(f"interval: {result['interval']}")
        self.stdout.write(f"image_path: {result['image_path']}")
        self.stdout.write(f"predicted_label: {result['predicted_label']}")
        self.stdout.write(f"confidence: {result['confidence']:.6f}")
        self.stdout.write(
            f"probability_downtrend: {probabilities.get('downtrend', 0.0):.6f}"
        )
        self.stdout.write(
            f"probability_sideways: {probabilities.get('sideways', 0.0):.6f}"
        )
        self.stdout.write(f"probability_uptrend: {probabilities.get('uptrend', 0.0):.6f}")
        if result["result_id"] is not None:
            self.stdout.write(f"result_id: {result['result_id']}")
