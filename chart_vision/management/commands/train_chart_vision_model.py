from django.core.management.base import BaseCommand, CommandError

from chart_vision.services.train_model import train_chart_vision_model


class Command(BaseCommand):
    help = "Train the chart vision ResNet18 classifier."

    def add_arguments(self, parser):
        parser.add_argument("--dataset", default="ml/datasets/chart_vision")
        parser.add_argument("--output", default="ml/models/chart_vision")
        parser.add_argument("--epochs", type=int, default=10)
        parser.add_argument("--batch-size", type=int, default=32)
        parser.add_argument("--image-size", type=int, default=224)
        parser.add_argument("--lr", type=float, default=1e-4)
        parser.add_argument("--num-workers", type=int, default=0)

    def handle(self, *args, **options):
        try:
            result = train_chart_vision_model(
                dataset_root=options["dataset"],
                output_dir=options["output"],
                epochs=options["epochs"],
                batch_size=options["batch_size"],
                image_size=options["image_size"],
                learning_rate=options["lr"],
                num_workers=options["num_workers"],
            )
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS("Training complete."))
        self.stdout.write(f"device: {result['device']}")
        self.stdout.write(f"best_val_accuracy: {result['best_val_accuracy']:.4f}")
        self.stdout.write(f"best_epoch: {result['best_epoch']}")
        self.stdout.write(f"checkpoint_path: {result['checkpoint_path']}")
        self.stdout.write(f"labels_path: {result['labels_path']}")
        self.stdout.write(f"training_config_path: {result['training_config_path']}")
        self.stdout.write(f"training_history_path: {result['training_history_path']}")
