from crypto_bot.ai_prediction.get_last_stats import get_last_days_stats
from crypto_bot.ai_prediction.format_gpt import format_stats_for_gpt
from crypto_bot.ai_prediction.call_gpt import call_gpt
def generate_coin_forecast(coingecko_id, days=7):
    stats = get_last_days_stats(coingecko_id, days)
    if not stats.exists():
        return "Нет данных для анализа."

    prompt = format_stats_for_gpt(stats, coingecko_id)
    forecast = call_gpt(prompt)
    return forecast
