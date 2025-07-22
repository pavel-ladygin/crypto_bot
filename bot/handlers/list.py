from aiogram import Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from asgiref.sync import sync_to_async
from subscriptions.models import CoinSnapshot
from datetime import datetime

router = Router()

@router.message(Command(commands=["list"]))
async def list_cmd(message: Message):
    # Асинхронно получаем данные из базы данных
    coins = await sync_to_async(list)(CoinSnapshot.objects.all().values('name', 'symbol', 'price', 'updated_at'))
    if not coins:
        await message.answer("Нет данных о монетах. Данные обновляются каждые 5 минут.")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{coin['name']} ({coin['symbol']}): ${coin['price']}", callback_data=f"subscribe_{coin['name']}")]
        for coin in coins[:10]  # Берем только 10 монет
    ])
    await message.answer("Топ 10 монет по капитализации (обновлено: последняя запись):\n\nВыберите криптовалюту для подписки:", reply_markup=keyboard)




@router.callback_query(lambda query: query.data == "list")
async def list_callback(call_query: CallbackQuery):
    await list_cmd(call_query.message)
    await call_query.answer()