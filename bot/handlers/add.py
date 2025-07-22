from aiogram import Router

from bot.handlers.start import start_hand

router = Router()

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from asgiref.sync import sync_to_async
from subscriptions.models import CoinSnapshot, Subscription, BotUser



router = Router()

@router.message(Command(commands=["add"]))
async def add_cmd(message: types.Message):
    # Асинхронно получаем список монет
    coins = await sync_to_async(list)(CoinSnapshot.objects.all().values('id', 'name', 'symbol', 'price'))
    if not coins:
        await message.answer("Нет доступных монет. Данные обновляются каждые 5 минут.")
        return

    # Создаём инлайн-клавиатуру с кнопками, используя symbol в callback_data
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{coin['name']} ({coin['symbol']}): ${coin['price']}", callback_data=coin['symbol'])]
        for coin in coins[:10]  # Берем только 10 монет
    ])

    await message.answer("Выберите криптовалюту для подписки:", reply_markup=keyboard)


@router.callback_query()
async def process_subscribe_callback(query: CallbackQuery):
    try:
        # Извлекаем callback_data (данные с кнопки)
        callback_data = query.data

        # Получаем доступные символы асинхронно
        available_symbols = await sync_to_async(list)(CoinSnapshot.objects.all().values_list('symbol', flat=True))

        # Обработка кнопки возвращения на домашнюю страницу
        if callback_data == "back":
            await start_hand(query.message)
            await query.answer()

        # Проверяем, является ли symbol допустимым
        if callback_data not in available_symbols:
            await query.answer("Недопустимый запрос. Пожалуйста, выберите монету из списка.")
            return

        user_chat_id = query.from_user.id

        # Получаем монету по symbol из БД с топ-10 монет
        coin = await sync_to_async(CoinSnapshot.objects.get)(symbol=callback_data)

        # Проверяем или создаём пользователя
        bot_user, _ = await sync_to_async(lambda: BotUser.objects.get_or_create(telegram_id=user_chat_id))()

        # Проверяем, существует ли уже подписка
        subscription_query = await sync_to_async(Subscription.objects.filter)(user=bot_user, coin=coin)
        subscription_exists = await sync_to_async(lambda: subscription_query.exists())()

        if not subscription_exists: # проверка существования подписки и создание соответрвующей, если ее нет
            await sync_to_async(Subscription.objects.create)(user=bot_user, coin=coin)
            await query.message.answer(f"Вы успешно подписаны на {coin.name} ({coin.symbol})!")
        else:
            await query.message.answer(f"Вы уже подписаны на {coin.name} ({coin.symbol}).")

        await query.answer()  # Подтверждаем обработку

    except CoinSnapshot.DoesNotExist: # Обрабокта исключений
        await query.answer("Монета не найдена. Пожалуйста, выберите другую.")
    except ValueError as e:
        await query.answer("Неверный запрос. Пожалуйста, выберите монету из списка.")
    except Exception as e:
        await query.answer(f"Произошла ошибка: {str(e)}", show_alert=True)  # Отображение в попапе