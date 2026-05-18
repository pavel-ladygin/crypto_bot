"""Run ResNet18 image inference for chart direction classification."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image
import torch
from torchvision import transforms

from chart_vision.services.torch_dataset import IMAGENET_MEAN, IMAGENET_STD
from chart_vision.services.train_model import _create_resnet18


MODEL_NOT_TRAINED_MESSAGE = (
    "Модель Chart Vision ещё не обучена. Сначала выполните:\n"
    "python manage.py train_chart_vision_model "
    "--dataset ml/datasets/chart_vision --epochs 10"
)


class ChartVisionPredictor:
    def __init__(
        self,
        checkpoint_path: str | Path = "ml/models/chart_vision/chart_classifier_resnet18.pt",
        labels_path: str | Path = "ml/models/chart_vision/labels.json",
        image_size: int = 224,
        device: str | None = None,
    ):
        self.checkpoint_path = Path(checkpoint_path)
        self.labels_path = Path(labels_path)
        self.image_size = image_size
        self.device = torch.device(
            device if device is not None else ("cuda" if torch.cuda.is_available() else "cpu")
        )

        if not self.checkpoint_path.exists():
            raise FileNotFoundError(
                f"{MODEL_NOT_TRAINED_MESSAGE}\nMissing checkpoint: {self.checkpoint_path}"
            )
        if not self.labels_path.exists():
            raise FileNotFoundError(
                f"{MODEL_NOT_TRAINED_MESSAGE}\nMissing labels.json: {self.labels_path}"
            )

        self.labels = self._load_labels()
        self.model = _create_resnet18(num_classes=len(self.labels), pretrained=False)
        checkpoint_payload = torch.load(self.checkpoint_path, map_location=self.device)
        state_dict = checkpoint_payload.get("model_state_dict", checkpoint_payload)
        self.model.load_state_dict(state_dict)
        self.model.to(self.device)
        self.model.eval()
        self.transform = transforms.Compose(
            [
                transforms.Resize((self.image_size, self.image_size)),
                transforms.ToTensor(),
                transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
            ]
        )

    def _load_labels(self) -> list[str]:
        with self.labels_path.open("r", encoding="utf-8") as labels_file:
            labels_payload = json.load(labels_file)

        return [
            labels_payload[str(index)]
            for index in sorted(int(key) for key in labels_payload.keys())
        ]

    def predict_image(self, image_path: str | Path) -> dict:
        image_file = Path(image_path)
        if not image_file.exists():
            raise FileNotFoundError(f"Image does not exist: {image_file}")

        try:
            with Image.open(image_file) as image:
                image = image.convert("RGB")
                image_tensor = self.transform(image).unsqueeze(0).to(self.device)
        except Exception as exc:
            raise ValueError(f"Could not load image {image_file}: {exc}") from exc

        with torch.no_grad():
            logits = self.model(image_tensor)
            probabilities_tensor = torch.softmax(logits, dim=1).squeeze(0).cpu()

        probabilities = {
            label: float(probabilities_tensor[index].item())
            for index, label in enumerate(self.labels)
        }
        predicted_index = int(probabilities_tensor.argmax().item())
        predicted_label = self.labels[predicted_index]
        confidence = probabilities[predicted_label]

        return {
            "predicted_label": predicted_label,
            "confidence": confidence,
            "probabilities": probabilities,
        }
