from aiogram import types, Dispatcher, Router
from subscriptions.models import BotUser


router = Router()

@router.message(commands=["start"])  # С помощью декоратора определяем, что функция # будет принадлежать команде /start
async def start_hand(message: types.Message):
    user_id = message.from_user.id  # Получаем id пользователя

    user, created = BotUser.objects.get_or_create(  # Ищем пользователя в базе, если ноывй - то
                                                    # создаем объект BotUser
        telegram_id=user_id,
    )
    if created:
        await message.answer("Привет! Ты зарегистрирован!")  # Отпраляем ответ
    else:
        await message.answer("Привет! Ты уже зарегистрирован!")
