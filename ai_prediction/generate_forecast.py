from subscriptions.models import CoinSnapshot, CoinDailyStat
from datetime import date, timedelta
from asgiref.sync import sync_to_async
import openai
import os
from dotenv import load_dotenv
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

@sync_to_async
def get_coin_by_coingecko_id(coingecko_id):
    return CoinSnapshot.objects.filter(coingecko_id=coingecko_id).first()

@sync_to_async
def get_last_days_stats(coin_obj, days=7):
    today = date.today()
    start_date = today - timedelta(days=days)
    return list(CoinDailyStat.objects.filter(
        coin=coin_obj,
        date__range=(start_date, today)
    ).order_by("date"))

def format_stats_for_gpt(stats, coin):
    context = f"У меня есть данные по монете {coin.name} ({coin.symbol.upper()}) за последние {len(stats)} дней:\n"
    for stat in stats:
        context += (
            f"{stat.date}: Цена: ${stat.price:.2f}, "
            f"Объем: {stat.volume if stat.volume else 'N/A'}, "
            f"Капитализация: {stat.market_cap if stat.market_cap else 'N/A'}\n"
        )
    context += (
        "\nИсходя из динамики цены, объема и капитализации за эти дни, "
        "что ты можешь сказать? Стоит ли покупать, продавать или держать монету сейчас? "
        "Ответь кратко: [Покупать / Продавать / Держать] и поясни почему."
    )
    return context

from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def call_gpt(prompt: str) -> str:
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",  # или gpt-4
        messages=[
            {"role": "system", "content": "Ты финансовый аналитик."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        max_tokens=1000,
    )
    return response.choices[0].message.content

async def generate_coin_forecast(coingecko_id: str, days: int = 7):
    coin = await get_coin_by_coingecko_id(coingecko_id)
    if not coin:
        return f"Монета с ID `{coingecko_id}` не найдена."

    stats = await get_last_days_stats(coin, days)
    if not stats:
        return f"Нет данных по монете {coin.name} ({coin.symbol.upper()}) за последние {days} дней."

    prompt = format_stats_for_gpt(stats, coin)
    return call_gpt(prompt)
