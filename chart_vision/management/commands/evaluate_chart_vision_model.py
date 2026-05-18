from django.core.management.base import BaseCommand, CommandError

from chart_vision.services.evaluate_model import evaluate_chart_vision_model


class Command(BaseCommand):
    help = "Evaluate a trained chart vision model on the test split."

    def add_arguments(self, parser):
        parser.add_argument("--dataset", default="ml/datasets/chart_vision")
        parser.add_argument(
            "--checkpoint",
            default="ml/models/chart_vision/chart_classifier_resnet18.pt",
        )
        parser.add_argument("--labels", default="ml/models/chart_vision/labels.json")
        parser.add_argument("--output", default="ml/models/chart_vision")
        parser.add_argument("--image-size", type=int, default=224)
        parser.add_argument("--batch-size", type=int, default=32)
        parser.add_argument("--num-workers", type=int, default=0)

    def handle(self, *args, **options):
        try:
            result = evaluate_chart_vision_model(
                dataset_root=options["dataset"],
                checkpoint_path=options["checkpoint"],
                labels_path=options["labels"],
                output_dir=options["output"],
                image_size=options["image_size"],
                batch_size=options["batch_size"],
                num_workers=options["num_workers"],
            )
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS("Evaluation complete."))
        self.stdout.write(f"accuracy: {result['accuracy']:.4f}")
        self.stdout.write(f"precision_macro: {result['precision_macro']:.4f}")
        self.stdout.write(f"recall_macro: {result['recall_macro']:.4f}")
        self.stdout.write(f"f1_macro: {result['f1_macro']:.4f}")
        self.stdout.write(f"model_report_path: {result['model_report_path']}")
        self.stdout.write(f"confusion_matrix_path: {result['confusion_matrix_path']}")
