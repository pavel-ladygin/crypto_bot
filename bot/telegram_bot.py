import asyncio
import os
import django

from subscriptions.models import BotUser, Subscription, Coin
from aiogram import Bot, Dispatcher, Router
from dotenv import load_dotenv
from handler import router

# Подключаем и запускаем джанго
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "bot.settings")
django.setup()

# Загружаем токен из .env файла
load_dotenv()
TG_TOKEN = os.getenv("TG_TOKEN")

# Инициализация бота и диспетчера, подключение роутера к боту через диспетчер
bot = Bot(token=TG_TOKEN)
dispatcher = Dispatcher()
dispatcher.include_router(router) # Роутер содержит все хендлеры, тут они подклчаеются через диспетчер

if __name__ == '__main__':
    asyncio.run(bot)  # Асинхронный запуск бота