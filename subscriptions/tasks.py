from celery import shared_task
from .models import CoinSnapshot
import requests
from datetime import datetime

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