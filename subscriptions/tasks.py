import logging
from bot.telegram_bot import TG_TOKEN
from celery import shared_task
from django.db import transaction
from .models import CoinSnapshot, Subscription
import requests
from datetime import datetime

"""
Для коректной работы всех переодических задач требуется в отдельных терминалах:
1. Запустить django: ❯ python manage.py runserver
2. Запустить бота: ❯ python bot_run.py
3. Запустить celery worker: ❯ celery -A core.celery worker --loglevel=info
4. Запустить celery beat: ❯ celery -A core.celery beat --loglevel=info
5. На всякий проверить работу redis: redis-cli ping, должен прийти ответ PONG


"""


# РАБОТАЕТ ЧЕРЕЗ АДМИНКУ
@shared_task
def update_coin_snapshots():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": 20,
        "page": 1,
        "sparkline": "false"
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        coins_data = response.json()

        with transaction.atomic():
            for coin in coins_data:
                CoinSnapshot.objects.update_or_create(
                    symbol=coin["symbol"],
                    defaults={
                        "name": coin["name"],
                        "price": coin["current_price"]
                    }
                )

        print(f"[{datetime.now()}] Обновлено {len(coins_data)} монет")
        return f"Обновлено {len(coins_data)} монет"

    except requests.RequestException as e:
        print(f"[{datetime.now()}] Ошибка при запросе к API: {e}")
        return f"Ошибка: {e}"




logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)





# Пока это работает без асинхронки, она не заработала у меня, по идее для этого нужно менять Celery
#  на другую архитектуру рассылки
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"

@shared_task
def send_price_updates():
    subscriptions = Subscription.objects.select_related("user", "coin").all()
    user_messages = {}

    for sub in subscriptions:
        user_id = sub.user.telegram_id
        coin = sub.coin
        text = f"{coin.name} ({coin.symbol}): ${coin.price:.2f}"
        user_messages.setdefault(user_id, []).append(text)

    for user_id, messages in user_messages.items():
        full_message = "Ваши обновления по криптовалютам:\n\n" + "\n".join(messages)
        try:
            response = requests.post(TELEGRAM_API_URL, data={
                "chat_id": user_id,
                "text": full_message
            }, timeout=10)
            if not response.ok:
                print(f"[Telegram] Не удалось отправить сообщение {user_id}: {response.text}")
        except Exception as e:
            print(f"[Celery] Ошибка при отправке сообщения пользователю {user_id}: {e}")
