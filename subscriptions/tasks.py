import logging
import os
from asyncio.log import logger

from aiogram import Bot
from celery import shared_task
from dotenv import load_dotenv

from .models import CoinSnapshot, Subscription
import requests
from datetime import datetime


# РАБОТАЕТ ЧЕРЕЗ АДМИНКУ
@shared_task
def update_coin_snapshots():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": 10,
        "page": 1,
        "sparkline": "false"
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()  # Вызывает исключение при ошибке HTTP
        CoinSnapshot.objects.all().delete()  # Очистка старых данных
        for coin in response.json():
            CoinSnapshot.objects.create(
                name=coin["name"],
                symbol=coin["symbol"],
                price=coin["current_price"]
            )
        print(f"Обновлено {len(response.json())} монет в {datetime.now()}")
        return f"Обновлено {len(response.json())} монет"
    except requests.RequestException as e:
        print(f"Ошибка при запросе к API: {e} в {datetime.now()}")
        return f"Ошибка: {e}"

load_dotenv()
token = os.getenv("TG_TOKEN")
bot = Bot(token=token)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



# НЕ РАБОТАЕТ, но через админку можно принудительно отправить, однако сообщение не приходит
@shared_task
def send_price_updates():
    logger.info(f"Starting price updates at {datetime.now()}")
    subscriptions = Subscription.objects.select_related('user', 'coin').all()
    for sub in subscriptions:
        user = sub.user
        coin = sub.coin
        message = f"Обновление цены для {coin.name} ({coin.symbol}): ${coin.price} (по состоянию на {coin.updated_at})"
        try:
            bot.send_message(chat_id=user.telegram_id, text=message)
            logger.info(f"Sent update to {user.telegram_id} for {coin.symbol}")
        except Exception as e:
            logger.error(f"Failed to send update to {user.telegram_id}: {str(e)}")
    logger.info("Price updates completed")