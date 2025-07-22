from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from asgiref.sync import sync_to_async

from subscriptions.models import BotUser, Subscription

router = Router()

@router.message(Command(commands=["subscriptions"]))
async def subscriptions_cmd(message: Message):
    # Получаем или создаем пользователя по telegram_id
    user, _ = await sync_to_async(BotUser.objects.get_or_create)(
        telegram_id=message.from_user.id
    )

    # Получаем все подписки этого пользователя
    subscriptions = await sync_to_async(list)(
        Subscription.objects.filter(user=user).select_related("coin")
    )

    if not subscriptions:
        await message.answer("Вы ещё не подписались ни на одну криптовалюту. Используйте /list, чтобы выбрать монету.")
        return

    # Формируем список монет
    text_lines = [
        f"• {sub.coin.name} ({sub.coin.symbol})"
        for sub in subscriptions
    ]
    coins_text = "\n".join(text_lines)
    await message.answer(f"Вы подписаны на следующие криптовалюты:\n\n{coins_text}")
