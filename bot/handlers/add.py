# bot/handlers/add.py

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from asgiref.sync import sync_to_async

from subscriptions.models import CoinSnapshot, BotUser, Subscription

router = Router()

@router.callback_query(F.data.in_([coin.coingecko_id for coin in CoinSnapshot.objects.all()]))
async def subscribe_coin(callback: CallbackQuery):
    """
    Обработчик подписки на монету по callback_data = coingecko_id
    """
    coingecko_id = callback.data
    telegram_id = callback.from_user.id
    
    @sync_to_async
    def add_subscription():
        try:
            coin = CoinSnapshot.objects.get(coingecko_id=coingecko_id)
            user, _ = BotUser.objects.get_or_create(telegram_id=telegram_id)
            
            # Проверяем существует ли уже подписка
            subscription, created = Subscription.objects.get_or_create(
                user=user,
                coin=coin
            )
            
            return coin, created
        except CoinSnapshot.DoesNotExist:
            return None, False
    
    coin, created = await add_subscription()
    
    if not coin:
        await callback.message.answer("❌ Монета не найдена")
        await callback.answer()
        return
    
    if created:
        # Создаем клавиатуру с быстрыми действиями
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔮 Посмотреть прогноз", callback_data=f"pred_{coin.symbol}")],
            [InlineKeyboardButton(text="📋 Мои подписки", callback_data="subscriptions")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="h0me")]
        ])
        
        message = (
            f"✅ <b>Подписка успешно оформлена!</b>\n\n"
            f"💰 Монета: {coin.name} ({coin.symbol.upper()})\n"
            f"💵 Текущая цена: ${coin.price:,.2f}\n\n"
            f"📬 <b>Что дальше?</b>\n"
            f"• Каждый день в <b>10:00 МСК</b> вы будете получать:\n"
            f"  - Прогноз изменения цены\n"
            f"  - Текущую цену\n"
            f"  - Изменение за последние 24 часа\n\n"
            f"🔮 Прогнозы генерируются AI-моделью на основе анализа цен и новостей\n\n"
            f"<i>Отменить подписку: /delete</i>"
        )
        
        await callback.message.answer(message, reply_markup=keyboard, parse_mode="HTML")
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Мои подписки", callback_data="subscriptions")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="h0me")]
        ])
        
        await callback.message.answer(
            f"ℹ️ Вы уже подписаны на <b>{coin.name} ({coin.symbol.upper()})</b>\n\n"
            f"Рассылка прогнозов: каждый день в 10:00 МСК",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    
    await callback.answer()


# Альтернативный обработчик для прямой подписки по callback из других хэндлеров
@router.callback_query(lambda c: c.data.startswith("subscribe_"))
async def subscribe_coin_direct(callback: CallbackQuery):
    """
    Прямая подписка по callback_data = subscribe_<coin_symbol>
    """
    coin_symbol = callback.data.replace("subscribe_", "")
    telegram_id = callback.from_user.id
    
    @sync_to_async
    def add_subscription():
        try:
            coin = CoinSnapshot.objects.get(symbol=coin_symbol.lower())
            user, _ = BotUser.objects.get_or_create(telegram_id=telegram_id)
            subscription, created = Subscription.objects.get_or_create(user=user, coin=coin)
            return coin, created
        except CoinSnapshot.DoesNotExist:
            return None, False
    
    coin, created = await add_subscription()
    
    if not coin:
        await callback.message.answer("❌ Монета не найдена")
        await callback.answer()
        return
    
    if created:
        await callback.message.answer(
            f"✅ Подписка на {coin.name} ({coin.symbol.upper()}) оформлена!\n"
            f"📬 Прогнозы будут приходить каждый день в 10:00 МСК"
        )
    else:
        await callback.message.answer(
            f"ℹ️ Вы уже подписаны на {coin.name}"
        )
    
    await callback.answer()
