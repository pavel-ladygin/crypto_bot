import asyncio
import os
import django
# Подключаем и запускаем Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from aiogram import Bot, Dispatcher
from dotenv import load_dotenv
from bot.handlers import all_router
from core.celery import app as celery_app  # Импорт для проверки доступности

# Загружаем токен из .env файла
load_dotenv()
TG_TOKEN = os.getenv("TG_TOKEN")

# Инициализация бота и диспетчера
bot = Bot(token=TG_TOKEN)
dispatcher = Dispatcher()

# Регистрация роутеров
for r in all_router:
    dispatcher.include_router(r)

async def run_bot():
    await bot.delete_webhook(drop_pending_updates=True)  # Удаляем старые обновления
    print("Бот запущен, Celery доступен:", celery_app)  # Проверка доступности Celery
    await dispatcher.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(run_bot())