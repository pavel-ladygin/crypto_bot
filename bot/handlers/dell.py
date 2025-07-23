from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from asgiref.sync import sync_to_async
from subscriptions.models import CoinSnapshot, Subscription, BotUser

router = Router()

@router.message(Command(commands=["delete"]))
async def del_cmd(message: types.Message):
    user_chat_id = message.from_user.id

    # Получаем пользователя и все его подписки
    try:
        user = await sync_to_async(BotUser.objects.get)(telegram_id=user_chat_id)
    except BotUser.DoesNotExist:
        await message.answer("Вы ещё не подписаны ни на одну монету.")
        return

    subscriptions = await sync_to_async(list)(Subscription.objects.filter(user=user).select_related("coin"))

    if not subscriptions:
        await message.answer("У вас нет активных подписок.")
        return

    # Создаем клавиатуру с монетами, на которые пользователь подписан
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{sub.coin.name} ({sub.coin.symbol})",
            callback_data=f"del:{sub.coin.symbol}"
        )] for sub in subscriptions
    ])

    await message.answer("Выберите монету, от которой хотите отписаться:", reply_markup=keyboard)


@router.callback_query()
async def process_delete_callback(query: CallbackQuery):
    data = query.data
    if not data.startswith("del:"):
        return  # Не обрабатываем, если это не наша кнопка

    symbol = data.split(":")[1]
    user_chat_id = query.from_user.id

    try:
        user = await sync_to_async(BotUser.objects.get)(telegram_id=user_chat_id)
        coin = await sync_to_async(CoinSnapshot.objects.get)(symbol=symbol)
        subscription = await sync_to_async(Subscription.objects.get)(user=user, coin=coin)

        await sync_to_async(subscription.delete)()

        await query.message.answer(f"Вы отписались от {coin.name} ({coin.symbol}).")
        await query.answer()

    except Subscription.DoesNotExist:
        await query.answer("Подписка не найдена.", show_alert=True)
    except Exception as e:
        await query.answer(f"Ошибка при удалении подписки: {str(e)}", show_alert=True)
