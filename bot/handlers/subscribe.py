from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from asgiref.sync import sync_to_async
from aiogram.filters import Command, CommandObject

from subscriptions.models import CoinSnapshot, BotUser, Subscription

router = Router()


@router.message(F.text.startswith("/subscribe"))
async def subscribe(message: Message):
    args = message.text.split()
    if len(args) != 2:
        await message.answer("❗ Использование: /subscribe SYMBOL\nПример: /subscribe BTC")
        return

    symbol = args[1].lower()
    print(symbol)
    try:
        coin = await sync_to_async(CoinSnapshot.objects.get)(symbol=symbol)
        # Проверяем или создаём пользователя
        bot_user, _ = await sync_to_async(lambda: BotUser.objects.get_or_create(telegram_id=message.chat.id))()

        # Проверяем, существует ли уже подписка
        subscription_query = await sync_to_async(Subscription.objects.filter)(user=bot_user, coin=coin)
        subscription_exists = await sync_to_async(lambda: subscription_query.exists())()

        if not subscription_exists:  # проверка существования подписки и создание соответрвующей, если ее нет

            await sync_to_async(Subscription.objects.create)(user=bot_user, coin=coin)
            await message.answer(f"Вы успешно подписаны на {coin.name} ({coin.symbol})!")
        else:
            await message.answer(f"Вы уже подписаны на {coin.name} ({coin.symbol}).")


    except CoinSnapshot.DoesNotExist:
        await message.answer("❌ Такой монеты не найдено.")

@router.callback_query(lambda query: query.data == "subscribe")
async def subscribe_callback(call_query: CallbackQuery):
    await subscribe(call_query.message)
    await call_query.answer()
