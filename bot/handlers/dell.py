from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from asgiref.sync import sync_to_async
from subscriptions.models import CoinSnapshot, Subscription, BotUser

router = Router()
# Функция для создания кнопок с монетами под удаление
async def show_delete_keyboard(user_id: int, send_func):
    try:
        user = await sync_to_async(BotUser.objects.get)(telegram_id=user_id)
    except BotUser.DoesNotExist:
        await send_func("❗ Вы ещё не подписаны ни на одну монету.")
        return
    subscriptions = await sync_to_async(list)(
        Subscription.objects.filter(user=user).select_related("coin")
    )

    if not subscriptions:
        await send_func("ℹ️ У вас нет активных подписок.")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"❌ {sub.coin.name} ({sub.coin.symbol.upper()})",
            callback_data=f"del:{sub.coin.symbol}"
        )] for sub in subscriptions


    ] + [
        [InlineKeyboardButton(text="Назад", callback_data="h0me")]
    ]
    )

    await send_func("Выберите монету, от которой хотите отписаться:", reply_markup=keyboard)

# Функция для вывода кнопок удаления по команда /delete
@router.message(Command("delete"))
async def delete_command(message: Message):
    await show_delete_keyboard(message.from_user.id, message.answer)

# Функция для вывода кнопок удаления по кнопке delete

@router.callback_query(F.data == "delete")
async def delete_button(query: CallbackQuery):
    await show_delete_keyboard(query.from_user.id, query.message.answer)
    await query.answer()

# Функция для обработки нажатия кнопок в списке кнопок на удаление
@router.callback_query(F.data.startswith("del:"))
async def process_delete_callback(query: CallbackQuery):
    symbol = query.data.split(":", 1)[1]
    user_chat_id = query.from_user.id
    try:
        user = await sync_to_async(BotUser.objects.get)(telegram_id=user_chat_id)
        coin = await sync_to_async(CoinSnapshot.objects.get)(symbol=symbol)
        subscription = await sync_to_async(Subscription.objects.get)(user=user, coin=coin)

        await sync_to_async(subscription.delete)()

        await query.message.answer(f"✅ Вы отписались от {coin.name} ({coin.symbol.upper()}).")
    except Subscription.DoesNotExist:
        await query.answer("⚠️ Подписка не найдена.", show_alert=True)
    except Exception as e:
        await query.answer(f"❌ Ошибка при удалении: {str(e)}", show_alert=True)
    finally:
        await query.answer()
