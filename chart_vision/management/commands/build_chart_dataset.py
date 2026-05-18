from django.core.management.base import BaseCommand, CommandError

from chart_vision.services.dataset_builder import build_chart_dataset


class Command(BaseCommand):
    help = "Build generated chart vision image dataset from saved BybitKline candles."

    def add_arguments(self, parser):
        parser.add_argument(
            "--symbols",
            nargs="+",
            default=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
        )
        parser.add_argument("--interval", default="D")
        parser.add_argument("--window", type=int, default=30)
        parser.add_argument("--threshold", type=float, default=0.03)
        parser.add_argument("--output", default="ml/datasets/chart_vision")
        parser.add_argument("--max-per-class", type=int, default=None)
        parser.add_argument("--clear", action="store_true")
        parser.add_argument("--split", dest="split", action="store_true", default=True)
        parser.add_argument("--no-split", dest="split", action="store_false")

    def handle(self, *args, **options):
        try:
            stats = build_chart_dataset(
                symbols=options["symbols"],
                interval=options["interval"],
                window=options["window"],
                threshold=options["threshold"],
                output_dir=options["output"],
                max_per_class=options["max_per_class"],
                clear=options["clear"],
                split=options["split"],
            )
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS("Chart dataset build complete."))
        self.stdout.write(f"total_images: {stats['total_images']}")

        self.stdout.write("class_counts:")
        for label, count in stats["class_counts"].items():
            self.stdout.write(f"  {label}: {count}")

        self.stdout.write("split_counts:")
        for split_name, split_counts in stats["split_counts"].items():
            counts_text = ", ".join(
                f"{label}={count}" for label, count in split_counts.items()
            )
            self.stdout.write(f"  {split_name}: {counts_text}")

        self.stdout.write(f"metadata_path: {stats['metadata_path']}")
        self.stdout.write(f"split_metadata_path: {stats['split_metadata_path']}")
