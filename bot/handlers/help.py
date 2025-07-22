from aiogram import types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import Router

router = Router()

@router.message(Command(commands=["help"]))
async def help_handler(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🏠 /start", callback_data="start"),
            InlineKeyboardButton(text="📈 /list", callback_data="list"),
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
        "/list - список доступных криптовалют\n"
        "/settings - настройки бота\n"
        "/faq - часто задаваемые вопросы\n\n"
        "Выберите команду на кнопках ниже или введите ее вручную."
    )

    await message.answer(text=help_text, reply_markup=keyboard)
