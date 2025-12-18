# bot/handlers/start.py

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from asgiref.sync import sync_to_async

from subscriptions.models import BotUser

router = Router()

@router.message(Command("home"))
async def start_hand(message: types.Message):
    user_id = message.from_user.id
    user, created = await sync_to_async(BotUser.objects.get_or_create)(
        telegram_id=message.from_user.id
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔮 Прогнозы", callback_data="predictions"),
        ],
        [
            InlineKeyboardButton(text="📝 Мои подписки", callback_data="subscriptions"),
            InlineKeyboardButton(text="❌ Отписаться", callback_data="delete"),
        ],
        [
            InlineKeyboardButton(text="❓ FAQ", callback_data="faq"),
        ],
    ])
    
    help_text = (
        "👋 <b>Добро пожаловать в Crypto Predictions Bot!</b>\n\n"
        
        "🤖 Я использую AI для прогнозирования движения криптовалют\n\n"
        
        "<b>Доступные команды:</b>\n\n"
        
        "🔮 <b>/predictions</b> - Прогнозы на сегодня\n"
        "   • Просмотр прогнозов для всех монет\n"
        "   • Актуальные цены\n"
        "   • Подписка на рассылку\n\n"
        
        "📝 <b>/subscriptions</b> - Ваши подписки\n"
        "   • Список монет в рассылке\n\n"
        
        "❌ <b>/delete</b> - Отписаться от монеты\n\n"
        
        "❓ <b>/faq</b> - Частые вопросы\n\n"
        
        "📬 <b>Рассылка:</b> Каждый день в 10:00 МСК\n\n"
        
        "<i>Выберите команду ниже или введите вручную</i>"
    )
    
    await message.answer(text=help_text, reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(lambda c: c.data == "h0me")
async def process_start_callback(callback_query: CallbackQuery):
    await start_hand(callback_query.message)
    await callback_query.answer()


@router.message(Command("start"))
async def process_start_command(message: types.Message):
    await start_hand(message)
