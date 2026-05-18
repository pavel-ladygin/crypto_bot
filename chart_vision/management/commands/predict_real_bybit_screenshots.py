import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from chart_vision.services.predictor import ChartVisionPredictor


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


class Command(BaseCommand):
    help = "Run demo predictions for real Bybit screenshot images."

    def add_arguments(self, parser):
        parser.add_argument(
            "--input",
            default="ml/datasets/chart_vision_real_screenshots/raw",
        )
        parser.add_argument(
            "--output",
            default=(
                "ml/datasets/chart_vision_real_screenshots/"
                "predictions/real_screenshot_predictions.csv"
            ),
        )
        parser.add_argument(
            "--checkpoint",
            default="ml/models/chart_vision/chart_classifier_resnet18.pt",
        )
        parser.add_argument("--labels", default="ml/models/chart_vision/labels.json")

    def handle(self, *args, **options):
        input_dir = Path(options["input"])
        output_path = Path(options["output"])

        if not input_dir.exists():
            raise CommandError(f"Input directory does not exist: {input_dir}")

        image_paths = sorted(
            path
            for path in input_dir.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        )

        if not image_paths:
            self.stdout.write(
                self.style.WARNING(f"No images found in {input_dir}. Nothing to predict.")
            )
            return

        try:
            predictor = ChartVisionPredictor(
                checkpoint_path=options["checkpoint"],
                labels_path=options["labels"],
            )
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        output_path.parent.mkdir(parents=True, exist_ok=True)
        success_count = 0
        error_count = 0

        with output_path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=[
                    "filename",
                    "predicted_label",
                    "confidence",
                    "probability_downtrend",
                    "probability_sideways",
                    "probability_uptrend",
                    "notes",
                ],
            )
            writer.writeheader()

            for image_path in image_paths:
                try:
                    result = predictor.predict_image(image_path)
                    probabilities = result["probabilities"]
                    writer.writerow(
                        {
                            "filename": image_path.name,
                            "predicted_label": result["predicted_label"],
                            "confidence": result["confidence"],
                            "probability_downtrend": probabilities.get("downtrend", 0.0),
                            "probability_sideways": probabilities.get("sideways", 0.0),
                            "probability_uptrend": probabilities.get("uptrend", 0.0),
                            "notes": "",
                        }
                    )
                    success_count += 1
                except Exception as exc:
                    writer.writerow(
                        {
                            "filename": image_path.name,
                            "predicted_label": "",
                            "confidence": "",
                            "probability_downtrend": "",
                            "probability_sideways": "",
                            "probability_uptrend": "",
                            "notes": f"error: {exc}",
                        }
                    )
                    error_count += 1

        self.stdout.write(self.style.SUCCESS(f"Predictions saved to: {output_path}"))
        self.stdout.write(f"images: {len(image_paths)}")
        self.stdout.write(f"success: {success_count}")
        self.stdout.write(f"errors: {error_count}")
