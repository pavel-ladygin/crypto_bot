# 📊 Анализ динамики цен на криптовалюты с учетом новостного фона

[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://python.org)
[![Django](https://img.shields.io/badge/Django-5.2.4-darkgreen)](https://djangoproject.com)
[![PyTorch](https://img.shields.io/badge/PyTorch-2.0+-red)](https://pytorch.org)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

> Полнофункциональная система анализа влияния криптоновостей на динамику цен криптовалют с использованием трансформер-моделей (FinBERT vs Custom DistilBERT).

## 📝 Описание проекта

Система автоматически:
- 📰 Собирает криптоновости в реальном времени из множества источников
- 🤖 Анализирует сентимент новостей двумя конкурирующими моделями NLP
- 💹 Интегрирует данные о ценах криптовалют
- 📊 Проводит A/B тестирование моделей
- 📱 Отправляет уведомления через Telegram бота
- 📈 Предоставляет аналитику через Django Admin панель

**Главное достижение:** Создана **Custom DistilBERT модель**, специализированная на криптоновостях, превосходящая baseline решение (FinBERT) по быстродействию (2.4x) и специфичности к крипто-домену.

## 🎯 Ключевые результаты

| Метрика | Значение |
|---------|----------|
| **Новостей обработано** | 1,137 криптоновостей |
| **Custom Model Accuracy** | 81.23% |
| **A/B тестирование** | 70-75% согласие между моделями |
| **Скорость обработки** | 60 msg/sec (Custom vs 25 msg/sec FinBERT) |
| **Размер модели** | 268 МБ (DistilBERT 66M параметров) |

## 🏗️ Архитектура

```
┌─────────────────────────────────────────────────┐
│          TELEGRAM BOT (Aiogram)                 │
│  Подписки, уведомления, статистика по монетам  │
└──────────────────┬──────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────┐
│       DJANGO ADMIN ANALYTICS PANEL              │
│  Сравнение моделей, метрики, визуализация      │
└──────────────────┬──────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────┐
│        NLP PROCESSING LAYER                     │
│  ├─ FinBERT (baseline)                          │
│  └─ Custom DistilBERT (основная модель)        │
└──────────────────┬──────────────────────────────┘
                   │
    ┌──────────────┴──────────────┐
    │                             │
┌───▼──────────────┐    ┌────────▼────────┐
│ PARSER LAYER     │    │ MARKET DATA     │
│ CryptoNews API   │    │ CoinGecko API   │
│ NewsData.io      │    │ OHLCV Data      │
│ RSS Feeds        │    │                 │
└───┬──────────────┘    └────────┬────────┘
    │                           │
    └───────────┬────────────────┘
                │
        ┌───────▼─────────┐
        │  PostgreSQL DB  │
        │ + Redis Cache   │
        └─────────────────┘
```

## 🔧 Технологический стек

### Backend
- **Django 5.2.4** — веб-фреймворк
- **Django REST Framework** — REST API
- **Celery** — асинхронные задачи
- **PostgreSQL** — основная БД
- **Redis** — кэширование

### NLP & ML
- **HuggingFace Transformers** — трансформер-модели
- **PyTorch** — фреймворк глубокого обучения
- **scikit-learn** — метрики и утилиты
- **spaCy** — предобработка текста

### APIs & Integrations
- **CoinGecko API** — котировки криптовалют
- **CryptoNews API** — криптоновости
- **NewsData.io** — RSS агрегатор
- **Aiogram** — Telegram bot framework

### DevOps
- **Docker & Docker Compose** — контейнеризация
- **Nginx** — reverse proxy
- **GitHub Actions** — CI/CD

## 📦 Установка

### Требования
- Python 3.11+
- PostgreSQL 13+
- Redis 6+
- Docker (опционально)

### Локальная установка

```bash
# 1. Клонируем репозиторий
git clone https://github.com/yourusername/crypto-news-sentiment.git
cd crypto-news-sentiment

# 2. Создаем виртуальное окружение
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate  # Windows

# 3. Устанавливаем зависимости
pip install -r requirements.txt

# 4. Создаем .env файл
cp .env.example .env
# Заполняем необходимые переменные окружения

# 5. Применяем миграции
python manage.py migrate

# 6. Создаем супер-пользователя
python manage.py createsuperuser

# 7. Загружаем обученную Custom модель
python manage.py load_model ml/models/crypto_sentiment

# 8. Запускаем разработческий сервер
python manage.py runserver
```

### Docker установка

```bash
# 1. Клонируем репозиторий
git clone https://github.com/yourusername/crypto-news-sentiment.git
cd crypto-news-sentiment

# 2. Создаем .env файл
cp .env.example .env

# 3. Запускаем контейнеры
docker-compose up -d

# 4. Применяем миграции
docker-compose exec django python manage.py migrate

# 5. Создаем супер-пользователя
docker-compose exec django python manage.py createsuperuser
```

## 🚀 Использование

### Django Admin панель
```
http://localhost:8000/admin/
```
Здесь можно просмотреть:
- Список новостей и их анализ (FinBERT)
- Custom модель результаты
- Сравнение моделей (команда `python manage.py compare_models`)
- Статистику по криптовалютам

### Telegram Bot

```python
from subscriptions.tasks import analyze_news_sentiment, analyze_sentiment_with_custom_model

# Анализ с FinBERT
result = analyze_news_sentiment()
print(f"Проанализировано: {result['analyzed']} новостей")

# Анализ с Custom DistilBERT
result = analyze_sentiment_with_custom_model()
print(f"Проанализировано: {result['analyzed']} новостей")
```

Запустить бота:
```bash
docker-compose exec django python telegram_bot.py
```

### Сравнение моделей

```bash
python manage.py compare_models
```

Результат:
```
============================================================
📊 СРАВНЕНИЕ МОДЕЛЕЙ
============================================================

🤖 FinBERT (основная модель)
   Количество анализов: 1137
   Средняя уверенность: 81.5%
   Распределение:
      🔴 negative: 371
      🟢 positive: 313
      ⚪ neutral: 453

🤖 Custom DistilBERT
   Количество анализов: 1117
   Средняя уверенность: 78.1%
   Распределение:
      🔴 negative: 388
      🟢 positive: 371
      ⚪ neutral: 358

============================================================
```

## 📊 API Endpoints

### Получить анализ новости
```bash
GET /api/news/
GET /api/news/{id}/
```

### Получить результаты FinBERT
```bash
GET /api/sentiments/finbert/
GET /api/sentiments/finbert/{id}/
```

### Получить результаты Custom модели
```bash
GET /api/sentiments/custom/
GET /api/sentiments/custom/{id}/
```

### Статистика
```bash
GET /api/statistics/models/
GET /api/statistics/coins/
GET /api/statistics/sentiment/
```

## 🔍 Исследования

### A/B Тестирование

Мы провели A/B тестирование двух моделей на одних и тех же 1,117 криптоновостях:

| Параметр | FinBERT | Custom DistilBERT |
|----------|---------|-------------------|
| Accuracy | ~82% | 81.23% |
| Уверенность | 81.5% | 78.1% |
| Скорость | 25 msg/sec | 60 msg/sec |
| Размер | 440 MB | 268 MB |
| Согласие | 70-75% на одних данных |

### Корреляция новостей и цен

Проверили гипотезу о прямом влиянии новостей на цены:

| Интервал | Корреляция |
|----------|-----------|
| ±1 час | 0.12 (слабая) |
| ±4 часа | 0.18 (слабая) |
| ±24 часа | 0.22 (слабая-средняя) |

**Вывод:** Прямая каузальность не подтвердилась. На крипто-цены влияют множество факторов (макро, спекуляции, технический анализ).

## 📁 Структура проекта

```
crypto-news-sentiment/
├── ml/
│   ├── models/
│   │   └── crypto_sentiment/          # Custom DistilBERT модель
│   │       ├── config.json
│   │       ├── pytorch_model.bin
│   │       └── vocab.txt
│   └── training/
│       ├── train.py                   # Скрипт обучения
│       └── dataset.py                 # Датасет класс
├── subscriptions/
│   ├── models.py                      # NewsSentiment, CustomModelSentiment
│   ├── views.py                       # API endpoints
│   ├── tasks.py                       # Celery задачи
│   ├── admin.py                       # Django Admin конфигурация
│   ├── management/commands/
│   │   ├── compare_models.py          # Сравнение моделей
│   │   └── detailed_comparison.py     # Детальное A/B тестирование
│   └── tests/
├── telegram_bot/
│   ├── bot.py                         # Главный файл бота
│   ├── handlers/
│   │   ├── start.py
│   │   ├── subscribe.py
│   │   └── stats.py
│   └── keyboards/
├── docker-compose.yml                 # Docker конфигурация
├── requirements.txt                   # Python зависимости
├── .env.example                       # Пример переменных окружения
└── README.md                          # Этот файл
```

## 🎓 Выводы исследования

1. **Гипотеза не подтвердилась:** Новости не имеют прямого влияния на краткосрочные ценовые движения крипто-валют.

2. **Причины:**
   - Высокая волатильность крипто-рынков
   - Efficient Market Hypothesis
   - Множество других влияющих факторов
   - Временные задержки между событием и публикацией

3. **Практическое применение Custom модели:**
   - Мониторинг репутации криптопроектов
   - Долгосрочный анализ тренов
   - Анализ сентимента сообщества
   - Исследовательские задачи в финтехе

## 🚀 Рекомендации для развития

### Краткосрочные (1-2 месяца)
- [ ] Расширить датасет до 5K примеров
- [ ] Добавить анализ долгосрочных корреляций (7-30 дней)
- [ ] Интегрировать технический анализ (RSI, MACD)

### Среднесрочные (3-6 месяцев)
- [ ] Экспериментировать с энсамблями моделей
- [ ] Добавить Multi-label классификацию
- [ ] Реализовать LIME/SHAP для интерпретируемости

### Долгосрочные (6-12 месяцев)
- [ ] Экспериментировать с LLMs (LLaMA, GPT)
- [ ] Добавить предсказание ценовых движений
- [ ] Развернуть как SaaS платформу

## 🤝 Команда

- **Ладыгин П.Н.** — Backend, Django, Database
- **Буторов Г.А.** — NLP, ML, Fine-tuning
- **Фатеев С.А.** — APIs, Парсинг, Интеграции
- **Чекин А.В.** — Telegram Bot, DevOps, Docker

## 📜 Лицензия

Проект распространяется под лицензией MIT. Подробности в файле [LICENSE](LICENSE).

## 📞 Контакты

- **Email:** [your-email@example.com]
- **GitHub Issues:** [Issues](https://github.com/yourusername/crypto-news-sentiment/issues)
- **Telegram:** [@yourbot](https://t.me/yourbot)

## 🙏 Благодарности

Спасибо:
- HuggingFace за Transformers библиотеку
- Django разработчикам за отличный фреймворк
- CoinGecko и CryptoNews за открытые API

---

**Статус проекта:** Активно разрабатывается 🚀

**Последнее обновление:** Декабрь 2025

**Звезд:** ⭐⭐⭐⭐⭐ (Если вам понравился проект, поставьте звезду!)
