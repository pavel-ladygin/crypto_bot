from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from asgiref.sync import sync_to_async
from subscriptions.models import CoinSnapshot, BotUser, Subscription
from bot.states import SubscribeState
from aiogram.fsm.context import FSMContext


router = Router()

# команды /subscribe активирует ожидание другого сообщения с символом монеты
@router.message(F.text == "/subscribe")
async def cmd_subscribe(message: Message, state: FSMContext):          # Обрабокта команды
    await message.answer("Введите символ монеты (например: BTC):")
    await state.set_state(SubscribeState.waiting_for_symbol)


# Функция для обработки сообщения после активации команды /subscribe
@router.message(SubscribeState.waiting_for_symbol)
async def process_symbol(message: Message, state: FSMContext):
    symbol = message.text.strip().lower()
    try:
        coin = await sync_to_async(CoinSnapshot.objects.get)(symbol=symbol)
        bot_user, _ = await sync_to_async(lambda: BotUser.objects.get_or_create(telegram_id=message.chat.id))()

        subscription_query = await sync_to_async(Subscription.objects.filter)(user=bot_user, coin=coin)
        subscription_exists = await sync_to_async(lambda: subscription_query.exists())()

        if not subscription_exists:
            await sync_to_async(Subscription.objects.create)(user=bot_user, coin=coin)
            await message.answer(f"✅ Подписка оформлена на {coin.name} ({coin.symbol.upper()})!")
        else:
            await message.answer(f"ℹ️ Вы уже подписаны на {coin.name} ({coin.symbol.upper()}).")

    except CoinSnapshot.DoesNotExist:
        await message.answer("❌ Такой монеты не найдено.")
    finally:
        await state.clear()


#Функция для обаботки команды /subscribe, которая подписывает на нужную монету по поиску
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



