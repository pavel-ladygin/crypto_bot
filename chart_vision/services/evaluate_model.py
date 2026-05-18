"""Evaluation utilities for the chart vision classifier."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import torch
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

from chart_vision.services.torch_dataset import create_dataloaders
from chart_vision.services.train_model import _create_resnet18


def _load_labels(labels_path: Path) -> list[str]:
    if not labels_path.exists():
        raise FileNotFoundError(f"labels.json does not exist: {labels_path}")

    with labels_path.open("r", encoding="utf-8") as labels_file:
        labels_payload = json.load(labels_file)

    return [
        labels_payload[str(index)]
        for index in sorted(int(key) for key in labels_payload.keys())
    ]


def _plot_confusion_matrix(
    matrix,
    class_names: list[str],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6, 5))
    image = ax.imshow(matrix, interpolation="nearest", cmap="Blues")
    fig.colorbar(image, ax=ax)

    ax.set_xticks(range(len(class_names)))
    ax.set_yticks(range(len(class_names)))
    ax.set_xticklabels(class_names, rotation=35, ha="right")
    ax.set_yticklabels(class_names)
    ax.set_xlabel("Predicted label")
    ax.set_ylabel("True label")
    ax.set_title("Chart Vision Confusion Matrix")

    for row_index in range(len(class_names)):
        for column_index in range(len(class_names)):
            value = matrix[row_index][column_index]
            ax.text(
                column_index,
                row_index,
                str(value),
                ha="center",
                va="center",
                color="white" if value > matrix.max() / 2 else "black",
            )

    fig.tight_layout()
    fig.savefig(output_path, dpi=140, bbox_inches="tight")
    plt.close(fig)


def evaluate_chart_vision_model(
    dataset_root: str | Path = "ml/datasets/chart_vision",
    checkpoint_path: str | Path = "ml/models/chart_vision/chart_classifier_resnet18.pt",
    labels_path: str | Path = "ml/models/chart_vision/labels.json",
    output_dir: str | Path = "ml/models/chart_vision",
    image_size: int = 224,
    batch_size: int = 32,
    num_workers: int = 0,
) -> dict:
    checkpoint = Path(checkpoint_path)
    labels_file = Path(labels_path)
    model_output_dir = Path(output_dir)
    report_path = model_output_dir / "model_report.json"
    confusion_matrix_path = model_output_dir / "confusion_matrix.png"

    if not checkpoint.exists():
        raise FileNotFoundError(f"Checkpoint does not exist: {checkpoint}")

    class_names = _load_labels(labels_file)
    _train_loader, _val_loader, test_loader, _dataset_class_names = create_dataloaders(
        dataset_root,
        batch_size=batch_size,
        image_size=image_size,
        num_workers=num_workers,
    )
    if len(test_loader.dataset) == 0:
        raise ValueError("Test split contains no images.")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = _create_resnet18(num_classes=len(class_names), pretrained=False).to(device)
    checkpoint_payload = torch.load(checkpoint, map_location=device)
    state_dict = checkpoint_payload.get("model_state_dict", checkpoint_payload)
    model.load_state_dict(state_dict)
    model.eval()

    true_labels = []
    predicted_labels = []

    with torch.no_grad():
        for images, labels in test_loader:
            images = images.to(device)
            outputs = model(images)
            predictions = outputs.argmax(dim=1).cpu().tolist()
            predicted_labels.extend(predictions)
            true_labels.extend(labels.cpu().tolist())

    accuracy = accuracy_score(true_labels, predicted_labels)
    precision_macro = precision_score(
        true_labels,
        predicted_labels,
        average="macro",
        zero_division=0,
    )
    recall_macro = recall_score(
        true_labels,
        predicted_labels,
        average="macro",
        zero_division=0,
    )
    f1_macro = f1_score(
        true_labels,
        predicted_labels,
        average="macro",
        zero_division=0,
    )
    report = classification_report(
        true_labels,
        predicted_labels,
        labels=list(range(len(class_names))),
        target_names=class_names,
        output_dict=True,
        zero_division=0,
    )
    matrix = confusion_matrix(
        true_labels,
        predicted_labels,
        labels=list(range(len(class_names))),
    )

    model_report = {
        "accuracy": accuracy,
        "precision_macro": precision_macro,
        "recall_macro": recall_macro,
        "f1_macro": f1_macro,
        "classification_report": report,
        "confusion_matrix": matrix.tolist(),
    }

    model_output_dir.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as report_file:
        json.dump(model_report, report_file, indent=2, ensure_ascii=False)

    _plot_confusion_matrix(matrix, class_names, confusion_matrix_path)

    return {
        **model_report,
        "model_report_path": str(report_path),
        "confusion_matrix_path": str(confusion_matrix_path),
    }
