from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from asgiref.sync import sync_to_async

from subscriptions.models import BotUser, Subscription

router = Router()

# Функция для создания списка подписок
async def send_user_subscriptions(user_id: int, send_func):
    user, _ = await sync_to_async(BotUser.objects.get_or_create)(
    telegram_id=user_id
    )
    subscriptions = await sync_to_async(list)(
        Subscription.objects.filter(user=user).select_related("coin")
    )

    if not subscriptions:
        await send_func("❗ Вы ещё не подписались ни на одну криптовалюту. Используйте /list, чтобы выбрать монету.")
        return

    # Формируем текст
    lines = [f"• {sub.coin.name} ({sub.coin.symbol.upper()})" for sub in subscriptions]
    text = "📋 Ваши подписки:\n\n" + "\n".join(lines)

    await send_func(text)

# Функция для отображения списка подписок по команде
@router.message(Command("subscriptions"))
async def subscriptions_cmd(message: Message):
    await send_user_subscriptions(message.from_user.id, message.answer)


# Функция для отображения списка подписок по кнопке
@router.callback_query(F.data == "subscriptions")
async def subscriptions_callback(query: CallbackQuery):
    await send_user_subscriptions(query.from_user.id, query.message.answer)
    await query.answer()