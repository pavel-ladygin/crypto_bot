from aiogram import Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from asgiref.sync import sync_to_async
from subscriptions.models import CoinSnapshot
from bot.handlers.subscribe import subscribe
router = Router()

# Функция для обработки команды /list
@router.message(Command(commands=["list"]))
async def list_cmd(message: Message):
    # Асинхронно получаем данные из базы данных
    coins = await sync_to_async(list)(CoinSnapshot.objects.all().values('name', 'symbol', 'price', 'updated_at'))
    if not coins:
        await message.answer("Нет данных о монетах. Данные обновляются каждые 5 минут.") #Обработка исключений
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[  # Создаем кнопки для вывода монет
        [InlineKeyboardButton(text=f"{coin['name']} ({coin['symbol']}): ${coin['price']}",callback_data=coin['symbol'])]
        for coin in coins[:10]  # Берем только 10 монет
    ] + [
        [InlineKeyboardButton(text="Подписка по поиску", callback_data="subscribe")]  # Добавляем кнопку для закрытия меню
    ] + [[InlineKeyboardButton(text ="Назад", callback_data="h0me")

    ]])
    await message.answer("Топ 10 монет по капитализации:\n\nВыберите криптовалюту для подписки:", reply_markup=keyboard)



# Обработка кнопки list
@router.callback_query(lambda query: query.data == "list")
async def list_callback(call_query: CallbackQuery):
    await list_cmd(call_query.message)
    await call_query.answer()


@router.callback_query(lambda query: query.data == "subscribe")                   # Обработка кнопки
async def inline_subscribe(query: CallbackQuery):
    await subscribe(query.message)
    await query.answer()
