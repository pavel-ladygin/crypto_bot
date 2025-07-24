from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from asgiref.sync import sync_to_async
from subscriptions.models import BotUser

router = Router()

# Обработка команды /start которая выводит приветственное сообщение
@router.message(Command("home"))  # С помощью декоратора определяем, что функция # будет принадлежать команде /start
async def start_hand(message: types.Message):
    user_id = message.from_user.id  # Получаем id пользователя

    user, created = await sync_to_async(BotUser.objects.get_or_create)(
        telegram_id=message.from_user.id
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🏠 /home", callback_data="start"),
            InlineKeyboardButton(text="📈 /list", callback_data="list"),
        ],
        [
            InlineKeyboardButton(text="✅ /subscribe", callback_data="subscribe"),
            InlineKeyboardButton(text="📝 /subscriptions", callback_data="subscriptions"),
        ],
        [
            InlineKeyboardButton(text="❌ /delete", callback_data="delete"),
            InlineKeyboardButton(text="❓ /faq", callback_data="faq"),
        ],
    ])

    help_text = (
        "👋 Привет! Я ваш бот для работы с криптовалютами.\n\n"
        "Вот список доступных команд:\n"
        "🏠 /home - начальная страница бота\n"
        "📈 /list - список доступных для подписки криптовалют, просто нажмите на нужную вам монету из списка!\n"
        "✅ /subscribe - подписаться на монету, которой нет в списке по поиску, просто введите название нужной монеты!\n"
        "📝 /subscriptions - список монет, на которые вы подписались\n"
        "❌ /delete - удалить криптовалюту из вашей рассылки\n"
        "❓ /faq - часто задаваемые вопросы\n\n"
        "Выберите команду на кнопках ниже или введите ее вручную."
    )

    await message.answer(text=help_text, reply_markup=keyboard)


# Функция для перехода домой по кнопке (название h0me, а не home, потому что есть крипта HOME)
@router.callback_query(lambda c: c.data == "h0me")
async def process_start_callback(callback_query: CallbackQuery):
    await start_hand(callback_query.message)
    await callback_query.answer()

@router.message(Command("home"))
async def process_start_callback(message: types.Message):
    await start_hand(message)
    await message.answer()