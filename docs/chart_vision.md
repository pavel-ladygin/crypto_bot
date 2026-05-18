# Chart Vision

## Назначение

Модуль Chart Vision классифицирует изображения свечных графиков криптовалют, построенных на основе исторических Bybit Kline/OHLCV-данных.

MVP-модель решает задачу визуальной классификации текущего состояния уже видимого графика, а не прогнозирования будущей цены.

## Архитектура

```text
Bybit Kline API
  -> BybitKline в БД
  -> генерация графиков в стиле Bybit
  -> автоматическая разметка uptrend/downtrend/sideways
  -> train/val/test dataset
  -> ResNet18
  -> ChartVisionResult
  -> Telegram /chart_ai
```

## Классы

- `uptrend` — восходящий тренд
- `downtrend` — нисходящий тренд
- `sideways` — боковое движение

## Полный пайплайн

For a step-by-step local verification checklist, see [chart_vision_smoke_test.md](chart_vision_smoke_test.md).

Создать миграции:

```bash
python manage.py makemigrations chart_vision
python manage.py migrate
```

В репозитории уже есть initial migration для `chart_vision`; после pull обычно достаточно выполнить `python manage.py migrate`. `makemigrations` нужен, если модели были изменены.

Загрузить свечи:

```bash
python manage.py download_bybit_klines --symbols BTCUSDT ETHUSDT SOLUSDT --interval D --days 1000 --category spot
```

Проверить генерацию одного графика:

```bash
python manage.py render_chart_sample --symbol BTCUSDT --interval D --window 30 --output media/chart_vision/sample_btcusdt.png
```

Проверить label:

```bash
python manage.py label_chart_sample --symbol BTCUSDT --interval D --window 30 --threshold 0.03
```

Построить датасет:

```bash
python manage.py build_chart_dataset --symbols BTCUSDT ETHUSDT SOLUSDT --interval D --window 30 --threshold 0.03 --output ml/datasets/chart_vision --clear --split
```

Обучить модель:

```bash
python manage.py train_chart_vision_model --dataset ml/datasets/chart_vision --epochs 10 --batch-size 32
```

Оценить модель:

```bash
python manage.py evaluate_chart_vision_model --dataset ml/datasets/chart_vision --checkpoint ml/models/chart_vision/chart_classifier_resnet18.pt
```

Проверить одно изображение:

```bash
python manage.py predict_chart_image --image path/to/image.png
```

End-to-end анализ символа:

```bash
python manage.py analyze_chart_symbol --symbol BTCUSDT --interval D --window 30
```

Telegram:

```text
/chart_ai BTCUSDT
```

The Telegram command is available even if it does not appear in the bot command menu yet.

Проверка demo real screenshots:

```bash
python manage.py predict_real_bybit_screenshots
```

## Где хранятся данные

- `BybitKline` — исторические свечи Bybit в БД.
- `ChartVisionResult` — результаты визуальной классификации в БД.
- `ml/datasets/chart_vision/` — сгенерированный train/val/test датасет.
- `ml/models/chart_vision/` — checkpoint модели и отчёты обучения/evaluation.
- `media/chart_vision/` — сгенерированные графики для анализа.
- `ml/datasets/chart_vision_real_screenshots/` — demo-проверка реальных скриншотов Bybit.

## Ограничения MVP

- Модель обучается на сгенерированных графиках в стиле Bybit.
- Реальные скриншоты Bybit используются только как экспериментальная проверка переносимости модели.
- Результат не является финансовой рекомендацией.
- Пользовательские изображения в Telegram пока не обрабатываются.
- Celery не используется в MVP.
- REST API не реализован в MVP.

## Что можно улучшить

- Celery для тяжёлого inference.
- Обработка пользовательских скриншотов.
- Автоматический crop области графика.
- Grad-CAM.
- Сравнение ResNet18 и EfficientNet.
- Поддержка нескольких таймфреймов.
- REST API.
