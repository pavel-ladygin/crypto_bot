def format_stats_for_gpt(stats, coingecko_id):
    context = f"У меня есть данные по монете {coingecko_id.upper()} за последние {len(stats)} дней:\n"
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
