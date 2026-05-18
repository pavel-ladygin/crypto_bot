"""Build image datasets for chart vision model training."""

from __future__ import annotations

import csv
import random
import shutil
import warnings
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from chart_vision.models import BybitKline
from chart_vision.services.bybit_client import normalize_interval
from chart_vision.services.chart_renderer import (
    klines_queryset_to_dataframe,
    render_candlestick_chart,
)
from chart_vision.services.labeling import (
    assign_trend_label,
    calculate_window_return,
)


CLASS_NAMES = ["downtrend", "sideways", "uptrend"]
METADATA_COLUMNS = [
    "image_path",
    "symbol",
    "interval",
    "window_start",
    "window_end",
    "window_return",
    "label",
    "source",
    "is_real_screenshot",
]


def _validate_ratios(train_ratio: float, val_ratio: float, test_ratio: float) -> None:
    ratios = [train_ratio, val_ratio, test_ratio]
    if any(ratio < 0 for ratio in ratios):
        raise ValueError("train_ratio, val_ratio, and test_ratio must be non-negative.")
    if train_ratio <= 0:
        raise ValueError("train_ratio must be greater than 0.")
    ratio_sum = train_ratio + val_ratio + test_ratio
    if ratio_sum <= 0:
        raise ValueError("At least one split ratio must be positive.")
    if abs(ratio_sum - 1.0) > 0.001:
        raise ValueError("train_ratio, val_ratio, and test_ratio must sum to 1.0.")


def _safe_clear_directory(output_dir: Path) -> None:
    if not output_dir.exists():
        return

    resolved = output_dir.resolve()
    if resolved.anchor == str(resolved) or len(resolved.parts) <= 2:
        raise ValueError(f"Refusing to clear unsafe output directory: {output_dir}")

    shutil.rmtree(resolved)


def _write_metadata(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _split_class_records(
    records: list[dict[str, Any]],
    train_ratio: float,
    val_ratio: float,
    random_seed: int,
) -> dict[str, list[dict[str, Any]]]:
    rng = random.Random(random_seed)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[record["label"]].append(record)

    split_records = {"train": [], "val": [], "test": []}

    for label, label_records in grouped.items():
        shuffled = list(label_records)
        rng.shuffle(shuffled)
        count = len(shuffled)

        if count < 3:
            warnings.warn(
                f"Class '{label}' has only {count} image(s); "
                "train/val/test split will be incomplete.",
                stacklevel=2,
            )

        if count == 1:
            split_records["train"].extend(shuffled)
            continue
        if count == 2:
            split_records["train"].append(shuffled[0])
            split_records["val"].append(shuffled[1])
            continue

        train_count = max(1, round(count * train_ratio))
        val_count = max(1, round(count * val_ratio))
        test_count = count - train_count - val_count

        while test_count < 1 and (train_count > 1 or val_count > 1):
            if train_count >= val_count and train_count > 1:
                train_count -= 1
            elif val_count > 1:
                val_count -= 1
            test_count = count - train_count - val_count

        if test_count < 1:
            test_count = 0

        split_records["train"].extend(shuffled[:train_count])
        split_records["val"].extend(shuffled[train_count : train_count + val_count])
        split_records["test"].extend(shuffled[train_count + val_count :])

    return split_records


def _copy_split_images(
    output_dir: Path,
    split_records: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    split_metadata: list[dict[str, Any]] = []

    for split_name in ["train", "val", "test"]:
        split_root = output_dir / split_name
        if split_root.exists():
            shutil.rmtree(split_root)

        for class_name in CLASS_NAMES:
            (split_root / class_name).mkdir(parents=True, exist_ok=True)

        for record in split_records[split_name]:
            source_path = Path(record["image_path"])
            destination = split_root / record["label"] / source_path.name
            shutil.copy2(source_path, destination)

            split_record = dict(record)
            split_record["image_path"] = str(destination)
            split_record["split"] = split_name
            split_metadata.append(split_record)

    return split_metadata


def _count_by_split_and_class(
    split_metadata: list[dict[str, Any]],
) -> dict[str, dict[str, int]]:
    split_counts = {
        split_name: {class_name: 0 for class_name in CLASS_NAMES}
        for split_name in ["train", "val", "test"]
    }
    for row in split_metadata:
        split_counts[row["split"]][row["label"]] += 1
    return split_counts


def build_chart_dataset(
    symbols: list[str],
    interval: str = "D",
    window: int = 30,
    threshold: float = 0.03,
    output_dir: str | Path = "ml/datasets/chart_vision",
    max_per_class: int | None = None,
    clear: bool = False,
    split: bool = True,
    train_ratio: float = 0.7,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    random_seed: int = 42,
) -> dict:
    """Build generated candlestick chart images and metadata from saved BybitKline rows."""
    if not symbols:
        raise ValueError("symbols must contain at least one symbol.")
    if window <= 1:
        raise ValueError("window must be greater than 1.")
    if max_per_class is not None and max_per_class <= 0:
        raise ValueError("max_per_class must be positive when provided.")
    if split:
        _validate_ratios(train_ratio, val_ratio, test_ratio)

    normalized_symbols = [symbol.strip().upper() for symbol in symbols if symbol.strip()]
    if not normalized_symbols:
        raise ValueError("symbols must contain at least one non-empty symbol.")

    normalized_interval = normalize_interval(interval)
    output_path = Path(output_dir)
    if clear:
        _safe_clear_directory(output_path)

    all_root = output_path / "all"
    for class_name in CLASS_NAMES:
        (all_root / class_name).mkdir(parents=True, exist_ok=True)

    metadata_rows: list[dict[str, Any]] = []
    generated_by_class: Counter[str] = Counter()

    for symbol in normalized_symbols:
        klines = list(
            BybitKline.objects.filter(symbol=symbol, interval=normalized_interval)
            .order_by("open_time")
        )

        if len(klines) < window:
            warnings.warn(
                f"{symbol} {normalized_interval}: not enough candles "
                f"for window={window}; available={len(klines)}.",
                stacklevel=2,
            )
            continue

        for index in range(0, len(klines) - window + 1):
            window_klines = klines[index : index + window]
            first = window_klines[0]
            last = window_klines[-1]
            close_first = float(first.close_price)
            close_last = float(last.close_price)
            label = assign_trend_label(close_first, close_last, threshold=threshold)

            if max_per_class is not None and generated_by_class[label] >= max_per_class:
                continue

            window_return = calculate_window_return(close_first, close_last)
            start_stamp = first.open_time.strftime("%Y%m%d%H%M%S")
            end_stamp = last.open_time.strftime("%Y%m%d%H%M%S")
            filename = f"{symbol}_{normalized_interval}_{start_stamp}_{end_stamp}.png"
            image_path = all_root / label / filename

            try:
                dataframe = klines_queryset_to_dataframe(window_klines)
                render_candlestick_chart(
                    dataframe,
                    image_path,
                    title=None,
                    show_volume=True,
                )
            except Exception as exc:
                warnings.warn(
                    f"Skipping {symbol} window {first.open_time}..{last.open_time}: {exc}",
                    stacklevel=2,
                )
                continue

            if not image_path.exists() or image_path.stat().st_size == 0:
                warnings.warn(
                    f"Skipping {symbol} window {first.open_time}..{last.open_time}: "
                    f"renderer did not create a valid image.",
                    stacklevel=2,
                )
                continue

            generated_by_class[label] += 1
            metadata_rows.append(
                {
                    "image_path": str(image_path),
                    "symbol": symbol,
                    "interval": normalized_interval,
                    "window_start": first.open_time.isoformat(),
                    "window_end": last.open_time.isoformat(),
                    "window_return": window_return,
                    "label": label,
                    "source": "generated_bybit_style",
                    "is_real_screenshot": "false",
                }
            )

    metadata_path = output_path / "metadata.csv"
    _write_metadata(metadata_path, metadata_rows, METADATA_COLUMNS)

    split_metadata_path: Path | None = None
    split_counts: dict[str, dict[str, int]] = {
        split_name: {class_name: 0 for class_name in CLASS_NAMES}
        for split_name in ["train", "val", "test"]
    }

    if split and metadata_rows:
        split_records = _split_class_records(
            metadata_rows,
            train_ratio=train_ratio,
            val_ratio=val_ratio,
            random_seed=random_seed,
        )
        split_metadata = _copy_split_images(output_path, split_records)
        split_counts = _count_by_split_and_class(split_metadata)
        split_metadata_path = output_path / "split_metadata.csv"
        _write_metadata(split_metadata_path, split_metadata, METADATA_COLUMNS + ["split"])

    class_counts = {class_name: generated_by_class[class_name] for class_name in CLASS_NAMES}
    return {
        "total_images": len(metadata_rows),
        "class_counts": class_counts,
        "split_counts": split_counts,
        "metadata_path": str(metadata_path),
        "split_metadata_path": str(split_metadata_path) if split_metadata_path else None,
    }
