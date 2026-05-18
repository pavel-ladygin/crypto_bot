from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import FSInputFile
from asgiref.sync import sync_to_async

from subscriptions.models import BotUser


router = Router()

LABEL_TRANSLATIONS = {
    "uptrend": "восходящий тренд",
    "downtrend": "нисходящий тренд",
    "sideways": "боковое движение",
}


def _usage_text() -> str:
    return (
        "Использование:\n"
        "/chart_ai BTCUSDT\n"
        "/chart_ai BTCUSDT D\n"
        "/chart_ai ETHUSDT 4H"
    )


def _format_percent(value: float) -> str:
    return f"{value * 100:.1f}%"


@sync_to_async
def _analyze_for_user(message: types.Message, symbol: str, interval: str) -> dict:
    from chart_vision.services.analyze_symbol import analyze_bybit_symbol_chart

    user, _created = BotUser.objects.get_or_create(
        telegram_id=message.from_user.id,
        defaults={
            "username": message.from_user.username,
            "first_name": message.from_user.first_name,
            "last_name": message.from_user.last_name,
            "language_code": message.from_user.language_code,
        },
    )
    user.username = message.from_user.username
    user.first_name = message.from_user.first_name
    user.last_name = message.from_user.last_name
    user.language_code = message.from_user.language_code
    user.total_commands += 1
    user.save()

    return analyze_bybit_symbol_chart(
        symbol=symbol,
        interval=interval,
        window=30,
        save_result=True,
        user=user,
    )


@router.message(Command("chart_ai"))
async def chart_ai_cmd(message: types.Message):
    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer(_usage_text())
        return

    symbol = parts[1].strip().upper()
    interval = parts[2].strip() if len(parts) >= 3 else "D"

    if not symbol:
        await message.answer(_usage_text())
        return

    progress_message = await message.answer(
        f"Генерирую визуальный анализ Bybit для {symbol} {interval}..."
    )

    try:
        result = await _analyze_for_user(message, symbol, interval)
    except FileNotFoundError:
        await progress_message.edit_text(
            "Модель Chart Vision ещё не обучена или checkpoint не найден.\n\n"
            "Сначала выполните:\n"
            "python manage.py train_chart_vision_model "
            "--dataset ml/datasets/chart_vision --epochs 10"
        )
        return
    except Exception as exc:
        await progress_message.edit_text(
            "Не удалось выполнить визуальный анализ графика.\n\n"
            f"Причина: {exc}"
        )
        return

    probabilities = result["probabilities"]
    predicted_label = LABEL_TRANSLATIONS.get(
        result["predicted_label"],
        result["predicted_label"],
    )

    try:
        await message.answer_photo(FSInputFile(result["image_path"]))
    except Exception:
        await message.answer(f"График сохранён: {result['image_path']}")

    text = (
        "📊 Визуальный анализ графика Bybit\n\n"
        f"Пара: {result['symbol']}\n"
        f"Таймфрейм: {result['interval']}\n"
        "Источник: Bybit Kline API\n\n"
        f"Класс: {predicted_label}\n"
        f"Уверенность: {_format_percent(result['confidence'])}\n\n"
        "Вероятности:\n"
        f"• восходящий тренд: {_format_percent(probabilities.get('uptrend', 0.0))}\n"
        f"• боковое движение: {_format_percent(probabilities.get('sideways', 0.0))}\n"
        f"• нисходящий тренд: {_format_percent(probabilities.get('downtrend', 0.0))}\n\n"
        "⚠️ Результат является экспериментальной аналитической оценкой "
        "и не является финансовой рекомендацией."
    )
    try:
        await progress_message.delete()
    except Exception:
        pass
    await message.answer(text)
