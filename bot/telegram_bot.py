import asyncio
import os
import django
# Подключаем и запускаем Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from aiogram.types import BotCommand
from dotenv import load_dotenv
from bot.handlers import all_router
from core.celery import app as celery_app  # Импорт для проверки доступности

# Загружаем токен из .env файла
load_dotenv()
TG_TOKEN = os.getenv("TG_TOKEN")

# Инициализация бота и диспетчера
bot = Bot(token=TG_TOKEN)
storage = MemoryStorage() # Инициализацяи сторедж для того, чтобы обрабатывать сообщения без команды
dispatcher = Dispatcher(storage=storage)

async def set_bot_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="list", description="Список топ-10 монет"),
        BotCommand(command="subscribe", description="Подписаться по поиску монеты"),
        # BotCommand(command="delete", description="Удалить подписку"),
        # BotCommand(command="settings", description="Настройки бота"),
        # BotCommand(command="faq", description="Часто задаваемые вопросы"),
    ]
    await bot.set_my_commands(commands)

# Регистрация роутеров
for r in all_router:
    dispatcher.include_router(r)

async def run_bot():
    await bot.delete_webhook(drop_pending_updates=True)  # Удаляем старые обновления
    await set_bot_commands(bot)
    print("Команды добавлены!")# Добавляем команды в бота
    print("Бот запущен, Celery доступен:", celery_app)  # Проверка доступности Celery
    await dispatcher.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(run_bot())