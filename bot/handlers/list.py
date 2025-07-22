from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from asgiref.sync import sync_to_async
from subscriptions.models import CoinSnapshot
from datetime import datetime

router = Router()

@router.message(Command(commands=["list"]))
async def list_cmd(message: Message):
    # Асинхронно получаем данные из базы данных
    coins = await sync_to_async(list)(CoinSnapshot.objects.all().values('name', 'symbol', 'price', 'updated_at'))
    if not coins:
        await message.answer("Нет данных о монетах. Данные обновляются каждые 5 минут.")
        return
    text = "Топ 10 монет по капитализации (обновлено: последняя запись):\n\n"
    for coin in coins:
        # Преобразуем updated_at в читаемый формат по московскому времени
        updated_time = datetime.fromisoformat(str(coin['updated_at'].replace(tzinfo=None))).strftime('%H:%M')
        text += f"{coin['name']} ({coin['symbol']}): ${coin['price']} (обновлено в {updated_time} по UTC+3)\n"
    await message.answer(text)