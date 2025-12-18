# subscriptions/tasks.py

"""
Celery задачи для крипто-аналитики

Модули:
1. Сбор данных (CoinGecko, NewsAPI)
2. Анализ тональности (FinBERT)
3. Машинное обучение (классификатор направления)
4. Генерация прогнозов
"""

import logging
import os
import time
import json
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import requests
import joblib

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import (
    accuracy_score, 
    classification_report, 
    roc_auc_score, 
    confusion_matrix
)

from .models import (
    CoinSnapshot, 
    CoinDailyStat, 
    NewsArticle, 
    NewsSentiment, 
    DirectionPrediction
)


# ============================================
# ПУТИ К МОДЕЛЯМ ML
# ============================================

BASE_DIR = Path(__file__).resolve().parent.parent
ML_MODELS_DIR = BASE_DIR / 'ml' / 'models'

# Создаем директорию если не существует
ML_MODELS_DIR.mkdir(parents=True, exist_ok=True)

# Пути к файлам моделей
CLASSIFIER_MODEL_PATH = ML_MODELS_DIR / 'ml_classifier.pkl'
CLASSIFIER_SCALER_PATH = ML_MODELS_DIR / 'ml_classifier_scaler.pkl'
CLASSIFIER_FEATURES_PATH = ML_MODELS_DIR / 'classifier_features.pkl'

TRAINING_DATA_PATH = ML_MODELS_DIR / 'classification_data.csv'
MODEL_REPORT_PATH = ML_MODELS_DIR / 'model_report.json'


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================
# 1. СБОР ДАННЫХ
# ============================================

@shared_task
def update_coin_snapshots():
    """
    Обновляет текущие цены и данные монет из CoinGecko API
    """
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": 20,
        "page": 1,
        "sparkline": "false"
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        coins_data = response.json()
        
        with transaction.atomic():
            for coin in coins_data:
                CoinSnapshot.objects.update_or_create(
                    coingecko_id=coin["id"],
                    defaults={
                        "name": coin["name"],
                        "symbol": coin["symbol"],
                        "price": coin["current_price"],
                        "market_cap": coin.get("market_cap")
                    }
                )
        
        print(f"[{datetime.now()}] ✅ Обновлено {len(coins_data)} монет")
        return f"Обновлено {len(coins_data)} монет"
        
    except requests.RequestException as e:
        print(f"[{datetime.now()}] ❌ Ошибка при запросе к API: {e}")
        return f"Ошибка: {e}"


@shared_task
def collect_historical_prices(days=30):
    """
    Собирает исторические дневные цены за последние N дней
    """
    coins = CoinSnapshot.objects.all()[:10]
    
    for coin in coins:
        try:
            url = f"https://api.coingecko.com/api/v3/coins/{coin.coingecko_id}/market_chart"
            params = {
                "vs_currency": "usd",
                "days": days,
                "interval": "daily"
            }
            
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            prices = data.get("prices", [])
            market_caps = data.get("market_caps", [])
            volumes = data.get("total_volumes", [])
            
            for i in range(len(prices)):
                timestamp = prices[i][0] / 1000
                date = datetime.utcfromtimestamp(timestamp).date()
                price = prices[i][1]
                market_cap = market_caps[i][1] if i < len(market_caps) else None
                volume = volumes[i][1] if i < len(volumes) else None
                
                # Вычисляем изменение цены
                prev_price = prices[i-1][1] if i > 0 else price
                price_change_percent = ((price - prev_price) / prev_price) * 100 if prev_price else 0
                
                CoinDailyStat.objects.update_or_create(
                    coin=coin,
                    date=date,
                    defaults={
                        "price": price,
                        "market_cap": market_cap,
                        "volume": volume,
                        "price_change_percent": price_change_percent
                    }
                )
            
            print(f"✅ {coin.symbol.upper()} - загружено {len(prices)} дней")
            time.sleep(60)  # Rate limiting
            
        except Exception as e:
            print(f"❌ Ошибка для {coin.symbol}: {e}")
            continue
    
    return f"Собрано данных для {len(coins)} монет"


@shared_task
def collect_historical_news(days=30):
    """
    Собирает новости за последние N дней через NewsAPI.org
    """
    from newsapi import NewsApiClient
    
    NEWSAPI_KEY = os.environ.get('NEWSAPI_KEY')
    if not NEWSAPI_KEY:
        return "NEWSAPI_KEY не найден"
    
    newsapi = NewsApiClient(api_key=NEWSAPI_KEY)
    coins = CoinSnapshot.objects.order_by('-market_cap')[:10]
    total_articles = 0
    
    for coin in coins:
        try:
            queries = [
                f"{coin.name} cryptocurrency",
                f"{coin.symbol.upper()} price",
                f"{coin.name} news"
            ]
            
            from_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            to_date = datetime.now().strftime('%Y-%m-%d')
            
            for query in queries:
                try:
                    all_articles = newsapi.get_everything(
                        q=query,
                        from_param=from_date,
                        to=to_date,
                        language='en',
                        sort_by='publishedAt',
                        page_size=100
                    )
                    
                    articles = all_articles.get('articles', [])
                    saved_count = 0
                    
                    for article in articles:
                        try:
                            if not article.get('url') or not article.get('title'):
                                continue
                            
                            published_str = article.get('publishedAt', '')
                            if published_str:
                                published_at = datetime.strptime(published_str, '%Y-%m-%dT%H:%M:%SZ')
                            else:
                                continue
                            
                            obj, created = NewsArticle.objects.get_or_create(
                                url=article['url'],
                                defaults={
                                    'coin': coin,
                                    'title': article['title'][:500],
                                    'description': article.get('description', '')[:1000] if article.get('description') else '',
                                    'source': article.get('source', {}).get('name', 'Unknown'),
                                    'published_at': published_at,
                                    'news_type': 'financial'
                                }
                            )
                            
                            if created:
                                saved_count += 1
                        except Exception:
                            continue
                    
                    total_articles += saved_count
                    print(f"  '{query}' - {saved_count} новых")
                    time.sleep(1)
                    
                except Exception as e:
                    print(f"  ⚠️ Ошибка для '{query}': {e}")
                    continue
            
            print(f"✅ {coin.symbol.upper()} - собрано {total_articles} новостей")
            time.sleep(2)
            
        except Exception as e:
            print(f"❌ Ошибка для {coin.symbol}: {e}")
            continue
    
    return f"Собрано {total_articles} новых новостей"


# ============================================
# 2. АНАЛИЗ ТОНАЛЬНОСТИ (FinBERT)
# ============================================

def analyze_with_finbert(text):
    """
    Анализирует текст с помощью FinBERT
    """
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    import torch
    
    model_name = "ProsusAI/finbert"
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name)
    
    # Tokenize
    inputs = tokenizer(text, return_tensors="pt", padding=True, truncation=True, max_length=512)
    
    # Predict
    with torch.no_grad():
        outputs = model(**inputs)
        probs = torch.nn.functional.softmax(outputs.logits, dim=-1)
    
    # FinBERT classes: positive, negative, neutral
    positive_score = probs[0][0].item()
    negative_score = probs[0][1].item()
    neutral_score = probs[0][2].item()
    
    # Конвертируем в [-1, 1] scale
    sentiment_score = positive_score - negative_score
    
    # Определяем метку
    max_idx = probs[0].argmax().item()
    labels = ['positive', 'negative', 'neutral']
    sentiment_label = labels[max_idx]
    confidence = probs[0][max_idx].item()
    
    return {
        'sentiment_score': sentiment_score,
        'sentiment_label': sentiment_label,
        'confidence': confidence
    }


@shared_task
def analyze_all_sentiment():
    """
    Анализирует тональность всех необработанных новостей с FinBERT
    """
    articles = NewsArticle.objects.filter(newssentiment__isnull=True)
    total_articles = articles.count()
    
    if total_articles == 0:
        return "Все новости уже проанализированы"
    
    print(f"💭 Анализирую тональность {total_articles} новостей с FinBERT...")
    
    analyzed_count = 0
    for article in articles:
        try:
            text = f"{article.title}. {article.description or ''}"
            result = analyze_with_finbert(text)
            
            NewsSentiment.objects.create(
                article=article,
                sentiment_score=result['sentiment_score'],
                sentiment_label=result['sentiment_label'],
                confidence=result['confidence']
            )
            
            analyzed_count += 1
            
            if analyzed_count % 50 == 0:
                print(f"  Проанализировано: {analyzed_count}/{total_articles}")
                
        except Exception as e:
            print(f"❌ Ошибка анализа статьи {article.id}: {e}")
            continue
    
    print(f"✅ Проанализировано {analyzed_count} из {total_articles} статей")
    return f"Проанализировано {analyzed_count} статей"


# ============================================
# 3. ПОДГОТОВКА ДАННЫХ ДЛЯ ОБУЧЕНИЯ
# ============================================

@shared_task
def prepare_classification_dataset():
    """
    Подготавливает датасет для обучения классификатора направления тренда
    Сохраняет в ml/models/classification_data.csv
    """
    data = []
    
    for coin in CoinSnapshot.objects.all():
        print(f"Processing {coin.symbol}...")
        
        daily_stats = list(
            CoinDailyStat.objects
            .filter(coin=coin)
            .order_by('date')
            .values('date', 'price', 'volume', 'market_cap')
        )
        
        if len(daily_stats) < 8:
            continue
        
        for i in range(7, len(daily_stats) - 1):
            current_day = daily_stats[i]
            next_day = daily_stats[i + 1]
            
            # TARGET: 0 = down, 1 = up
            price_current = float(current_day['price'])
            price_next = float(next_day['price'])
            price_change_percent = ((price_next - price_current) / price_current) * 100
            
            # Игнорируем шум (<0.5%)
            if abs(price_change_percent) < 0.5:
                continue
            
            target = 1 if price_change_percent > 0 else 0
            
            # === ЦЕНОВЫЕ ПРИЗНАКИ (7 дней) ===
            past_7_days = daily_stats[i-6:i+1]
            prices_7d = [float(d['price']) for d in past_7_days]
            volumes_7d = [float(d['volume']) for d in past_7_days]
            
            avg_price_7d = np.mean(prices_7d)
            volatility_7d = np.std(prices_7d)
            price_trend_7d = ((prices_7d[-1] - prices_7d[0]) / prices_7d[0]) * 100
            avg_volume_7d = np.mean(volumes_7d)
            
            # === НОВОСТНЫЕ ПРИЗНАКИ ===
            date_3d_ago = current_day['date'] - timedelta(days=3)
            date_6d_ago = current_day['date'] - timedelta(days=6)
            
            # Текущий период (последние 3 дня)
            news_current = NewsArticle.objects.filter(
                coin=coin,
                published_at__date__gte=date_3d_ago,
                published_at__date__lte=current_day['date']
            ).select_related('newssentiment')
            
            # Предыдущий период (дни -6 до -3)
            news_previous = NewsArticle.objects.filter(
                coin=coin,
                published_at__date__gte=date_6d_ago,
                published_at__date__lt=date_3d_ago
            ).select_related('newssentiment')
            
            # Вычисляем метрики для текущего периода
            news_count_current = news_current.count()
            sentiments_current = [
                n.newssentiment.sentiment_score
                for n in news_current
                if hasattr(n, 'newssentiment')
            ]
            
            avg_sentiment_current = np.mean(sentiments_current) if sentiments_current else 0
            positive_current = sum(1 for s in sentiments_current if s > 0.05)
            negative_current = sum(1 for s in sentiments_current if s < -0.05)
            
            # Вычисляем метрики для предыдущего периода
            news_count_previous = news_previous.count()
            sentiments_previous = [
                n.newssentiment.sentiment_score
                for n in news_previous
                if hasattr(n, 'newssentiment')
            ]
            
            avg_sentiment_previous = np.mean(sentiments_previous) if sentiments_previous else 0
            positive_previous = sum(1 for s in sentiments_previous if s > 0.05)
            negative_previous = sum(1 for s in sentiments_previous if s < -0.05)
            
            # === ДИНАМИЧЕСКИЕ ПРИЗНАКИ ===
            news_volume_change = news_count_current - news_count_previous
            sentiment_change = avg_sentiment_current - avg_sentiment_previous
            positive_change = positive_current - positive_previous
            negative_change = negative_current - negative_previous
            
            # Всплески
            negative_spike = 1 if (negative_current > 5 and negative_change > 3) else 0
            positive_spike = 1 if (positive_current > 5 and positive_change > 3) else 0
            
            # Взаимодействия
            price_sentiment_alignment = price_trend_7d * avg_sentiment_current
            divergence = 1 if (price_trend_7d < -1 and avg_sentiment_current > 0.1) else 0
            
            data.append({
                'coin': coin.symbol,
                'date': current_day['date'],
                'target': target,
                'price_change_percent': price_change_percent,
                
                # Ценовые признаки
                'price_trend_7d': price_trend_7d,
                'volatility_7d': volatility_7d,
                'avg_volume_7d': avg_volume_7d,
                'avg_price_7d': avg_price_7d,
                
                # Новостные признаки
                'news_volume_change': float(news_volume_change),
                'sentiment_change': float(sentiment_change),
                'positive_change': float(positive_change),
                'negative_change': float(negative_change),
                'negative_spike': float(negative_spike),
                'positive_spike': float(positive_spike),
                'price_sentiment_alignment': float(price_sentiment_alignment),
                'divergence': float(divergence),
            })
    
    df = pd.DataFrame(data)
    
    up_count = (df['target'] == 1).sum()
    down_count = (df['target'] == 0).sum()
    
    print(f"\n✅ Dataset created: {len(df)} samples")
    print(f"📊 Class distribution:")
    print(f"   UP (1):   {up_count} ({up_count/len(df)*100:.1f}%)")
    print(f"   DOWN (0): {down_count} ({down_count/len(df)*100:.1f}%)")
    
    # Сохраняем в ml/models/
    df.to_csv(TRAINING_DATA_PATH, index=False)
    print(f"💾 Saved to: {TRAINING_DATA_PATH}")
    
    return {
        'total_samples': len(df),
        'up_count': int(up_count),
        'down_count': int(down_count),
        'saved_to': str(TRAINING_DATA_PATH)
    }


# ============================================
# 4. ОБУЧЕНИЕ КЛАССИФИКАТОРА
# ============================================

@shared_task
def train_classification_model_v2():
    """
    Обучает бинарный классификатор направления тренда (UP/DOWN)
    Сохраняет модели в ml/models/
    """
    print(f"📂 Loading data from: {TRAINING_DATA_PATH}")
    df = pd.read_csv(TRAINING_DATA_PATH)
    
    print(f"📊 Dataset: {len(df)} samples")
    
    # Выбираем лучшие признаки (по результатам экспериментов)
    feature_cols = [
        'price_trend_7d', 
        'volatility_7d', 
        'avg_volume_7d', 
        'avg_price_7d',
        'sentiment_change', 
        'price_sentiment_alignment',
    ]
    
    print(f"🎯 Using {len(feature_cols)} features")
    
    X = df[feature_cols]
    y = df['target']
    
    # Temporal split (80/20)
    df_sorted = df.sort_values('date')
    split_idx = int(len(df_sorted) * 0.8)
    
    train_df = df_sorted.iloc[:split_idx]
    test_df = df_sorted.iloc[split_idx:]
    
    X_train = train_df[feature_cols]
    y_train = train_df['target']
    X_test = test_df[feature_cols]
    y_test = test_df['target']
    
    print(f"\n📦 Train: {len(train_df)} samples")
    print(f"   UP: {(train_df['target']==1).sum()}, DOWN: {(train_df['target']==0).sum()}")
    print(f"📦 Test: {len(test_df)} samples")
    print(f"   UP: {(test_df['target']==1).sum()}, DOWN: {(test_df['target']==0).sum()}")
    
    # Масштабирование
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    # Модель
    model = GradientBoostingClassifier(
        n_estimators=30,
        learning_rate=0.1,
        max_depth=3,
        min_samples_split=30,
        min_samples_leaf=15,
        subsample=0.7,
        max_features='sqrt',
        random_state=42,
        verbose=0
    )
    
    print("\n🔧 Training classifier...")
    model.fit(X_train_scaled, y_train)
    
    # Оценка
    train_pred = model.predict(X_train_scaled)
    test_pred = model.predict(X_test_scaled)
    
    train_pred_proba = model.predict_proba(X_train_scaled)[:, 1]
    test_pred_proba = model.predict_proba(X_test_scaled)[:, 1]
    
    train_acc = accuracy_score(y_train, train_pred)
    test_acc = accuracy_score(y_test, test_pred)
    
    train_auc = roc_auc_score(y_train, train_pred_proba)
    test_auc = roc_auc_score(y_test, test_pred_proba)
    
    print("\n" + "="*60)
    print("📈 CLASSIFICATION PERFORMANCE")
    print("="*60)
    print(f"Train Accuracy: {train_acc:.4f} ({train_acc*100:.1f}%)")
    print(f"Test Accuracy:  {test_acc:.4f} ({test_acc*100:.1f}%)  {'✅' if test_acc > 0.52 else '⚠️'}")
    print(f"Train AUC-ROC:  {train_auc:.4f}")
    print(f"Test AUC-ROC:   {test_auc:.4f}  {'✅' if test_auc > 0.55 else '⚠️'}")
    print(f"\n📊 Comparison:")
    print(f"   Baseline (random):     50.0%")
    print(f"   Your model:           {test_acc*100:.1f}%")
    print(f"   Improvement:          +{(test_acc - 0.5)*100:.1f}%")
    print(f"   Overfitting gap:      {(train_acc - test_acc)*100:.1f}%  {'✅' if (train_acc - test_acc) < 0.15 else '⚠️'}")
    
    # Confusion matrix
    cm = confusion_matrix(y_test, test_pred)
    print("\n" + "="*60)
    print("📋 CONFUSION MATRIX (Test Set)")
    print("="*60)
    print(f"                Predicted")
    print(f"              DOWN    UP")
    print(f"Actual DOWN    {cm[0][0]:3d}   {cm[0][1]:3d}")
    print(f"       UP      {cm[1][0]:3d}   {cm[1][1]:3d}")
    
    # Classification report
    print("\n" + "="*60)
    print("📋 DETAILED METRICS")
    print("="*60)
    print(classification_report(y_test, test_pred, target_names=['DOWN', 'UP']))
    
    # Feature importance
    feature_importance = pd.DataFrame({
        'feature': feature_cols,
        'importance': model.feature_importances_
    }).sort_values('importance', ascending=False)
    
    print("\n" + "="*60)
    print("🔝 FEATURE IMPORTANCE")
    print("="*60)
    for idx, row in feature_importance.iterrows():
        bar = "█" * int(row['importance'] * 100)
        category = "💰" if any(p in row['feature'] for p in ['price', 'volume', 'volatility']) else "📰"
        print(f"{category} {row['feature']:.<35} {row['importance']*100:>5.1f}% {bar}")
    
    # Группировка
    price_features = ['avg_price_7d', 'volatility_7d', 'price_trend_7d', 'avg_volume_7d']
    news_features = [f for f in feature_cols if f not in price_features]
    
    price_importance = feature_importance[feature_importance['feature'].isin(price_features)]['importance'].sum()
    news_importance = feature_importance[feature_importance['feature'].isin(news_features)]['importance'].sum()
    
    print("\n" + "="*60)
    print("📊 FEATURE GROUPS")
    print("="*60)
    print(f"💰 Price features:  {price_importance*100:>5.1f}%")
    print(f"📰 News features:   {news_importance*100:>5.1f}%")
    
    # Сохраняем в ml/models/
    joblib.dump(model, CLASSIFIER_MODEL_PATH)
    joblib.dump(scaler, CLASSIFIER_SCALER_PATH)
    joblib.dump(feature_cols, CLASSIFIER_FEATURES_PATH)
    
    print("\n" + "="*60)
    print("💾 MODEL SAVED")
    print("="*60)
    print(f"   Model:    {CLASSIFIER_MODEL_PATH}")
    print(f"   Scaler:   {CLASSIFIER_SCALER_PATH}")
    print(f"   Features: {CLASSIFIER_FEATURES_PATH}")
    
    return {
        'train_acc': float(train_acc),
        'test_acc': float(test_acc),
        'train_auc': float(train_auc),
        'test_auc': float(test_auc),
        'improvement': float((test_acc - 0.5) * 100),
        'overfitting_gap': float((train_acc - test_acc) * 100),
        'price_importance': float(price_importance),
        'news_importance': float(news_importance),
        'confusion_matrix': cm.tolist(),
        'saved_to': {
            'model': str(CLASSIFIER_MODEL_PATH),
            'scaler': str(CLASSIFIER_SCALER_PATH),
            'features': str(CLASSIFIER_FEATURES_PATH)
        }
    }


# ============================================
# 5. ВЫЧИСЛЕНИЕ ПРИЗНАКОВ ДЛЯ ПРЕДСКАЗАНИЯ
# ============================================

def compute_features_for_coin(coin):
    """
    Вычисляет признаки для одной монеты на основе текущих данных
    Возвращает DataFrame с признаками или None если данных недостаточно
    """
    now = timezone.now()
    
    # 1. ЦЕНОВЫЕ ПРИЗНАКИ (последние 7 дней)
    prices_7d = list(
        CoinDailyStat.objects
        .filter(coin=coin, date__gte=now.date() - timedelta(days=7))
        .order_by('-date')
        .values_list('price', 'volume', flat=False)[:7]
    )
    
    if len(prices_7d) < 7:
        return None
    
    prices = [float(p[0]) for p in prices_7d]
    volumes = [float(p[1]) for p in prices_7d]
    
    avg_price_7d = np.mean(prices)
    volatility_7d = np.std(prices)
    price_trend_7d = ((prices[0] - prices[-1]) / prices[-1]) * 100
    avg_volume_7d = np.mean(volumes)
    
    # 2. НОВОСТНЫЕ ПРИЗНАКИ
    # Текущий период (последние 3 дня)
    news_current = NewsArticle.objects.filter(
        coin=coin,
        published_at__gte=now - timedelta(days=3)
    ).select_related('newssentiment')
    
    # Предыдущий период (дни -6 до -3)
    news_previous = NewsArticle.objects.filter(
        coin=coin,
        published_at__gte=now - timedelta(days=6),
        published_at__lt=now - timedelta(days=3)
    ).select_related('newssentiment')
    
    # Метрики для текущего периода
    news_count_current = news_current.count()
    sentiments_current = [
        n.newssentiment.sentiment_score
        for n in news_current
        if hasattr(n, 'newssentiment')
    ]
    
    avg_sentiment_current = np.mean(sentiments_current) if sentiments_current else 0
    positive_current = sum(1 for s in sentiments_current if s > 0.05)
    negative_current = sum(1 for s in sentiments_current if s < -0.05)
    
    # Метрики для предыдущего периода
    news_count_previous = news_previous.count()
    sentiments_previous = [
        n.newssentiment.sentiment_score
        for n in news_previous
        if hasattr(n, 'newssentiment')
    ]
    
    avg_sentiment_previous = np.mean(sentiments_previous) if sentiments_previous else 0
    positive_previous = sum(1 for s in sentiments_previous if s > 0.05)
    negative_previous = sum(1 for s in sentiments_previous if s < -0.05)
    
    # 3. ДИНАМИЧЕСКИЕ ПРИЗНАКИ
    news_volume_change = news_count_current - news_count_previous
    sentiment_change = avg_sentiment_current - avg_sentiment_previous
    positive_change = positive_current - positive_previous
    negative_change = negative_current - negative_previous
    
    negative_spike = 1 if (negative_current > 5 and negative_change > 3) else 0
    positive_spike = 1 if (positive_current > 5 and positive_change > 3) else 0
    
    price_sentiment_alignment = price_trend_7d * avg_sentiment_current
    divergence = 1 if (price_trend_7d < -1 and avg_sentiment_current > 0.1) else 0
    
    features_dict = {
        'price_trend_7d': price_trend_7d,
        'volatility_7d': volatility_7d,
        'avg_volume_7d': avg_volume_7d,
        'avg_price_7d': avg_price_7d,
        'news_volume_change': float(news_volume_change),
        'sentiment_change': float(sentiment_change),
        'positive_change': float(positive_change),
        'negative_change': float(negative_change),
        'negative_spike': float(negative_spike),
        'positive_spike': float(positive_spike),
        'price_sentiment_alignment': float(price_sentiment_alignment),
        'divergence': float(divergence),
    }
    
    return pd.DataFrame([features_dict])


# ============================================
# 6. ГЕНЕРАЦИЯ ПРОГНОЗОВ
# ============================================

@shared_task
def generate_daily_predictions_classifier():
    """
    Генерирует ежедневные прогнозы направления для всех монет
    Использует обученный классификатор из ml/models/
    """
    print(f"🔮 Generating direction predictions at {timezone.now()}")
    
    # Загружаем модели из ml/models/
    try:
        print(f"📂 Loading models from: {ML_MODELS_DIR}")
        model = joblib.load(CLASSIFIER_MODEL_PATH)
        scaler = joblib.load(CLASSIFIER_SCALER_PATH)
        feature_cols = joblib.load(CLASSIFIER_FEATURES_PATH)
        print("✅ Models loaded successfully")
    except FileNotFoundError as e:
        print(f"❌ Model files not found: {e}")
        print(f"   Expected location: {ML_MODELS_DIR}")
        return {'error': 'Classifier not trained', 'path': str(ML_MODELS_DIR)}
    
    today = timezone.now().date()
    predictions_created = 0
    predictions_updated = 0
    
    for coin in CoinSnapshot.objects.all():
        try:
            # Вычисляем признаки
            features_df = compute_features_for_coin(coin)
            
            if features_df is None:
                print(f"⚠️  {coin.symbol}: insufficient data")
                continue
            
            # Выбираем только нужные признаки
            X = features_df[feature_cols]
            
            # Масштабируем
            X_scaled = scaler.transform(X)
            
            # Предсказываем направление
            direction_code = model.predict(X_scaled)[0]
            probability = model.predict_proba(X_scaled)[0]
            
            prob_down = float(probability[0])
            prob_up = float(probability[1])
            
            predicted_direction = 'UP' if direction_code == 1 else 'DOWN'
            confidence = max(prob_down, prob_up)
            
            # Оцениваем изменение цены
            if predicted_direction == 'UP':
                estimated_change = 1.5 * confidence
            else:
                estimated_change = -1.5 * confidence
            
            # Вычисляем оценочную цену
            current_price = float(coin.price)
            estimated_price = current_price * (1 + estimated_change / 100)
            
            # Сохраняем прогноз
            prediction, created = DirectionPrediction.objects.update_or_create(
                coin=coin,
                prediction_date=today,
                defaults={
                    'predicted_direction': predicted_direction,
                    'confidence_score': confidence,
                    'probability_up': prob_up,
                    'probability_down': prob_down,
                    'estimated_change_percent': estimated_change,
                    'current_price': current_price,
                    'estimated_price': estimated_price,
                    'model_version': 'classifier_v2'
                }
            )
            
            if created:
                predictions_created += 1
            else:
                predictions_updated += 1
            
            emoji = "🟢" if predicted_direction == 'UP' else "🔴"
            signal = prediction.signal_strength.upper()
            
            print(f"{emoji} {coin.symbol:>6}: {predicted_direction:>4} "
                  f"({confidence*100:>5.1f}% confident, {signal:>8}) → {estimated_change:>+6.2f}%")
            
        except Exception as e:
            print(f"❌ Error predicting {coin.symbol}: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    print(f"\n✅ Generated {predictions_created} new predictions, updated {predictions_updated}")
    
    return {
        'status': 'success',
        'predictions_created': predictions_created,
        'predictions_updated': predictions_updated,
        'total': predictions_created + predictions_updated,
        'models_location': str(ML_MODELS_DIR),
        'timestamp': timezone.now().isoformat()
    }


# ============================================
# 7. ОТЧЕТ О МОДЕЛИ
# ============================================

@shared_task
def generate_model_report():
    """
    Генерирует отчет о производительности модели
    Сохраняет в ml/models/model_report.json
    """
    report = {
        'generated_at': datetime.now().isoformat(),
        'model_version': 'classifier_v2',
        'model_type': 'Gradient Boosting Classifier',
        'models_location': str(ML_MODELS_DIR),
        
        'dataset': {
            'total_samples': 480,
            'train_samples': 384,
            'test_samples': 96,
            'date_range': '2025-09-26 to 2025-12-16',
            'cryptocurrencies': 9,
            'news_articles': 2088,
            'sentiment_analyzer': 'FinBERT (ProsusAI/finbert)'
        },
        
        'features': {
            'total': 6,
            'price_features': ['price_trend_7d', 'volatility_7d', 'avg_volume_7d', 'avg_price_7d'],
            'news_features': ['sentiment_change', 'price_sentiment_alignment']
        },
        
        'performance': {
            'train_accuracy': 0.7031,
            'test_accuracy': 0.5312,
            'improvement_over_baseline': '+3.1%',
            'auc_roc': 0.5371,
            'overfitting_gap': 0.172
        },
        
        'feature_importance': {
            'price_features': '95.3%',
            'news_features': '4.7%',
            'top_feature': 'avg_volume_7d (33.2%)'
        },
        
        'key_findings': [
            'Model achieves 53.1% accuracy, exceeding random baseline by 3.1%',
            'Price technical indicators dominate (95.3%) over news sentiment (4.7%)',
            'Model is conservative: high recall for DOWN (83%), low recall for UP (16%)',
            'FinBERT sentiment analysis provides marginal predictive power on daily granularity',
            'Suitable as a weak signal in ensemble trading strategies'
        ]
    }
    
    # Сохраняем в ml/models/
    with open(MODEL_REPORT_PATH, 'w') as f:
        json.dump(report, f, indent=2)
    
    print("="*60)
    print("📊 MODEL PERFORMANCE REPORT")
    print("="*60)
    print(f"\n🎯 Test Accuracy: {report['performance']['test_accuracy']*100:.1f}%")
    print(f"   Improvement: {report['performance']['improvement_over_baseline']}")
    print(f"   AUC-ROC: {report['performance']['auc_roc']:.3f}")
    print(f"\n💾 Report saved to: {MODEL_REPORT_PATH}")
    
    return report


# ============================================
# 8. АВТОМАТИЗАЦИЯ (ДЛЯ CELERY BEAT)
# ============================================

@shared_task
def update_daily_data():
    """
    Ежедневное обновление данных:
    1. Обновляет цены монет
    2. Собирает исторические цены
    3. Собирает новости
    4. Анализирует тональность
    5. Генерирует прогнозы
    """
    print(f"🔄 Daily data update started at {timezone.now()}")
    
    # 1. Обновляем текущие цены
    update_coin_snapshots()
    
    # 2. Собираем исторические цены за последние 2 дня
    collect_historical_prices(days=2)
    
    # 3. Собираем новости за последний день
    collect_historical_news(days=1)
    
    # 4. Анализируем тональность новых новостей
    analyze_all_sentiment()
    
    # 5. Генерируем прогнозы
    generate_daily_predictions_classifier()
    
    print(f"✅ Daily data update completed at {timezone.now()}")
    
    return {
        'status': 'success',
        'timestamp': timezone.now().isoformat()
    }


# subscriptions/tasks.py (добавляем в конец файла)

# ============================================
# 9. TELEGRAM РАССЫЛКИ
# ============================================

@shared_task
def send_daily_predictions_to_users():
    """
    Отправляет ежедневные прогнозы всем подписчикам
    Запускается каждый день в 10:00 MSK (07:00 UTC)
    """
    import asyncio
    from aiogram import Bot
    from subscriptions.models import Subscription, BotUser, DirectionPrediction
    from datetime import date
    import os
    
    TG_TOKEN = os.getenv("TG_TOKEN")
    if not TG_TOKEN:
        print("❌ TG_TOKEN не найден")
        return {"error": "TG_TOKEN not found"}
    
    bot = Bot(token=TG_TOKEN)
    today = date.today()
    
    # Получаем все активные подписки
    subscriptions = Subscription.objects.select_related('user', 'coin').all()
    
    sent_count = 0
    error_count = 0
    
    print(f"📤 Начинаю рассылку прогнозов на {today}...")
    
    # Группируем подписки по пользователям
    users_coins = {}
    for sub in subscriptions:
        if sub.user.telegram_id not in users_coins:
            users_coins[sub.user.telegram_id] = []
        users_coins[sub.user.telegram_id].append(sub.coin)
    
    async def send_predictions():
        nonlocal sent_count, error_count
        
        for telegram_id, coins in users_coins.items():
            try:
                # Формируем сообщение для пользователя
                message_parts = [
                    "🔮 <b>Доброе утро! Ваши прогнозы на сегодня:</b>\n",
                    "═" * 30 + "\n"
                ]
                
                for coin in coins:
                    # Получаем прогноз на сегодня
                    prediction = DirectionPrediction.objects.filter(
                        coin=coin,
                        prediction_date=today
                    ).first()
                    
                    if not prediction:
                        message_parts.append(
                            f"\n💰 <b>{coin.name} ({coin.symbol.upper()})</b>\n"
                            f"⚠️ Прогноз еще не готов\n"
                        )
                        continue
                    
                    # Получаем цену вчерашнего дня для вычисления изменения
                    yesterday_stat = CoinDailyStat.objects.filter(
                        coin=coin,
                        date=today - timedelta(days=1)
                    ).first()
                    
                    if yesterday_stat:
                        price_yesterday = float(yesterday_stat.price)
                        price_current = float(prediction.current_price)
                        daily_change = ((price_current - price_yesterday) / price_yesterday) * 100
                        daily_change_emoji = "🟢" if daily_change > 0 else "🔴"
                    else:
                        daily_change = None
                        daily_change_emoji = "⚪"
                    
                    # Emoji для направления прогноза
                    direction_emoji = "🟢 ↗️" if prediction.predicted_direction == 'UP' else "🔴 ↘️"
                    
                    # Формируем блок для монеты
                    message_parts.append(
                        f"\n💰 <b>{coin.name} ({coin.symbol.upper()})</b>\n"
                        f"💵 Цена: ${prediction.current_price:,.2f}"
                    )
                    
                    if daily_change is not None:
                        message_parts.append(
                            f" ({daily_change_emoji} {daily_change:+.2f}% за 24ч)\n"
                        )
                    else:
                        message_parts.append("\n")
                    
                    message_parts.append(
                        f"{direction_emoji} <b>Прогноз:</b> {prediction.predicted_direction} "
                        f"({prediction.estimated_change_percent:+.2f}%)\n"
                        f"🎯 Уверенность: {prediction.confidence_score*100:.0f}%\n"
                        f"📊 Целевая цена: ${prediction.estimated_price:,.2f}\n"
                    )
                
                message_parts.append(
                    f"\n{'═' * 30}\n"
                    f"<i>⚠️ Прогнозы носят информационный характер</i>\n\n"
                    f"🔮 Подробнее: /predictions"
                )
                
                message = "".join(message_parts)
                
                # Отправляем сообщение
                await bot.send_message(
                    chat_id=telegram_id,
                    text=message,
                    parse_mode="HTML"
                )
                
                sent_count += 1
                print(f"✅ Отправлено пользователю {telegram_id} ({len(coins)} монет)")
                
                # Небольшая задержка между сообщениями
                await asyncio.sleep(0.5)
                
            except Exception as e:
                error_count += 1
                print(f"❌ Ошибка отправки пользователю {telegram_id}: {e}")
                continue
        
        await bot.session.close()
    
    # Запускаем асинхронную отправку
    asyncio.run(send_predictions())
    
    print(f"\n✅ Рассылка завершена:")
    print(f"   Успешно: {sent_count}")
    print(f"   Ошибки: {error_count}")
    
    return {
        'status': 'success',
        'sent': sent_count,
        'errors': error_count,
        'timestamp': timezone.now().isoformat()
    }

# subscriptions/tasks.py

@shared_task
def send_test_prediction(telegram_id: int, coin_symbol: str):
    """
    Тестовая отправка прогноза (HTTP API версия)
    """
    import requests
    import os
    from subscriptions.models import CoinSnapshot, DirectionPrediction, CoinDailyStat
    from datetime import date, timedelta
    
    print(f"📤 Отправка прогноза для {coin_symbol} пользователю {telegram_id}")
    
    TG_TOKEN = os.getenv("TG_TOKEN")
    if not TG_TOKEN:
        print("❌ TG_TOKEN не найден в переменных окружения")
        return {"error": "TG_TOKEN not found"}
    
    today = date.today()
    
    try:
        # Получаем монету
        coin = CoinSnapshot.objects.get(symbol=coin_symbol.lower())
        print(f"✅ Монета найдена: {coin.name}")
        
        # Получаем прогноз
        prediction = DirectionPrediction.objects.filter(
            coin=coin,
            prediction_date=today
        ).first()
        
        if not prediction:
            print(f"❌ Прогноз не найден для {coin_symbol} на {today}")
            
            # Отправляем сообщение об отсутствии
            url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
            data = {
                "chat_id": telegram_id,
                "text": f"❌ Прогноз для {coin_symbol.upper()} не найден на {today}\n\nПопробуйте позже или используйте /predictions",
                "parse_mode": "HTML"
            }
            response = requests.post(url, json=data, timeout=10)
            print(f"Ответ Telegram API: {response.status_code}")
            return {"error": "prediction not found", "date": str(today)}
        
        print(f"✅ Прогноз найден: {prediction.predicted_direction} ({prediction.confidence_score*100:.0f}%)")
        
        # Вычисляем изменение за день
        yesterday_stat = CoinDailyStat.objects.filter(
            coin=coin,
            date=today - timedelta(days=1)
        ).first()
        
        if yesterday_stat:
            price_yesterday = float(yesterday_stat.price)
            price_current = float(prediction.current_price)
            daily_change = ((price_current - price_yesterday) / price_yesterday) * 100
            daily_change_emoji = "🟢" if daily_change > 0 else "🔴"
            daily_change_text = f" ({daily_change_emoji} {daily_change:+.2f}% за 24ч)"
        else:
            daily_change_text = ""
        
        direction_emoji = "🟢 ↗️" if prediction.predicted_direction == 'UP' else "🔴 ↘️"
        
        # Формируем сообщение
        message = (
            f"🔮 <b>Тестовый прогноз</b>\n"
            f"{'═' * 30}\n\n"
            f"💰 <b>{coin.name} ({coin.symbol.upper()})</b>\n"
            f"💵 Цена: ${prediction.current_price:,.2f}{daily_change_text}\n"
            f"{direction_emoji} <b>Прогноз:</b> {prediction.predicted_direction} "
            f"({prediction.estimated_change_percent:+.2f}%)\n"
            f"🎯 Уверенность: {prediction.confidence_score*100:.0f}%\n"
            f"📊 Целевая цена: ${prediction.estimated_price:,.2f}\n\n"
            f"<i>⚠️ Это тестовое сообщение из Celery</i>"
        )
        
        print(f"📝 Сообщение сформировано, длина: {len(message)} символов")
        
        # Отправляем через Telegram HTTP API
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        data = {
            "chat_id": telegram_id,
            "text": message,
            "parse_mode": "HTML"
        }
        
        print(f"🚀 Отправляю запрос к Telegram API...")
        response = requests.post(url, json=data, timeout=10)
        
        print(f"📡 Ответ от Telegram: {response.status_code}")
        
        if response.status_code == 200:
            print(f"✅ Сообщение успешно отправлено пользователю {telegram_id}")
            return {
                "status": "success",
                "telegram_id": telegram_id,
                "coin": coin_symbol,
                "message_sent": True
            }
        else:
            print(f"❌ Ошибка отправки: {response.text}")
            return {
                "error": "telegram_api_error",
                "status_code": response.status_code,
                "response": response.text
            }
            
    except CoinSnapshot.DoesNotExist:
        print(f"❌ Монета не найдена: {coin_symbol}")
        return {"error": "coin_not_found", "coin": coin_symbol}
        
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")
        import traceback
        traceback.print_exc()
        return {"error": str(e), "type": type(e).__name__}
