import logging
from bot.telegram_bot import TG_TOKEN
from celery import shared_task
from django.db import transaction
from .models import CoinSnapshot, Subscription, CoinDailyStat
import requests
from datetime import datetime
import time

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
def update_all_coin_snapshots():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    page = 1
    per_page = 250
    all_coins = []

    while page < 4:
        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": per_page,
            "page": page,
            "sparkline": "false"
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        if not data:
            break

        all_coins.extend(data)
        page += 1
        time.sleep(5)

    updated_count = 0

    for coin in all_coins:
        CoinSnapshot.objects.update_or_create(
            coingecko_id=coin["id"],
            defaults={
                "name": coin["name"],
                "symbol": coin["symbol"],
                "price": coin["current_price"],
                "market_cap": coin.get("market_cap")  # добавлено
            }
        )
        updated_count += 1

    print(f"✅ Загружено и обновлено {updated_count} монет по coingecko_id")



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
                    coingecko_id=coin["id"],
                    defaults={
                        "name": coin["name"],
                        "symbol": coin["symbol"],
                        "price": coin["current_price"],
                        "market_cap": coin.get("market_cap")  # добавлено
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


@shared_task
def fetch_daily_coin_stats_from_30_day():
    coins = CoinSnapshot.objects.all()
    for coin in coins:
        try:
            url = f"https://api.coingecko.com/api/v3/coins/{coin.coingecko_id}/market_chart"
            params = {
                "vs_currency": "usd",
                "days": 30,
                "interval": "daily"
            }
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()

            prices = data.get("prices", [])
            market_caps = data.get("market_caps", [])
            volumes = data.get("total_volumes", [])

            for i in range(len(prices)):
                timestamp = prices[i][0] / 1000
                date = datetime.utcfromtimestamp(timestamp).date()

                price = prices[i][1]
                market_cap = market_caps[i][1] if i < len(market_caps) else None
                volume = volumes[i][1] if i < len(volumes) else None

                # Изменение капитализации
                prev_market_cap = market_caps[i - 1][1] if i > 0 and i - 1 < len(market_caps) else None
                market_cap_change = market_cap - prev_market_cap if market_cap and prev_market_cap else None

                # Изменение цены в %
                prev_price = prices[i - 1][1] if i > 0 and i - 1 < len(prices) else None
                price_change_percent = None
                if prev_price and prev_price > 0:
                    price_change_percent = ((price - prev_price) / prev_price) * 100

                CoinDailyStat.objects.update_or_create(
                    coin=coin,
                    date=date,
                    defaults={
                        "price": price,
                        "market_cap": market_cap,
                        "market_cap_change": market_cap_change,
                        "volume": volume,
                        "price_change_percent": price_change_percent
                    }
                )

            print(f"✅ {coin.symbol.upper()} обновлен")

            time.sleep(60)  # защита от rate limit'а

        except Exception as e:
            print(f"❌ Ошибка для {coin.coingecko_id}: {e}")
