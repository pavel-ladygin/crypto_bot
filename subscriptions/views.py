# subscriptions/views.py

from django.http import JsonResponse
from django.utils import timezone
from .models import DirectionPrediction, CoinSnapshot, PricePrediction

def get_prediction(request, coin_symbol):
    """
    GET /api/predict/btc/
    Возвращает старый формат прогноза (для совместимости)
    """
    try:
        coin = CoinSnapshot.objects.get(symbol=coin_symbol.lower())
        today = timezone.now().date()
        
        prediction = PricePrediction.objects.filter(
            coin=coin,
            prediction_date=today
        ).first()
        
        if not prediction:
            return JsonResponse({
                'error': 'No prediction available for today',
                'coin': coin_symbol,
                'date': today.isoformat()
            }, status=404)
        
        direction = 'UP' if prediction.predicted_change_percent > 0 else 'DOWN'
        
        return JsonResponse({
            'coin': coin.symbol,
            'name': coin.name,
            'prediction_date': prediction.prediction_date.isoformat(),
            'current_price': float(prediction.current_price),
            'predicted_direction': direction,
            'predicted_change': f"{prediction.predicted_change_percent:+.2f}%",
            'predicted_price': float(prediction.predicted_price),
            'confidence': float(prediction.confidence_score) if prediction.confidence_score else None,
            'model_version': prediction.model_version,
            'created_at': prediction.created_at.isoformat()
        })
        
    except CoinSnapshot.DoesNotExist:
        return JsonResponse({'error': 'Coin not found'}, status=404)


def get_all_predictions(request):
    """
    GET /api/predictions/
    Возвращает все старые прогнозы (для совместимости)
    """
    today = timezone.now().date()
    
    predictions = PricePrediction.objects.filter(
        prediction_date=today
    ).select_related('coin').order_by('-confidence_score')
    
    data = []
    for p in predictions:
        direction = 'UP' if p.predicted_change_percent > 0 else 'DOWN'
        
        data.append({
            'coin': p.coin.symbol,
            'name': p.coin.name,
            'current_price': float(p.current_price),
            'predicted_direction': direction,
            'predicted_change': f"{p.predicted_change_percent:+.2f}%",
            'predicted_price': float(p.predicted_price),
            'confidence': float(p.confidence_score) if p.confidence_score else 0.5,
            'signal_strength': 'strong' if (p.confidence_score or 0) > 0.7 else 'weak'
        })
    
    return JsonResponse({
        'date': today.isoformat(),
        'total_predictions': len(data),
        'bullish_count': sum(1 for d in data if d['predicted_direction'] == 'UP'),
        'bearish_count': sum(1 for d in data if d['predicted_direction'] == 'DOWN'),
        'predictions': data
    })


def get_direction_prediction(request, coin_symbol):
    """
    GET /api/direction/btc/
    Возвращает прогноз направления движения на сегодня
    """
    try:
        coin = CoinSnapshot.objects.get(symbol=coin_symbol.lower())
        today = timezone.now().date()
        
        prediction = DirectionPrediction.objects.filter(
            coin=coin,
            prediction_date=today
        ).first()
        
        if not prediction:
            return JsonResponse({
                'error': 'No prediction available for today',
                'coin': coin_symbol,
                'date': today.isoformat()
            }, status=404)
        
        return JsonResponse({
            'coin': coin.symbol,
            'name': coin.name,
            'prediction_date': prediction.prediction_date.isoformat(),
            
            # Направление
            'predicted_direction': prediction.predicted_direction,
            'signal_strength': prediction.signal_strength,
            
            # Уверенность
            'confidence': float(prediction.confidence_score),
            'probability_up': float(prediction.probability_up),
            'probability_down': float(prediction.probability_down),
            
            # Оценка изменения
            'estimated_change_percent': f"{prediction.estimated_change_percent:+.2f}%",
            'current_price': float(prediction.current_price),
            'estimated_price': float(prediction.estimated_price),
            
            # Метаданные
            'model_version': prediction.model_version,
            'created_at': prediction.created_at.isoformat()
        })
        
    except CoinSnapshot.DoesNotExist:
        return JsonResponse({'error': 'Coin not found'}, status=404)


def get_all_direction_predictions(request):
    """
    GET /api/directions/
    Возвращает все прогнозы направлений на сегодня
    """
    today = timezone.now().date()
    
    predictions = DirectionPrediction.objects.filter(
        prediction_date=today
    ).select_related('coin').order_by('-confidence_score')
    
    # Группируем по направлению
    bullish = []
    bearish = []
    
    for p in predictions:
        pred_data = {
            'coin': p.coin.symbol,
            'name': p.coin.name,
            'direction': p.predicted_direction,
            'confidence': float(p.confidence_score),
            'signal_strength': p.signal_strength,
            'estimated_change': f"{p.estimated_change_percent:+.2f}%",
            'current_price': float(p.current_price),
            'estimated_price': float(p.estimated_price)
        }
        
        if p.predicted_direction == 'UP':
            bullish.append(pred_data)
        else:
            bearish.append(pred_data)
    
    # Статистика
    total = len(predictions)
    strong_signals = sum(1 for p in predictions if p.signal_strength == 'strong')
    avg_confidence = sum(p.confidence_score for p in predictions) / total if total > 0 else 0
    
    return JsonResponse({
        'date': today.isoformat(),
        'total_predictions': total,
        'bullish_count': len(bullish),
        'bearish_count': len(bearish),
        'strong_signals': strong_signals,
        'average_confidence': f"{avg_confidence*100:.1f}%",
        
        'market_sentiment': 'bullish' if len(bullish) > len(bearish) else 'bearish',
        
        'predictions': {
            'bullish': bullish,
            'bearish': bearish
        }
    })


def get_model_info(request):
    """
    GET /api/model/info/
    Возвращает информацию о модели из ml/models/model_report.json
    """
    import json
    from pathlib import Path
    
    BASE_DIR = Path(__file__).resolve().parent.parent
    MODEL_REPORT_PATH = BASE_DIR / 'ml' / 'models' / 'model_report.json'
    
    try:
        with open(MODEL_REPORT_PATH, 'r') as f:
            report = json.load(f)
        return JsonResponse(report)
    except FileNotFoundError:
        return JsonResponse({
            'model_version': 'classifier_v2',
            'test_accuracy': 0.531,
            'improvement': '+3.1%',
            'description': 'Binary classifier for crypto price direction prediction',
            'models_location': str(MODEL_REPORT_PATH.parent)
        })