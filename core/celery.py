import os
from celery import Celery
from celery.schedules import crontab

# Установка модуля настроек Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

# Создание экземпляра Celery
app = Celery('crypto_bot')  # Замените 'your_project' на имя вашего проекта (например, 'crypto_bot')
app.config_from_object('django.conf:settings', namespace='CELERY')

app.autodiscover_tasks()


# Настройка периодических задач после конфигурации, не факт, что это нужно, потому что можно через админку
@app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # Рассылка в 10:00 утра по местному времени (CEST, UTC+2)
    from subscriptions.tasks import send_price_updates
    sender.add_periodic_task(
        crontab(minute='*/5'),  # 10:00 UTC+2
        send_price_updates.s(),
        name='daily_price_updates'
    )