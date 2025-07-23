from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from asgiref.sync import sync_to_async
from subscriptions.models import BotUser

router = Router()

@router.message(Command("start"))  # С помощью декоратора определяем, что функция # будет принадлежать команде /start
async def start_hand(message: types.Message):
    user_id = message.from_user.id  # Получаем id пользователя

    user, created = await sync_to_async(BotUser.objects.get_or_create)(
        telegram_id=message.from_user.id
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🏠 /start", callback_data="start"),
            InlineKeyboardButton(text="📈 /list", callback_data="list"),
        ],
        [
            InlineKeyboardButton(text=" /subscribe", callback_data="sub"),
            InlineKeyboardButton(text=" /delete", callback_data="dell"),
        ],
        [
            InlineKeyboardButton(text="⚙️ /settings", callback_data="settings"),
            InlineKeyboardButton(text="❓ /faq", callback_data="faq"),
        ],
    ])

    help_text = (
        "👋 Привет! Я ваш бот для работы с криптовалютами.\n\n"
        "Вот список доступных команд:\n"
        "/start - начать работу с ботом\n"
        "/list - список доступных для подписки криптовалют\n"
        "/subscribe - подписаться на монету, которой нет в списке по поиску\n"
        "/delete - удалить криптовалюту из рассылки\n"
        "/settings - настройки бота\n"
        "/faq - часто задаваемые вопросы\n\n"
        "Выберите команду на кнопках ниже или введите ее вручную."
    )

    await message.answer(text=help_text, reply_markup=keyboard)



@router.callback_query(lambda c: c.data == "start")
async def process_start_callback(callback_query: CallbackQuery):
    await start_hand(callback_query.message)
    await callback_query.answer()