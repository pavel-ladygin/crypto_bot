import os
from celery import Celery

# Установка модуля настроек Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

# Создание экземпляра Celery
app = Celery('crypto_bot')  # Замените 'your_project' на имя вашего проекта (например, 'crypto_bot')
app.config_from_object('django.conf:settings', namespace='CELERY')

app.autodiscover_tasks()


