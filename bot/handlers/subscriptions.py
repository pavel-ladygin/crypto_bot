from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from asgiref.sync import sync_to_async

from subscriptions.models import BotUser, Subscription

router = Router()

async def send_user_subscriptions(user_id: int, send_func):
    user, _ = await sync_to_async(BotUser.objects.get_or_create)(telegram_id=user_id)
    subs = await sync_to_async(list)(Subscription.objects.filter(user=user).select_related("coin"))

    if not subs:
        await send_func("❗ У вас ещё нет подписок. Используйте /list или кнопку «Подписаться».")
        return

    lines = [
        f"• {s.coin.name} ({s.coin.symbol.upper()}) — ID: {s.coin.coingecko_id}"
        for s in subs
    ]
    await send_func("📋 Ваши подписки:\n\n" + "\n".join(lines))

@router.message(Command("subscriptions"))
async def subscriptions_cmd(message: Message):
    await send_user_subscriptions(message.from_user.id, message.answer)

@router.callback_query(F.data == "subscriptions")
async def subscriptions_cb(query: CallbackQuery):
    await send_user_subscriptions(query.from_user.id, query.message.answer)
    await query.answer()
