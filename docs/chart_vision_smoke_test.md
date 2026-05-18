# Chart Vision Smoke Test

Use this checklist after pulling the project locally or rebuilding the Docker image.

## 1. Django Check

```bash
python manage.py check
```

## 2. Migrations

If migrations need to be generated:

```bash
python manage.py makemigrations chart_vision
python manage.py migrate
```

If the migration already exists:

```bash
python manage.py migrate
```

## 3. Download Bybit Candles

```bash
python manage.py download_bybit_klines --symbols BTCUSDT ETHUSDT SOLUSDT --interval D --days 1000 --category spot
```

## 4. Render One Chart

```bash
python manage.py render_chart_sample --symbol BTCUSDT --interval D --window 30 --output media/chart_vision/sample_btcusdt.png
```

## 5. Check One Label

```bash
python manage.py label_chart_sample --symbol BTCUSDT --interval D --window 30 --threshold 0.03
```

## 6. Build Dataset

```bash
python manage.py build_chart_dataset --symbols BTCUSDT ETHUSDT SOLUSDT --interval D --window 30 --threshold 0.03 --output ml/datasets/chart_vision --clear --split
```

## 7. Quick Training Smoke Test

```bash
python manage.py train_chart_vision_model --dataset ml/datasets/chart_vision --epochs 1 --batch-size 8
```

## 8. Full Training

```bash
python manage.py train_chart_vision_model --dataset ml/datasets/chart_vision --epochs 10 --batch-size 32
```

## 9. Evaluation

```bash
python manage.py evaluate_chart_vision_model --dataset ml/datasets/chart_vision --checkpoint ml/models/chart_vision/chart_classifier_resnet18.pt
```

## 10. Predict One Image

```bash
python manage.py predict_chart_image --image <path_to_test_image>
```

## 11. End-to-End Symbol Analysis

```bash
python manage.py analyze_chart_symbol --symbol BTCUSDT --interval D --window 30
```

## 12. Telegram

```text
/chart_ai BTCUSDT
```

The command is available even if Telegram's command menu has not been refreshed.

## 13. Demo Real Screenshots

```bash
python manage.py predict_real_bybit_screenshots
```

## Typical Errors

### checkpoint not found

Train the model first:

```bash
python manage.py train_chart_vision_model --dataset ml/datasets/chart_vision --epochs 10
```

### no klines found

Download candles and run migrations first:

```bash
python manage.py migrate
python manage.py download_bybit_klines --symbols BTCUSDT --interval D --days 1000 --category spot
```

### no module named cv2

Install dependencies from `requirements.txt` or rebuild Docker after the Dockerfile hardening.

### matplotlib backend error

The renderer uses the `Agg` backend. Rebuild/install dependencies if the error persists.

### no such table chart_vision_bybitkline

Run:

```bash
python manage.py migrate
```

### Bybit API returned empty list

Check the symbol, interval, category, and network access. Try `BTCUSDT`, `D`, and `spot`.

### CUDA not available

This is safe. Training and inference fall back to CPU.

### Telegram bot does not show /chart_ai in menu

The handler is still registered. Run `/chart_ai BTCUSDT` manually or refresh bot commands later.
