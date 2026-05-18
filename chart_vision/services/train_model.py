"""Training utilities for the chart vision ResNet18 classifier."""

from __future__ import annotations

import json
from pathlib import Path

import torch
from torch import nn
from torch.optim import AdamW
from torchvision import models

from chart_vision.services.torch_dataset import CLASS_NAMES, create_dataloaders


def _create_resnet18(num_classes: int = 3, pretrained: bool = True) -> nn.Module:
    if pretrained:
        try:
            weights = models.ResNet18_Weights.DEFAULT
            model = models.resnet18(weights=weights)
        except Exception as exc:
            print(f"Could not load pretrained ResNet18 weights; using weights=None. Reason: {exc}")
            try:
                model = models.resnet18(weights=None)
            except TypeError:
                model = models.resnet18(pretrained=False)
    else:
        try:
            model = models.resnet18(weights=None)
        except TypeError:
            model = models.resnet18(pretrained=False)

    model.fc = nn.Linear(model.fc.in_features, num_classes)
    return model


def _run_epoch(
    model: nn.Module,
    loader,
    criterion,
    device: torch.device,
    optimizer=None,
) -> tuple[float, float]:
    is_training = optimizer is not None
    model.train() if is_training else model.eval()

    total_loss = 0.0
    total_correct = 0
    total_samples = 0

    context = torch.enable_grad() if is_training else torch.no_grad()
    with context:
        for images, labels in loader:
            images = images.to(device)
            labels = labels.to(device)

            if is_training:
                optimizer.zero_grad()

            outputs = model(images)
            loss = criterion(outputs, labels)

            if is_training:
                loss.backward()
                optimizer.step()

            batch_size = labels.size(0)
            total_loss += loss.item() * batch_size
            total_correct += (outputs.argmax(dim=1) == labels).sum().item()
            total_samples += batch_size

    if total_samples == 0:
        raise ValueError("DataLoader produced no samples.")

    return total_loss / total_samples, total_correct / total_samples


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as json_file:
        json.dump(payload, json_file, indent=2, ensure_ascii=False)


def train_chart_vision_model(
    dataset_root: str | Path = "ml/datasets/chart_vision",
    output_dir: str | Path = "ml/models/chart_vision",
    model_name: str = "resnet18",
    epochs: int = 10,
    batch_size: int = 32,
    image_size: int = 224,
    learning_rate: float = 1e-4,
    num_workers: int = 0,
) -> dict:
    if model_name != "resnet18":
        raise ValueError("Only model_name='resnet18' is currently supported.")
    if epochs <= 0:
        raise ValueError("epochs must be positive.")
    if batch_size <= 0:
        raise ValueError("batch_size must be positive.")
    if image_size <= 0:
        raise ValueError("image_size must be positive.")

    dataset_path = Path(dataset_root)
    model_output_dir = Path(output_dir)
    model_output_dir.mkdir(parents=True, exist_ok=True)

    train_loader, val_loader, _test_loader, class_names = create_dataloaders(
        dataset_path,
        batch_size=batch_size,
        image_size=image_size,
        num_workers=num_workers,
    )
    if len(train_loader.dataset) == 0:
        raise ValueError("Train split contains no images.")
    if len(val_loader.dataset) == 0:
        raise ValueError("Validation split contains no images.")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = _create_resnet18(num_classes=len(class_names), pretrained=True).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = AdamW(model.parameters(), lr=learning_rate)

    checkpoint_path = model_output_dir / "chart_classifier_resnet18.pt"
    labels_path = model_output_dir / "labels.json"
    config_path = model_output_dir / "training_config.json"
    history_path = model_output_dir / "training_history.json"
    report_path = model_output_dir / "model_report.json"

    labels_payload = {str(index): label for index, label in enumerate(class_names)}
    training_config = {
        "model": model_name,
        "image_size": image_size,
        "classes": class_names,
        "dataset_path": str(dataset_path),
        "epochs": epochs,
        "batch_size": batch_size,
        "learning_rate": learning_rate,
    }
    _write_json(labels_path, labels_payload)
    _write_json(config_path, training_config)

    history = []
    best_val_accuracy = -1.0
    best_epoch = 0

    for epoch in range(1, epochs + 1):
        train_loss, train_accuracy = _run_epoch(
            model,
            train_loader,
            criterion,
            device,
            optimizer=optimizer,
        )
        val_loss, val_accuracy = _run_epoch(
            model,
            val_loader,
            criterion,
            device,
            optimizer=None,
        )

        epoch_record = {
            "epoch": epoch,
            "train_loss": train_loss,
            "train_accuracy": train_accuracy,
            "val_loss": val_loss,
            "val_accuracy": val_accuracy,
        }
        history.append(epoch_record)

        print(
            f"epoch={epoch}/{epochs} "
            f"train_loss={train_loss:.4f} train_accuracy={train_accuracy:.4f} "
            f"val_loss={val_loss:.4f} val_accuracy={val_accuracy:.4f}"
        )

        if val_accuracy > best_val_accuracy:
            best_val_accuracy = val_accuracy
            best_epoch = epoch
            torch.save(
                {
                    "model_state_dict": model.state_dict(),
                    "model_name": model_name,
                    "image_size": image_size,
                    "classes": class_names,
                    "epoch": epoch,
                    "val_accuracy": val_accuracy,
                },
                checkpoint_path,
            )

        _write_json(history_path, history)

    final_record = history[-1]
    model_report = {
        "best_val_accuracy": best_val_accuracy,
        "best_epoch": best_epoch,
        "final_train_accuracy": final_record["train_accuracy"],
        "final_val_accuracy": final_record["val_accuracy"],
    }
    _write_json(report_path, model_report)

    return {
        "device": str(device),
        "best_val_accuracy": best_val_accuracy,
        "best_epoch": best_epoch,
        "checkpoint_path": str(checkpoint_path),
        "labels_path": str(labels_path),
        "training_config_path": str(config_path),
        "training_history_path": str(history_path),
        "model_report_path": str(report_path),
    }
