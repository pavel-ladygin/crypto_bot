from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from asgiref.sync import sync_to_async

from subscriptions.models import CoinSnapshot
from bot.handlers.subscribe import cmd_subscribe

router = Router()

@router.message(Command("list"))
async def list_cmd(message: Message):
    coins = await sync_to_async(lambda: list(CoinSnapshot.objects.order_by("-market_cap")[:10]))()

    if not coins:
        await message.answer("Нет данных. Дождитесь обновления.")
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{c.name} ({c.symbol.upper()})", callback_data=c.coingecko_id)]
            for c in coins
        ] + [
            [InlineKeyboardButton(text="📊 Прогноз", callback_data="predict")],
            [InlineKeyboardButton(text="Следующая страница", callback_data="list2")],
            [InlineKeyboardButton(text="Подписка по ID", callback_data="subscribe")],
            [InlineKeyboardButton(text="Назад", callback_data="h0me")]
        ]
    )
    await message.answer("📈 Топ‑10 монет:\n\nВыберите для подписки или прогноза:", reply_markup=keyboard)



# Кнопка «Следующая страница»
@router.callback_query(F.data == "list2")
async def list_page_2(query: CallbackQuery):
    coins = await sync_to_async(lambda: list(CoinSnapshot.objects.order_by("-market_cap")[10:20]))()

    if not coins:
        await query.message.answer("Нет данных.")
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{c.name} ({c.symbol.upper()})", callback_data=c.coingecko_id)]
            for c in coins
        ] + [
            [InlineKeyboardButton(text="Назад", callback_data="list")],
            [InlineKeyboardButton(text="Подписка по ID", callback_data="subscribe")],
            [InlineKeyboardButton(text="Главное меню", callback_data="h0me")]
        ]
    )
    await query.message.edit_text("📈 Монеты 11–20 по капитализации:", reply_markup=keyboard)
    await query.answer()



# Повторный вызов списка
@router.callback_query(F.data == "list")
async def list_callback(query: CallbackQuery):
    await list_cmd(query.message)
    await query.answer()


# Кнопка «Подписка по ID»
@router.callback_query(F.data == "subscribe")
async def inline_subscribe_cb(query: CallbackQuery, state: FSMContext):
    await cmd_subscribe(query.message, state)
    await query.answer()


# Меню прогнозов
@router.callback_query(F.data == "predict")
async def prediction_menu(query: CallbackQuery):
    coins = await sync_to_async(lambda: list(CoinSnapshot.objects.order_by("-market_cap")[:10]))()

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{c.name} ({c.symbol.upper()})", callback_data=f"predict:{c.coingecko_id}")]
            for c in coins
        ] + [
            [InlineKeyboardButton(text="⬅ Назад", callback_data="list")]
        ]
    )

    await query.message.edit_text("🔮 Выберите монету для прогноза:", reply_markup=keyboard)
    await query.answer()

from ai_prediction.generate_forecast import generate_coin_forecast  # путь подкорректируй под структуру проекта
# Генерация прогноза по конкретной монете
@router.callback_query(lambda q: q.data.startswith("predict:"))
async def predict_coin_forecast(query: CallbackQuery):
    coin_id = query.data.split(":", 1)[1]

    await query.message.edit_text(f"🔮 Генерирую ИИ‑прогноз для *{coin_id.upper()}*...")

    forecast = await generate_coin_forecast(coin_id)

    await query.message.answer(f"📊 Прогноз по монете *{coin_id.upper()}*:\n\n{forecast}", parse_mode="Markdown")
    await query.answer()
