from aiogram import Router

from bot.handlers.start import start_hand

router = Router()

from aiogram import Router, types
from aiogram.filters import Command, BaseFilter
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from asgiref.sync import sync_to_async
from subscriptions.models import CoinSnapshot, Subscription, BotUser



router = Router()

#Обработчик для кнопки назад
@router.callback_query(lambda query: query.data == "back")
async def back_call(query: CallbackQuery):
    await start_hand(query.message)
    await query.answer()



# Функция для обработки кнопки start
@router.callback_query(lambda query: query.data == "start")
async def start_call(query: CallbackQuery):
    await start_hand(query.message)
    await query.answer()



class CoinSymbolFilter(BaseFilter):
    """
    Класс - фильтр, который пропускает в callback только Symbol из таблицы с монетами, те только монеты
    Используется в декораторе @router_callback_query
    """
    async def __call__(self, query: CallbackQuery) -> bool:
        symbol = query.data
        available_symbols = await sync_to_async(list)(CoinSnapshot.objects.all().values_list("symbol", flat=True))
        return symbol in available_symbols


# Функция для обработки кнопки подписки из списка ТОП-10 монет
@router.callback_query(CoinSymbolFilter())
async def process_subscribe_callback(query: CallbackQuery):
    try:
        symbol = query.data
        user_chat_id = query.from_user.id

        # Получаем монету по symbol из БД с топ-10 монет
        coin = await sync_to_async(CoinSnapshot.objects.get)(symbol=symbol)

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