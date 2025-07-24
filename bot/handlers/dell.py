from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from asgiref.sync import sync_to_async

from subscriptions.models import CoinSnapshot, Subscription, BotUser

router = Router()

async def show_delete_keyboard(user_id: int, send_func):
    try:
        user = await sync_to_async(BotUser.objects.get)(telegram_id=user_id)
    except BotUser.DoesNotExist:
        await send_func("❗ У вас нет подписок.")
        return

    subs = await sync_to_async(list)(
        Subscription.objects.filter(user=user).select_related("coin")
    )
    if not subs:
        await send_func("ℹ️ У вас нет подписок.")
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"❌ {s.coin.name} ({s.coin.symbol.upper()})",
                    callback_data=f"del:{s.coin.coingecko_id}"
                )
            ]
            for s in subs
        ] + [
            [InlineKeyboardButton(text="🔙 Назад", callback_data="h0me")]
        ]
    )
    await send_func("Выберите монету для удаления подписки:", reply_markup=keyboard)

@router.message(Command("delete"))
async def delete_cmd(message: Message):
    await show_delete_keyboard(message.from_user.id, message.answer)

@router.callback_query(F.data == "delete")
async def delete_button_cb(query: CallbackQuery):
    await show_delete_keyboard(query.from_user.id, query.message.answer)
    await query.answer()

@router.callback_query(F.data.startswith("del:"))
async def process_delete_callback(query: CallbackQuery):
    coin_id = query.data.split(":",1)[1]
    user_id = query.from_user.id

    try:
        user = await sync_to_async(BotUser.objects.get)(telegram_id=user_id)
        coin = await sync_to_async(CoinSnapshot.objects.get)(coingecko_id=coin_id)
        sub = await sync_to_async(Subscription.objects.get)(user=user, coin=coin)
        await sync_to_async(sub.delete)()
        await query.message.answer(f"✅ Подписка на {coin.name} удалена.")
    except Subscription.DoesNotExist:
        await query.answer("⚠️ Подписка не найдена.", show_alert=True)
    finally:
        await query.answer()
