# bot/handlers/__init__.py

from bot.handlers import (
    start,
    add,
    dell,
    subscriptions,
    predictions,
    faq
)

all_router = [
    start.router,
    add.router,  # Оставляем для внутренних callback
    dell.router,
    subscriptions.router,
    predictions.router,
    faq.router
]
