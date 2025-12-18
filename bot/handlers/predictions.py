# bot/handlers/predictions.py

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from asgiref.sync import sync_to_async
from datetime import date

from subscriptions.models import DirectionPrediction, CoinSnapshot

router = Router()


@router.message(Command("predictions"))
async def predictions_cmd(message: Message):
    """
    Команда /predictions - показывает список монет с доступными прогнозами
    С актуальными ценами из CoinSnapshot
    """
    @sync_to_async
    def get_predictions_with_actual_prices():
        today = date.today()
        
        # Получаем прогнозы
        predictions = DirectionPrediction.objects.filter(
            prediction_date=today
        ).select_related('coin').order_by('-confidence_score')[:10]
        
        # Обновляем актуальные цены из CoinSnapshot
        result = []
        for p in predictions:
            p.coin.refresh_from_db()  # Подтягиваем свежую цену
            result.append(p)
        
        return result
    
    predictions = await get_predictions_with_actual_prices()
    
    if not predictions:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="h0me")]
        ])
        await message.answer(
            "📊 Прогнозы еще не готовы.\n\n"
            "Прогнозы генерируются автоматически каждый день в 01:00 UTC (04:00 МСК).\n"
            "Попробуйте позже!",
            reply_markup=keyboard
        )
        return
    
    # Формируем клавиатуру с актуальными ценами
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"{'🟢' if p.predicted_direction == 'UP' else '🔴'} {p.coin.name} (${p.coin.price:,.2f}) - {p.confidence_score*100:.0f}%",
                callback_data=f"pred_{p.coin.symbol}"
            )]
            for p in predictions
        ] + [
            [InlineKeyboardButton(text="🔄 Обновить цены", callback_data="predictions_refresh")],
            [InlineKeyboardButton(text="📄 Следующая страница", callback_data="predictions2")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="h0me")]
        ]
    )
    
    # Считаем статистику
    bullish = sum(1 for p in predictions if p.predicted_direction == 'UP')
    bearish = sum(1 for p in predictions if p.predicted_direction == 'DOWN')
    
    await message.answer(
        f"🔮 <b>Прогнозы на сегодня</b>\n\n"
        f"📊 Рыночный настрой:\n"
        f"🟢 Рост: {bullish}\n"
        f"🔴 Падение: {bearish}\n\n"
        f"💰 Цены актуальные\n\n"
        f"Выберите монету для подробного прогноза и подписки:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


@router.callback_query(lambda c: c.data == "predictions_refresh")
async def predictions_refresh(query: CallbackQuery):
    """
    Обновляет цены и показывает список заново
    """
    await query.answer("🔄 Обновляю...")
    await predictions_cmd(query.message)


@router.callback_query(lambda c: c.data == "predictions2")
async def predictions_page_2(query: CallbackQuery):
    """
    Вторая страница прогнозов (монеты 11-20)
    """
    @sync_to_async
    def get_predictions_page2():
        today = date.today()
        predictions = DirectionPrediction.objects.filter(
            prediction_date=today
        ).select_related('coin').order_by('-confidence_score')[10:20]
        
        result = []
        for p in predictions:
            p.coin.refresh_from_db()
            result.append(p)
        
        return result
    
    predictions = await get_predictions_page2()
    
    if not predictions:
        await query.answer("Больше прогнозов нет")
        return
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text=f"{'🟢' if p.predicted_direction == 'UP' else '🔴'} {p.coin.name} (${p.coin.price:,.2f}) - {p.confidence_score*100:.0f}%",
                callback_data=f"pred_{p.coin.symbol}"
            )]
            for p in predictions
        ] + [
            [InlineKeyboardButton(text="⬅️ Первая страница", callback_data="predictions")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="h0me")]
        ]
    )
    
    await query.message.edit_text(
        "🔮 <b>Прогнозы на сегодня (стр. 2)</b>\n\n"
        "Выберите монету для подробного прогноза:",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await query.answer()


@router.callback_query(lambda q: q.data == "predictions")
async def predictions_callback(query: CallbackQuery):
    """
    Возврат на первую страницу прогнозов
    """
    await predictions_cmd(query.message)
    await query.answer()


@router.callback_query(lambda q: q.data.startswith("pred_"))
async def show_prediction_detail(query: CallbackQuery):
    """
    Показывает детальный прогноз для выбранной монеты с актуальной ценой
    """
    coin_symbol = query.data.replace("pred_", "")
    
    @sync_to_async
    def get_prediction_detail(symbol):
        today = date.today()
        try:
            # Получаем монету (с актуальной ценой)
            coin = CoinSnapshot.objects.get(symbol=symbol)
            
            # Получаем прогноз
            prediction = DirectionPrediction.objects.filter(
                coin=coin,
                prediction_date=today
            ).first()
            
            if not prediction:
                return None, coin, None, None, None
            
            # Пересчитываем целевую цену на основе актуальной
            current_price_actual = float(coin.price)  # АКТУАЛЬНАЯ из CoinSnapshot
            estimated_price_actual = current_price_actual * (1 + prediction.estimated_change_percent / 100)
            
            # Вычисляем изменение с момента создания прогноза
            price_in_prediction = float(prediction.current_price)
            price_change_since_prediction = ((current_price_actual - price_in_prediction) / price_in_prediction) * 100
            
            return prediction, coin, current_price_actual, estimated_price_actual, price_change_since_prediction
            
        except CoinSnapshot.DoesNotExist:
            return None, None, None, None, None
    
    result = await get_prediction_detail(coin_symbol)
    
    if result[0] is None:
        await query.message.answer("❌ Прогноз не найден")
        await query.answer()
        return
    
    prediction, coin, current_price_actual, estimated_price_actual, price_change_since_prediction = result
    
    # Определяем emoji для направления
    direction_emoji = "🟢 ↗️" if prediction.predicted_direction == 'UP' else "🔴 ↘️"
    
    # Определяем силу сигнала
    signal_emoji = {
        'strong': '🔥',
        'moderate': '⚡',
        'weak': '💨'
    }.get(prediction.signal_strength, '❓')
    
    # Определяем как изменилась цена с момента прогноза
    if abs(price_change_since_prediction) > 0.1:
        price_change_emoji = "🟢" if price_change_since_prediction > 0 else "🔴"
        price_change_text = f"\n📊 С момента прогноза: {price_change_emoji} {price_change_since_prediction:+.2f}%"
    else:
        price_change_text = ""
    
    # Формируем красивое сообщение
    message_text = (
        f"🔮 <b>Прогноз для {coin.name}</b>\n"
        f"{'='*30}\n\n"
        
        f"💰 <b>Актуальная цена:</b> ${current_price_actual:,.2f}{price_change_text}\n"
        f"💵 <i>Цена при прогнозе: ${prediction.current_price:,.2f}</i>\n\n"
        
        f"{direction_emoji} <b>Направление:</b> {prediction.predicted_direction}\n"
        f"📊 <b>Оценка изменения:</b> {prediction.estimated_change_percent:+.2f}%\n"
        f"🎯 <b>Целевая цена:</b> ${estimated_price_actual:,.2f}\n\n"
        
        f"📈 <b>Вероятности:</b>\n"
        f"  🟢 Рост: {prediction.probability_up*100:.1f}%\n"
        f"  🔴 Падение: {prediction.probability_down*100:.1f}%\n\n"
        
        f"🎯 <b>Уверенность:</b> {prediction.confidence_score*100:.0f}%\n"
        f"{signal_emoji} <b>Сила сигнала:</b> {prediction.signal_strength.upper()}\n\n"
        
        f"🤖 <b>Модель:</b> {prediction.model_version}\n"
        f"📅 <b>Дата прогноза:</b> {prediction.prediction_date.strftime('%d.%m.%Y')}\n"
        f"⏰ <b>Создан:</b> {prediction.created_at.strftime('%H:%M:%S')}\n\n"
        
        f"<i>⚠️ Прогноз носит информационный характер и не является финансовой рекомендацией.</i>"
    )
    
    # Кнопки навигации
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Пересчитать прогноз", callback_data=f"refresh_pred_{coin.symbol}")],
        [InlineKeyboardButton(text="📬 Подписаться на рассылку", callback_data=f"subscribe_{coin.symbol}")],
        [InlineKeyboardButton(text="⬅️ К списку прогнозов", callback_data="predictions")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="h0me")]
    ])
    
    await query.message.edit_text(
        message_text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await query.answer()


@router.callback_query(lambda q: q.data.startswith("refresh_pred_"))
async def refresh_prediction_realtime(query: CallbackQuery):
    """
    Генерирует свежий прогноз в реальном времени
    """
    from subscriptions.tasks import compute_features_for_coin
    import joblib
    import pandas as pd
    from pathlib import Path
    
    coin_symbol = query.data.replace("refresh_pred_", "")
    
    await query.message.edit_text(
        f"🔄 Генерирую свежий прогноз для {coin_symbol.upper()}...\n"
        f"⏳ Это займет несколько секунд..."
    )
    
    @sync_to_async
    def generate_fresh_prediction(symbol):
        from subscriptions.models import CoinSnapshot, CoinDailyStat
        from datetime import timedelta, date
        import numpy as np
        
        try:
            # 1. Получаем монету
            coin = CoinSnapshot.objects.get(symbol=symbol)
            
            # 2. Загружаем модель
            BASE_DIR = Path(__file__).resolve().parent.parent.parent
            ML_MODELS_DIR = BASE_DIR / 'ml' / 'models'
            
            model = joblib.load(ML_MODELS_DIR / 'ml_classifier.pkl')
            scaler = joblib.load(ML_MODELS_DIR / 'ml_classifier_scaler.pkl')
            feature_cols = joblib.load(ML_MODELS_DIR / 'classifier_features.pkl')
            
            # 3. Вычисляем признаки прямо сейчас
            features_df = compute_features_for_coin(coin)
            
            if features_df is None:
                return None, "Недостаточно данных для прогноза"
            
            # 4. Предсказываем
            X = features_df[feature_cols]
            X_scaled = scaler.transform(X)
            
            direction_code = model.predict(X_scaled)[0]
            probability = model.predict_proba(X_scaled)[0]
            
            prob_down = float(probability[0])
            prob_up = float(probability[1])
            
            predicted_direction = 'UP' if direction_code == 1 else 'DOWN'
            confidence = max(prob_down, prob_up)
            
            # 5. Оцениваем изменение
            if predicted_direction == 'UP':
                estimated_change = 1.5 * confidence
            else:
                estimated_change = -1.5 * confidence
            
            # 6. АКТУАЛЬНАЯ цена из CoinSnapshot
            current_price = float(coin.price)
            estimated_price = current_price * (1 + estimated_change / 100)
            
            # 7. Определяем силу сигнала
            if confidence >= 0.7:
                signal_strength = 'strong'
            elif confidence >= 0.6:
                signal_strength = 'moderate'
            else:
                signal_strength = 'weak'
            
            return {
                'coin': coin,
                'predicted_direction': predicted_direction,
                'confidence_score': confidence,
                'probability_up': prob_up,
                'probability_down': prob_down,
                'estimated_change_percent': estimated_change,
                'current_price': current_price,
                'estimated_price': estimated_price,
                'signal_strength': signal_strength,
                'fresh': True
            }, None
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return None, str(e)
    
    prediction_data, error = await generate_fresh_prediction(coin_symbol)
    
    if error or not prediction_data:
        await query.message.edit_text(
            f"❌ Не удалось сгенерировать прогноз\n\n"
            f"Причина: {error or 'Недостаточно данных'}\n\n"
            f"Попробуйте позже или выберите другую монету.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="predictions")]
            ])
        )
        await query.answer()
        return
    
    # Формируем сообщение
    direction_emoji = "🟢 ↗️" if prediction_data['predicted_direction'] == 'UP' else "🔴 ↘️"
    signal_emoji = {
        'strong': '🔥',
        'moderate': '⚡',
        'weak': '💨'
    }.get(prediction_data['signal_strength'], '❓')
    
    from datetime import datetime
    
    message_text = (
        f"🔮 <b>Свежий прогноз для {prediction_data['coin'].name}</b>\n"
        f"{'='*30}\n"
        f"⏰ <b>Сгенерирован:</b> {datetime.now().strftime('%H:%M:%S')}\n\n"
        
        f"💰 <b>Актуальная цена:</b> ${prediction_data['current_price']:,.2f}\n"
        f"{direction_emoji} <b>Направление:</b> {prediction_data['predicted_direction']}\n"
        f"📊 <b>Оценка изменения:</b> {prediction_data['estimated_change_percent']:+.2f}%\n"
        f"🎯 <b>Целевая цена:</b> ${prediction_data['estimated_price']:,.2f}\n\n"
        
        f"📈 <b>Вероятности:</b>\n"
        f"  🟢 Рост: {prediction_data['probability_up']*100:.1f}%\n"
        f"  🔴 Падение: {prediction_data['probability_down']*100:.1f}%\n\n"
        
        f"🎯 <b>Уверенность:</b> {prediction_data['confidence_score']*100:.0f}%\n"
        f"{signal_emoji} <b>Сила сигнала:</b> {prediction_data['signal_strength'].upper()}\n\n"
        
        f"✨ <b>Это свежий прогноз на основе текущих данных</b>\n\n"
        
        f"<i>⚠️ Прогноз носит информационный характер</i>"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить еще раз", callback_data=f"refresh_pred_{coin_symbol}")],
        [InlineKeyboardButton(text="📬 Подписаться на рассылку", callback_data=f"subscribe_{coin_symbol}")],
        [InlineKeyboardButton(text="⬅️ К списку прогнозов", callback_data="predictions")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="h0me")]
    ])
    
    await query.message.edit_text(
        message_text,
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await query.answer("✅ Прогноз обновлен!")


@router.callback_query(lambda c: c.data.startswith("subscribe_"))
async def subscribe_coin_from_prediction(callback: CallbackQuery):
    """
    Подписка на монету из прогноза
    """
    coin_symbol = callback.data.replace("subscribe_", "")
    telegram_id = callback.from_user.id
    
    @sync_to_async
    def add_subscription():
        from subscriptions.models import BotUser, Subscription
        try:
            coin = CoinSnapshot.objects.get(symbol=coin_symbol.lower())
            user, _ = BotUser.objects.get_or_create(telegram_id=telegram_id)
            subscription, created = Subscription.objects.get_or_create(user=user, coin=coin)
            return coin, created
        except CoinSnapshot.DoesNotExist:
            return None, False
    
    coin, created = await add_subscription()
    
    if not coin:
        await callback.answer("❌ Монета не найдена", show_alert=True)
        return
    
    if created:
        await callback.answer(
            f"✅ Подписка на {coin.name} оформлена!\n"
            f"📬 Прогнозы будут приходить каждый день в 10:00 МСК",
            show_alert=True
        )
    else:
        await callback.answer(
            f"ℹ️ Вы уже подписаны на {coin.name}",
            show_alert=True
        )
