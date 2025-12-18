# core/celery.py

from celery import Celery
from celery.schedules import crontab
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

app = Celery('core')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# ============================================
# CELERY BEAT РАСПИСАНИЕ
# ============================================

app.conf.beat_schedule = {
    # Обновление цен каждые 5 минут
    'update-coin-prices-every-5-minutes': {
        'task': 'subscriptions.tasks.update_coin_snapshots',
        'schedule': 300.0,  # 5 минут
    },
    
    # Сбор исторических цен каждый час
    'collect-historical-prices-hourly': {
        'task': 'subscriptions.tasks.collect_historical_prices',
        'schedule': crontab(minute=0),  # Каждый час
        'kwargs': {'days': 2}  # Последние 2 дня
    },
    
    # Сбор новостей каждые 3 часа
    'collect-news-every-3-hours': {
        'task': 'subscriptions.tasks.collect_historical_news',
        'schedule': crontab(minute=0, hour='*/3'),  # Каждые 3 часа
        'kwargs': {'days': 1}  # Последний день
    },
    
    # Анализ тональности каждый час
    'analyze-sentiment-hourly': {
        'task': 'subscriptions.tasks.analyze_all_sentiment',
        'schedule': crontab(minute=30),  # Каждый час в :30
    },
    
    # Полное обновление и генерация прогнозов в 01:00 UTC (04:00 MSK)
    'daily-data-update-and-predictions': {
        'task': 'subscriptions.tasks.update_daily_data',
        'schedule': crontab(hour=1, minute=0),
    },
    
    # Рассылка прогнозов в 07:00 UTC (10:00 MSK)
    'send-daily-predictions': {
        'task': 'subscriptions.tasks.send_daily_predictions_to_users',
        'schedule': crontab(hour=7, minute=0),
    },
}

app.conf.timezone = 'UTC'
