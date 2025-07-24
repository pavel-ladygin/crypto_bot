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
    @sync_to_async
    def get_top_coins():
        return list(CoinSnapshot.objects.order_by("-market_cap")[:10])

    coins = await get_top_coins()

    if not coins:
        await message.answer("Нет данных. Дождитесь обновления.")
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
                            [InlineKeyboardButton(text=f"{c.name} ({c.symbol.upper()})", callback_data=c.coingecko_id)]
                            for c in coins
                        ] + [
                            [InlineKeyboardButton(text="Следующая страница", callback_data="list2")],
                            [InlineKeyboardButton(text="Подписка по ID", callback_data="subscribe")],
                            [InlineKeyboardButton(text="Назад", callback_data="h0me")]
                        ]
    )
    await message.answer("Топ‑10 монет:\n\nВыберите для подписки:", reply_markup=keyboard)



@router.callback_query(lambda c: c.data == "list2")
async def list_page_2(query):
    @sync_to_async
    def get_coins():
        return list(CoinSnapshot.objects.order_by("-market_cap")[10:20])

    coins = await get_coins()

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

    await query.message.edit_text("Монеты 11–20 по капитализации:", reply_markup=keyboard)



@router.callback_query(lambda q: q.data == "list")
async def list_callback(query: CallbackQuery):
    await list_cmd(query.message)
    await query.answer()


@router.callback_query(F.data == "subscribe")
async def inline_subscribe_cb(query: CallbackQuery, state: FSMContext):
    await cmd_subscribe(query.message, state)
    await query.answer()
