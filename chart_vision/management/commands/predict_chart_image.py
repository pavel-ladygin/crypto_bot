from django.core.management.base import BaseCommand, CommandError

from chart_vision.services.predictor import ChartVisionPredictor


class Command(BaseCommand):
    help = "Predict chart trend class for a single chart image."

    def add_arguments(self, parser):
        parser.add_argument("--image", required=True)
        parser.add_argument(
            "--checkpoint",
            default="ml/models/chart_vision/chart_classifier_resnet18.pt",
        )
        parser.add_argument("--labels", default="ml/models/chart_vision/labels.json")
        parser.add_argument("--image-size", type=int, default=224)

    def handle(self, *args, **options):
        try:
            predictor = ChartVisionPredictor(
                checkpoint_path=options["checkpoint"],
                labels_path=options["labels"],
                image_size=options["image_size"],
            )
            result = predictor.predict_image(options["image"])
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        probabilities = result["probabilities"]
        self.stdout.write(f"predicted_label: {result['predicted_label']}")
        self.stdout.write(f"confidence: {result['confidence']:.6f}")
        self.stdout.write(
            f"probability_downtrend: {probabilities.get('downtrend', 0.0):.6f}"
        )
        self.stdout.write(
            f"probability_sideways: {probabilities.get('sideways', 0.0):.6f}"
        )
        self.stdout.write(f"probability_uptrend: {probabilities.get('uptrend', 0.0):.6f}")
