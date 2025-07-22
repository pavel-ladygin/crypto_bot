from aiogram import Router, types
from aiogram.filters import Command
from asgiref.sync import sync_to_async

from subscriptions.models import BotUser

router = Router()

@router.message(Command("start"))  # С помощью декоратора определяем, что функция # будет принадлежать команде /start
async def start_hand(message: types.Message):
    user_id = message.from_user.id  # Получаем id пользователя

    user, created = await sync_to_async(BotUser.objects.get_or_create)(
        telegram_id=message.from_user.id
    )
    await message.answer(f"Привет, {'новый' if created else 'старый'} пользователь!")
