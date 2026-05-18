"""PyTorch datasets and dataloaders for chart vision images."""

from __future__ import annotations

from pathlib import Path

from PIL import Image
import torch
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms


CLASS_NAMES = ["downtrend", "sideways", "uptrend"]
LABEL_TO_INDEX = {
    "downtrend": 0,
    "sideways": 1,
    "uptrend": 2,
}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


class ChartVisionImageDataset(Dataset):
    def __init__(
        self,
        root_dir: str | Path,
        image_size: int = 224,
        augment: bool = False,
    ):
        self.root_dir = Path(root_dir)
        self.image_size = image_size
        self.augment = augment
        self.samples = self._collect_samples()
        self.transform = self._build_transform()

    def _collect_samples(self) -> list[tuple[Path, int]]:
        if not self.root_dir.exists():
            raise FileNotFoundError(f"Dataset directory does not exist: {self.root_dir}")

        samples: list[tuple[Path, int]] = []
        for class_name in CLASS_NAMES:
            class_dir = self.root_dir / class_name
            if not class_dir.exists():
                raise FileNotFoundError(f"Class directory does not exist: {class_dir}")

            for image_path in sorted(class_dir.iterdir()):
                if image_path.is_file() and image_path.suffix.lower() in IMAGE_EXTENSIONS:
                    samples.append((image_path, LABEL_TO_INDEX[class_name]))

        return samples

    def _build_transform(self):
        if self.augment:
            return transforms.Compose(
                [
                    transforms.RandomResizedCrop(
                        self.image_size,
                        scale=(0.9, 1.0),
                        ratio=(0.95, 1.05),
                    ),
                    transforms.RandomAffine(
                        degrees=0,
                        translate=(0.02, 0.02),
                        scale=(0.98, 1.02),
                    ),
                    transforms.ColorJitter(
                        brightness=0.08,
                        contrast=0.08,
                        saturation=0.04,
                    ),
                    transforms.GaussianBlur(kernel_size=3, sigma=(0.1, 0.6)),
                    transforms.ToTensor(),
                    transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
                ]
            )

        return transforms.Compose(
            [
                transforms.Resize((self.image_size, self.image_size)),
                transforms.ToTensor(),
                transforms.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
            ]
        )

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, index):
        image_path, label = self.samples[index]
        try:
            with Image.open(image_path) as image:
                image = image.convert("RGB")
                image_tensor = self.transform(image)
        except Exception as exc:
            raise ValueError(f"Could not load image {image_path}: {exc}") from exc

        return image_tensor, torch.tensor(label, dtype=torch.long)


def create_dataloaders(
    dataset_root: str | Path,
    batch_size: int = 32,
    image_size: int = 224,
    num_workers: int = 0,
) -> tuple:
    dataset_path = Path(dataset_root)
    split_dirs = {
        "train": dataset_path / "train",
        "val": dataset_path / "val",
        "test": dataset_path / "test",
    }

    missing_splits = [
        split_name for split_name, split_dir in split_dirs.items() if not split_dir.exists()
    ]
    if missing_splits:
        raise FileNotFoundError(
            "Missing dataset split directories: " + ", ".join(missing_splits)
        )

    train_dataset = ChartVisionImageDataset(
        split_dirs["train"],
        image_size=image_size,
        augment=True,
    )
    val_dataset = ChartVisionImageDataset(
        split_dirs["val"],
        image_size=image_size,
        augment=False,
    )
    test_dataset = ChartVisionImageDataset(
        split_dirs["test"],
        image_size=image_size,
        augment=False,
    )

    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=num_workers,
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
    )
    test_loader = DataLoader(
        test_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=num_workers,
    )

    return train_loader, val_loader, test_loader, CLASS_NAMES
