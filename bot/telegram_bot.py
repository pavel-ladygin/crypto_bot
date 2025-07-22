import asyncio
import os
import django
# Подключаем и запускаем джанго
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from aiogram import Bot, Dispatcher, Router
from dotenv import load_dotenv
from bot.handler import router


# Загружаем токен из .env файла
load_dotenv()
TG_TOKEN = os.getenv("TG_TOKEN")

# Инициализация бота и диспетчера, подключение роутера к боту через диспетчер
bot = Bot(token=TG_TOKEN)
dispatcher = Dispatcher()
dispatcher.include_router(router) # Роутер содержит все хендлеры, тут они подклчаеются через диспетчер

async def run_bot():
    await bot.delete_webhook(drop_pending_updates=True)  # удаляем старые обновления
    await dispatcher.start_polling(bot)