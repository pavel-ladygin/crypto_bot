from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.filters import BaseFilter
from asgiref.sync import sync_to_async

from bot.handlers.start import start_hand
from subscriptions.models import CoinSnapshot, BotUser, Subscription

router = Router()

@router.callback_query(F.data == "back")
async def back_call(query: CallbackQuery):
    await start_hand(query.message)
    await query.answer()

@router.callback_query(F.data == "start")
async def start_call(query: CallbackQuery):
    await start_hand(query.message)
    await query.answer()

class CoinIDFilter(BaseFilter):
    async def __call__(self, query: CallbackQuery) -> bool:
        # Пропускаем только валидные coingecko_id
        return await sync_to_async(CoinSnapshot.objects.filter(coingecko_id=query.data).exists)()

@router.callback_query(CoinIDFilter())
async def process_subscribe_callback(query: CallbackQuery):
    coin_id = query.data
    user_id = query.from_user.id

    coin = await sync_to_async(CoinSnapshot.objects.get)(coingecko_id=coin_id)
    bot_user, _ = await sync_to_async(BotUser.objects.get_or_create)(telegram_id=user_id)
    exists = await sync_to_async(Subscription.objects.filter(user=bot_user, coin=coin).exists)()

    if not exists:
        await sync_to_async(Subscription.objects.create)(user=bot_user, coin=coin)
        await query.message.answer(f"✅ Подписка на {coin.name} оформлена.")
    else:
        await query.message.answer(f"ℹ️ Уже подписаны на {coin.name}.")
    await query.answer()
