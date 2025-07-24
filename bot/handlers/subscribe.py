from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from asgiref.sync import sync_to_async

from subscriptions.models import CoinSnapshot, BotUser, Subscription
from bot.states import SubscribeState

router = Router()

# 1. /subscribe → активируем FSM
@router.message(F.text == "/subscribe")
async def cmd_subscribe(message: Message, state: FSMContext):
    await message.answer("Введите в чат ID монеты для подписки (coingecko_id), например: bitcoin")
    await state.set_state(SubscribeState.waiting_for_symbol)

# 2. Обработка ввода coingecko_id в FSM
@router.message(SubscribeState.waiting_for_symbol)
async def process_symbol(message: Message, state: FSMContext):
    coin_id = message.text.strip().lower()
    try:
        coin = await sync_to_async(CoinSnapshot.objects.get)(coingecko_id=coin_id)
    except CoinSnapshot.DoesNotExist:
        await message.answer("❌ Монета с таким ID не найдена. Проверьте coingecko_id и попробуйте снова.")
        await state.clear()
        return

    bot_user, _ = await sync_to_async(BotUser.objects.get_or_create)(telegram_id=message.chat.id)
    exists = await sync_to_async(Subscription.objects.filter(user=bot_user, coin=coin).exists)()

    if not exists:
        await sync_to_async(Subscription.objects.create)(user=bot_user, coin=coin)
        await message.answer(f"✅ Вы подписаны на {coin.name} ({coin.symbol.upper()}).")
    else:
        await message.answer(f"ℹ️ Вы уже подписаны на {coin.name} ({coin.symbol.upper()}).")

    await state.clear()

# 3. /subscribe <coingecko_id> сразу
@router.message(F.text.regexp(r"^/subscribe\s+\S+$"))
async def subscribe_direct(message: Message):
    coin_id = message.text.split(maxsplit=1)[1].strip().lower()
    try:
        coin = await sync_to_async(CoinSnapshot.objects.get)(coingecko_id=coin_id)
    except CoinSnapshot.DoesNotExist:
        await message.answer("❌ Монета с таким ID не найдена.")
        return

    bot_user, _ = await sync_to_async(BotUser.objects.get_or_create)(telegram_id=message.chat.id)
    exists = await sync_to_async(Subscription.objects.filter(user=bot_user, coin=coin).exists)()

    if not exists:
        await sync_to_async(Subscription.objects.create)(user=bot_user, coin=coin)
        await message.answer(f"✅ Подписка на {coin.name} оформлена.")
    else:
        await message.answer(f"ℹ️ Вы уже подписаны на {coin.name} ({coin.symbol.upper()}).")
