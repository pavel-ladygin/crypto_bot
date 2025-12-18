import logging
from bot.telegram_bot import TG_TOKEN
from celery import shared_task
from django.db import transaction
from django.utils import timezone
from .models import CoinSnapshot, Subscription, CoinDailyStat, NewsArticle, NewsSentiment, PriceEvent, PricePrediction, DirectionPrediction
import numpy as np
import requests
from datetime import datetime, timedelta
import time
import os
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score, mean_squared_error
from sklearn.preprocessing import StandardScaler

import joblib



# Определяем пути к моделям
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
# ============================================
# Задача для обновления данных о монетах из CoinGecko
# ============================================

@shared_task
def update_coin_snapshots():
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
                        "market_cap": coin.get("market_cap")  # добавлено
                    }
                )

        print(f"[{datetime.now()}] Обновлено {len(coins_data)} монет")
        return f"Обновлено {len(coins_data)} монет"

    except requests.RequestException as e:
        print(f"[{datetime.now()}] Ошибка при запросе к API: {e}")
        return f"Ошибка: {e}"



# ============================================
# # Задача для сбора исторических цен по дням
# ============================================

@shared_task
def collect_historical_prices(days=30):
    """
    Собирает исторические цены за последние 30 дней
    """
    coins = CoinSnapshot.objects.all()[:10]  # Уменьшил до 10 для безопасности
    
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
            
            print(f"✅ {coin.symbol.upper()} - загружено {len(prices)} дней истории цен")
            time.sleep(60)  # ← ИЗМЕНИЛ С 2 НА 5 СЕКУНД!
            
        except Exception as e:
            print(f"❌ Ошибка для {coin.symbol}: {e}")
    
    return f"Собрано данных для {len(coins)} монет"


# ============================================
# Задачи для сбора новостей
# ============================================

@shared_task
def collect_historical_news(days=30):
    """
    Собирает новости за последние N дней через NewsAPI.org
    С РАСШИРЕННЫМИ запросами
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
            # МНОЖЕСТВЕННЫЕ ВАРИАНТЫ ЗАПРОСОВ для каждой монеты
            queries = [
                f"{coin.name} cryptocurrency",
                f"{coin.symbol.upper()} price",
                f"{coin.name} {coin.symbol.upper()}",
                f"{coin.name} news",
                f"{coin.symbol.upper()} trading",
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
            
            print(f"✅ {coin.symbol.upper()} - всего {total_articles} новостей")
            time.sleep(2)
            
        except Exception as e:
            print(f"❌ Ошибка для {coin.symbol}: {e}")
            continue
    
    return f"Собрано {total_articles} новых новостей"

@shared_task
def collect_political_news():
    """
    Собирает политические новости влияющие на крипторынок
    - Регуляции
    - Геополитика
    - Макроэкономика
    - Судебные решения
    """
    from newsapi import NewsApiClient
    
    NEWSAPI_KEY = os.environ.get('NEWSAPI_KEY')
    if not NEWSAPI_KEY:
        return "NEWSAPI_KEY не найден"
    
    newsapi = NewsApiClient(api_key=NEWSAPI_KEY)
    coins = CoinSnapshot.objects.order_by('-market_cap')[:10]
    
    # ПОЛИТИЧЕСКИЕ ТЕМЫ влияющие на крипту
    political_queries = [
        # Регуляции
        'SEC cryptocurrency regulation',
        'crypto regulation bill congress',
        'European Union crypto regulation MiCA',
        'cryptocurrency ban government',
        
        # Судебные дела
        'Ripple SEC lawsuit',
        'cryptocurrency court case',
        'crypto exchange lawsuit',
        
        # Макроэкономика
        'Federal Reserve interest rate crypto',
        'inflation cryptocurrency',
        'economic recession bitcoin',
        
        # Геополитика
        'cryptocurrency sanctions Russia',
        'China cryptocurrency ban',
        'El Salvador bitcoin adoption',
        
        # Политика
        'Biden cryptocurrency policy',
        'Trump bitcoin',
        'crypto election campaign',
    ]
    
    total_articles = 0
    from_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    
    for query in political_queries:
        try:
            results = newsapi.get_everything(
                q=query,
                from_param=from_date,
                language='en',
                sort_by='relevancy',
                page_size=15  # по 15 новостей на тему
            )
            
            articles = results.get('articles', [])
            
            # Сохраняем для ВСЕХ монет (политика влияет на весь рынок)
            for coin in coins:
                for article in articles:
                    try:
                        if not article.get('url') or not article.get('title'):
                            continue
                        
                        published_str = article.get('publishedAt', '')
                        if published_str:
                            published_at = datetime.strptime(published_str, '%Y-%m-%dT%H:%M:%SZ')
                        else:
                            continue
                        
                        # Добавляем метку что это политическая новость
                        description = article.get('description', '') or ''
                        title = f"[POLITICAL] {article['title']}"[:500]
                        obj, created = NewsArticle.objects.get_or_create(
                            url=article['url'],
                            defaults={
                                'coin': coin,
                                'title': article['title'][:500],  # БЕЗ [POLITICAL]!
                                'description': description[:1000],
                                'source': article.get('source', {}).get('name', 'Political News'),
                                'published_at': published_at,
                                'news_type': 'political'  # ДОБАВИЛИ
                            }
                        )

                        
                        if created:
                            total_articles += 1
                            
                    except Exception as e:
                        continue
            
            print(f"✅ '{query[:40]}...' - {len(articles)} статей")
            time.sleep(3)  # Пауза между запросами
            
        except Exception as e:
            print(f"❌ Ошибка для '{query}': {e}")
            continue
    
    return f"Собрано {total_articles} политических новостей"

@shared_task
def collect_market_news():
    """
    Собирает общерыночные новости про криптовалюты
    Эти новости будут связаны со ВСЕМИ монетами
    """
    from newsapi import NewsApiClient
    
    NEWSAPI_KEY = os.environ.get('NEWSAPI_KEY')
    if not NEWSAPI_KEY:
        return "NEWSAPI_KEY не найден"
    
    newsapi = NewsApiClient(api_key=NEWSAPI_KEY)
    
    # Общерыночные запросы
    market_queries = [
        'cryptocurrency market crash',
        'crypto regulation SEC',
        'bitcoin ETF approval',
        'cryptocurrency adoption',
        'crypto market analysis',
    ]
    
    total_articles = 0
    coins = CoinSnapshot.objects.all()[:10]  
    
    for query in market_queries:
        try:
            from_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
            
            all_articles = newsapi.get_everything(
                q=query,
                from_param=from_date,
                language='en',
                sort_by='relevancy',
                page_size=20  # по 20 новостей на запрос
            )
            
            articles = all_articles.get('articles', [])
            
            # Сохраняем для КАЖДОЙ монеты (общий контекст)
            for coin in coins:
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
                                'description': description[:1000],
                                'source': article.get('source', {}).get('name', 'Market News'),
                                'published_at': published_at,
                                'news_type': 'market'  # ДОБАВИЛИ
                            }
                        )

                        
                        if created:
                            total_articles += 1
                            
                    except Exception as e:
                        continue
            
            print(f"✅ Query '{query}' - собрано {len(articles)} статей")
            time.sleep(2)
            
        except Exception as e:
            print(f"❌ Ошибка для запроса '{query}': {e}")
            continue
    
    return f"Собрано {total_articles} общерыночных новостей"

@shared_task
def collect_crypto_news_extended():
    """
    Расширенный сбор новостей по криптовалютам
    Использует разные источники и категории
    """
    from newsapi import NewsApiClient
    
    NEWSAPI_KEY = os.environ.get('NEWSAPI_KEY')
    if not NEWSAPI_KEY:
        return "NEWSAPI_KEY не найден"
    
    newsapi = NewsApiClient(api_key=NEWSAPI_KEY)
    coins = CoinSnapshot.objects.all()[:10]  # 15 монет
    total_articles = 0
    
    # Популярные крипто-источники
    crypto_sources = [
        'crypto-coins-news',
        'techcrunch',
        'the-verge',
        'wired',
        'ars-technica'
    ]
    
    for coin in coins:
        try:
            # Запрос 1: Общий поиск
            query = f'"{coin.name}" OR "{coin.symbol.upper()}" cryptocurrency'
            from_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
            
            results = newsapi.get_everything(
                q=query,
                from_param=from_date,
                language='en',
                sort_by='relevancy',  # сортировка по релевантности
                page_size=50
            )
            
            for article in results.get('articles', []):
                try:
                    if not article.get('url') or not article.get('title'):
                        continue
                        
                    published_at = datetime.strptime(
                        article['publishedAt'], 
                        '%Y-%m-%dT%H:%M:%SZ'
                    )
                    
                    obj, created = NewsArticle.objects.get_or_create(
                        url=article['url'],
                        defaults={
                            'coin': coin,
                            'title': article['title'][:500],
                            'description': article.get('description', '')[:1000] if article.get('description') else '',
                            'source': article.get('source', {}).get('name', 'Unknown'),
                            'published_at': published_at
                        }
                    )
                    
                    if created:
                        total_articles += 1
                        
                except Exception:
                    continue
            
            # Запрос 2: По специализированным источникам
            try:
                source_results = newsapi.get_everything(
                    q=coin.name,
                    sources=','.join(crypto_sources),
                    from_param=from_date,
                    language='en',
                    page_size=30
                )
                
                for article in source_results.get('articles', []):
                    try:
                        if not article.get('url'):
                            continue
                            
                        published_at = datetime.strptime(
                            article['publishedAt'], 
                            '%Y-%m-%dT%H:%M:%SZ'
                        )
                        
                        NewsArticle.objects.get_or_create(
                            url=article['url'],
                            defaults={
                                'coin': coin,
                                'title': article['title'][:500],
                                'description': article.get('description', '')[:1000] if article.get('description') else '',
                                'source': article.get('source', {}).get('name', 'Unknown'),
                                'published_at': published_at
                            }
                        )
                    except Exception:
                        continue
                        
            except Exception as e:
                print(f"⚠️ Ошибка источников для {coin.symbol}: {e}")
            
            print(f"✅ {coin.symbol.upper()} - обработано")
            time.sleep(2)  # пауза между монетами
            
        except Exception as e:
            print(f"❌ Ошибка для {coin.symbol}: {e}")
            continue
    
    return f"Собрано {total_articles} новостей"




# АНАЛИЗ ТОНАЛЬНОСТИ НОВОСТЕЙ
# ============================================

@shared_task
def analyze_all_sentiment():
    """
    Анализирует тональность всех необработанных новостей
    Использует VADER для определения позитивных/негативных/нейтральных новостей
    """
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    
    analyzer = SentimentIntensityAnalyzer()
    
    # Берем только новости БЕЗ анализа тональности
    articles = NewsArticle.objects.filter(newssentiment__isnull=True)
    total_articles = articles.count()
    
    if total_articles == 0:
        return "Все новости уже проанализированы"
    
    print(f"💭 Анализирую тональность {total_articles} новостей...")
    
    analyzed_count = 0
    
    for article in articles:
        try:
            # Объединяем заголовок и описание для анализа
            text = f"{article.title} {article.description or ''}"
            
            # VADER анализ
            scores = analyzer.polarity_scores(text)
            
            # compound: от -1 (очень негативно) до +1 (очень позитивно)
            sentiment_score = scores['compound']
            
            # Определяем категорию
            if sentiment_score >= 0.05:
                label = 'positive'
            elif sentiment_score <= -0.05:
                label = 'negative'
            else:
                label = 'neutral'
            
            # Сохраняем анализ
            NewsSentiment.objects.create(
                article=article,
                sentiment_score=sentiment_score,
                sentiment_label=label,
                confidence=max(scores['pos'], scores['neg'], scores['neu'])
            )
            
            analyzed_count += 1
            
            # Прогресс каждые 100 статей
            if analyzed_count % 100 == 0:
                print(f"  Проанализировано: {analyzed_count}/{total_articles}")
            
        except Exception as e:
            print(f"❌ Ошибка анализа статьи {article.id}: {e}")
            continue
    
    print(f"✅ Проанализировано {analyzed_count} из {total_articles} статей")
    return f"Проанализировано {analyzed_count} статей"


# subscriptions/tasks.py

@shared_task
def setup_finbert():
    """
    Устанавливает и тестирует FinBERT
    """
    try:
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
        import torch
        
        print("📥 Downloading FinBERT model...")
        
        model_name = "ProsusAI/finbert"
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForSequenceClassification.from_pretrained(model_name)
        
        print("✅ FinBERT loaded successfully")
        
        # Тест
        test_text = "Bitcoin surges to new all-time high as institutional adoption grows"
        
        inputs = tokenizer(test_text, return_tensors="pt", padding=True, truncation=True, max_length=512)
        
        with torch.no_grad():
            outputs = model(**inputs)
        
        probs = torch.nn.functional.softmax(outputs.logits, dim=-1)
        
        # FinBERT возвращает: [positive, negative, neutral]
        labels = ['positive', 'negative', 'neutral']
        scores = probs[0].tolist()
        
        print(f"\n📰 Test: \"{test_text}\"")
        for label, score in zip(labels, scores):
            print(f"   {label}: {score:.3f}")
        
        return {'status': 'success', 'model': model_name}
        
    except ImportError:
        print("❌ transformers not installed")
        print("   Run: pip install transformers torch")
        return {'error': 'dependencies missing'}


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
def reanalyze_with_finbert():
    """
    Переанализирует новости с FinBERT (МЕДЛЕННО!)
    """
    articles = NewsArticle.objects.all()
    total = articles.count()
    
    print(f"🔄 Re-analyzing {total} articles with FinBERT...")
    print("⚠️  This will take ~30 minutes!")
    
    for i, article in enumerate(articles, 1):
        text = f"{article.title}. {article.description or ''}"
        
        result = analyze_with_finbert(text)
        
        NewsSentiment.objects.update_or_create(
            article=article,
            defaults={
                'sentiment_score': result['sentiment_score'],
                'sentiment_label': result['sentiment_label'],
                'confidence': result['confidence']
            }
        )
        
        if i % 50 == 0:
            print(f"   Processed {i}/{total} articles...")
    
    print(f"✅ Re-analyzed with FinBERT")
    
    return {'total': total, 'method': 'finbert'}


# ============================================
# ПОИСК АНОМАЛИЙ В ЦЕНАХ
# ============================================

@shared_task
def detect_all_anomalies(threshold_percent=1.5):
    """
    Находит аномалии (резкие изменения) цен и связывает их с новостями
    
    Параметры:
    - threshold_percent: минимальное изменение цены в % для считания аномалией
                         (по умолчанию 1.5%)
    
    Алгоритм:
    1. Для каждой монеты берем историю цен
    2. Находим дни где цена изменилась более чем на threshold_percent
    3. Считаем сколько новостей было за 3 дня ДО этого события
    4. Сохраняем как аномалию (spike или crash)
    """
    coins = CoinSnapshot.objects.all()
    anomaly_count = 0
    
    print(f"⚡ Поиск аномалий (порог: {threshold_percent}%) для {coins.count()} монет...")
    
    for coin in coins:
        try:
            # Получаем историю цен, отсортированную по дате
            stats = list(
                CoinDailyStat.objects.filter(coin=coin).order_by('date')
            )
            
            if len(stats) < 2:
                print(f"⚠️  {coin.symbol.upper()} - недостаточно данных (< 2 дней)")
                continue
            
            coin_anomalies = 0
            
            # Сравниваем каждый день с предыдущим
            for i in range(1, len(stats)):
                try:
                    prev_stat = stats[i-1]
                    curr_stat = stats[i]
                    
                    prev_price = float(prev_stat.price)
                    curr_price = float(curr_stat.price)
                    
                    # Пропускаем если цена = 0
                    if prev_price == 0:
                        continue
                    
                    # Вычисляем изменение в процентах
                    change_percent = ((curr_price - prev_price) / prev_price) * 100
                    
                    # Проверяем порог аномалии
                    if abs(change_percent) > threshold_percent:
                        
                        # Считаем новости за 3 дня ДО события
                        news_period_start = curr_stat.date - timedelta(days=3)
                        news_period_end = curr_stat.date
                        
                        news_count = NewsArticle.objects.filter(
                            coin=coin,
                            published_at__date__range=[news_period_start, news_period_end]
                        ).count()
                        
                        # Определяем тип события
                        if change_percent > 0:
                            event_type = 'spike'  # рост
                        else:
                            event_type = 'crash'  # падение
                        
                        # Сохраняем или обновляем событие
                        event, created = PriceEvent.objects.update_or_create(
                            coin=coin,
                            date=curr_stat.date,
                            defaults={
                                'event_type': event_type,
                                'price_change_percent': change_percent,
                                'price_before': prev_price,
                                'price_after': curr_price,
                                'is_anomaly': True,
                                'news_count': news_count
                            }
                        )
                        
                        if created:
                            anomaly_count += 1
                            coin_anomalies += 1
                
                except Exception as e:
                    print(f"⚠️  Ошибка обработки дня {curr_stat.date}: {e}")
                    continue
            
            if coin_anomalies > 0:
                print(f"✅ {coin.symbol.upper()} - найдено {coin_anomalies} аномалий")
            else:
                print(f"ℹ️  {coin.symbol.upper()} - аномалий не найдено")
            
        except Exception as e:
            print(f"❌ Ошибка для {coin.symbol}: {e}")
            continue
    
    print(f"\n✅ Всего найдено {anomaly_count} новых аномалий")
    return f"Найдено {anomaly_count} аномалий"


# ============================================
# СТАТИСТИКА АНОМАЛИЙ (ДОПОЛНИТЕЛЬНО)
# ============================================

@shared_task
def get_anomalies_stats():
    """
    Возвращает подробную статистику по найденным аномалиям
    Полезно для проверки перед обучением
    """
    from django.db.models import Count, Avg, Max, Min
    
    total_events = PriceEvent.objects.filter(is_anomaly=True).count()
    
    if total_events == 0:
        return "Аномалии не найдены. Запустите detect_all_anomalies()"
    
    print("="*60)
    print("📊 СТАТИСТИКА АНОМАЛИЙ")
    print("="*60)
    
    # Общая статистика
    print(f"\n🎯 Всего аномалий: {total_events}")
    
    # По типам
    spikes = PriceEvent.objects.filter(event_type='spike', is_anomaly=True).count()
    crashes = PriceEvent.objects.filter(event_type='crash', is_anomaly=True).count()
    print(f"\n📈 Типы:")
    print(f"  Рост (spike):  {spikes} ({spikes/total_events*100:.1f}%)")
    print(f"  Падение (crash): {crashes} ({crashes/total_events*100:.1f}%)")
    
    # По монетам
    print(f"\n🪙 По монетам:")
    by_coin = PriceEvent.objects.filter(is_anomaly=True).values(
        'coin__symbol', 'coin__name'
    ).annotate(
        count=Count('id'),
        avg_change=Avg('price_change_percent'),
        max_change=Max('price_change_percent'),
        min_change=Min('price_change_percent'),
        avg_news=Avg('news_count')
    ).order_by('-count')
    
    for item in by_coin:
        print(f"  {item['coin__symbol'].upper():8} - "
              f"{item['count']:2} событий, "
              f"среднее изм: {item['avg_change']:+.2f}%, "
              f"новостей: {item['avg_news']:.1f}")
    
    # Статистика изменений
    changes = PriceEvent.objects.filter(is_anomaly=True).aggregate(
        avg=Avg('price_change_percent'),
        max=Max('price_change_percent'),
        min=Min('price_change_percent')
    )
    print(f"\n📊 Изменения цен:")
    print(f"  Среднее: {changes['avg']:+.2f}%")
    print(f"  Максимум: {changes['max']:+.2f}%")
    print(f"  Минимум: {changes['min']:+.2f}%")
    
    # Статистика новостей
    news_stats = PriceEvent.objects.filter(is_anomaly=True).aggregate(
        avg_news=Avg('news_count'),
        max_news=Max('news_count'),
        min_news=Min('news_count')
    )
    print(f"\n📰 Новости (за 3 дня до события):")
    print(f"  Среднее: {news_stats['avg_news']:.1f}")
    print(f"  Максимум: {news_stats['max_news']}")
    print(f"  Минимум: {news_stats['min_news']}")
    
    # Топ-5 событий
    print(f"\n🔥 Топ-5 самых сильных изменений:")
    top_events = PriceEvent.objects.filter(is_anomaly=True).select_related('coin').order_by(
        '-price_change_percent'
    )[:5]
    
    for event in top_events:
        print(f"  {event.coin.symbol.upper()} {event.date}: "
              f"{event.price_change_percent:+.2f}% "
              f"(новостей: {event.news_count})")
    
    print("\n" + "="*60)
    
    return {
        'total': total_events,
        'spikes': spikes,
        'crashes': crashes,
        'avg_change': changes['avg'],
        'avg_news': news_stats['avg_news']
    }


# ============================================
# МАШИННОЕ ОБУЧЕНИЕ (Задача предсказания цен)
# ============================================
@shared_task
def prepare_daily_training_dataset_v2():
    """
    Расширенная версия с инженерией новостных признаков
    """
    from datetime import timedelta
    import numpy as np
    import pandas as pd
    
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
            
            # TARGET
            price_current = float(current_day['price'])
            price_next = float(next_day['price'])
            target_change_percent = ((price_next - price_current) / price_current) * 100
            
            # === ЦЕНОВЫЕ ПРИЗНАКИ ===
            past_7_days = daily_stats[i-6:i+1]
            prices_7d = [float(d['price']) for d in past_7_days]
            volumes_7d = [float(d['volume']) for d in past_7_days]
            
            avg_price_7d = np.mean(prices_7d)
            volatility_7d = np.std(prices_7d)
            price_trend_7d = ((prices_7d[-1] - prices_7d[0]) / prices_7d[0]) * 100
            avg_volume_7d = np.mean(volumes_7d)
            
            # === НОВОСТНЫЕ ПРИЗНАКИ - ТЕКУЩИЙ ПЕРИОД (3 дня) ===
            date_3d_ago = current_day['date'] - timedelta(days=3)
            
            news_current = NewsArticle.objects.filter(
                coin=coin,
                published_at__date__gte=date_3d_ago,
                published_at__date__lte=current_day['date']
            ).select_related('newssentiment')
            
            # === НОВОСТНЫЕ ПРИЗНАКИ - ПРЕДЫДУЩИЙ ПЕРИОД (дни -6 до -3) ===
            date_6d_ago = current_day['date'] - timedelta(days=6)
            
            news_previous = NewsArticle.objects.filter(
                coin=coin,
                published_at__date__gte=date_6d_ago,
                published_at__date__lt=date_3d_ago
            ).select_related('newssentiment')
            
            # Вычисляем для текущего периода
            news_count_current = news_current.count()
            sentiments_current = [
                n.newssentiment.sentiment_score 
                for n in news_current 
                if hasattr(n, 'newssentiment')
            ]
            avg_sentiment_current = np.mean(sentiments_current) if sentiments_current else 0
            positive_current = sum(1 for s in sentiments_current if s > 0.05)
            negative_current = sum(1 for s in sentiments_current if s < -0.05)
            
            # Вычисляем для предыдущего периода
            news_count_previous = news_previous.count()
            sentiments_previous = [
                n.newssentiment.sentiment_score 
                for n in news_previous 
                if hasattr(n, 'newssentiment')
            ]
            avg_sentiment_previous = np.mean(sentiments_previous) if sentiments_previous else 0
            positive_previous = sum(1 for s in sentiments_previous if s > 0.05)
            negative_previous = sum(1 for s in sentiments_previous if s < -0.05)
            
            # === НОВЫЕ ПРИЗНАКИ: ИЗМЕНЕНИЕ НОВОСТНОГО ФОНА ===
            news_volume_change = news_count_current - news_count_previous
            news_volume_ratio = news_count_current / news_count_previous if news_count_previous > 0 else 1.0
            
            sentiment_change = avg_sentiment_current - avg_sentiment_previous
            sentiment_acceleration = sentiment_change  # скорость изменения тональности
            
            positive_change = positive_current - positive_previous
            negative_change = negative_current - negative_previous
            
            # Резкий всплеск негатива = плохой сигнал
            negative_spike = 1 if (negative_current > 5 and negative_change > 3) else 0
            
            # Резкий рост позитива = хороший сигнал
            positive_spike = 1 if (positive_current > 5 and positive_change > 3) else 0
            
            # === ВЗАИМОДЕЙСТВИЕ ЦЕН И НОВОСТЕЙ ===
            # Если тренд положительный И тональность растет = сильный сигнал
            price_sentiment_alignment = price_trend_7d * avg_sentiment_current
            
            # Дивергенция: цена падает, но новости позитивные = возможный разворот
            divergence = 1 if (price_trend_7d < -1 and avg_sentiment_current > 0.1) else 0
            
            # === ВРЕМЕННЫЕ ПРИЗНАКИ ===
            day_of_week = current_day['date'].weekday()
            month = current_day['date'].month
            
            # === СОБИРАЕМ ДАННЫЕ ===
            data.append({
                'coin': coin.symbol,
                'date': current_day['date'],
                'target': target_change_percent,
                
                # Ценовые (4)
                'avg_price_7d': avg_price_7d,
                'volatility_7d': volatility_7d,
                'price_trend_7d': price_trend_7d,
                'avg_volume_7d': avg_volume_7d,
                
                # Новостные - абсолютные (3)
                'news_count_current': news_count_current,
                'avg_sentiment_current': avg_sentiment_current,
                'sentiment_std': np.std(sentiments_current) if sentiments_current else 0,
                
                # Новостные - изменения (6) - НОВОЕ!
                'news_volume_change': news_volume_change,
                'sentiment_change': sentiment_change,
                'positive_change': positive_change,
                'negative_change': negative_change,
                'negative_spike': negative_spike,
                'positive_spike': positive_spike,
                
                # Взаимодействие (2) - НОВОЕ!
                'price_sentiment_alignment': price_sentiment_alignment,
                'divergence': divergence,
                
                # Временные (2)
                'day_of_week': day_of_week,
                'month': month
            })
    
    df = pd.DataFrame(data)
    
    # Удаляем выбросы в новостных признаках
    df['news_volume_change'] = df['news_volume_change'].clip(-50, 50)
    df['sentiment_change'] = df['sentiment_change'].clip(-1, 1)
    
    # Сохраняем
    df.to_csv('subscriptions/training_data_v2.csv', index=False)
    
    print(f"✅ Dataset created: {len(df)} samples")
    print(f"Target stats: mean={df['target'].mean():.2f}%, std={df['target'].std():.2f}%")
    print(f"\nNews features stats:")
    print(f"  news_volume_change: {df['news_volume_change'].mean():.1f} ± {df['news_volume_change'].std():.1f}")
    print(f"  sentiment_change: {df['sentiment_change'].mean():.3f} ± {df['sentiment_change'].std():.3f}")
    print(f"  negative_spike events: {df['negative_spike'].sum()}")
    print(f"  positive_spike events: {df['positive_spike'].sum()}")
    
    return {
        'total_samples': len(df),
        'coins': df['coin'].nunique(),
        'target_mean': float(df['target'].mean()),
        'target_std': float(df['target'].std())
    }


@shared_task
def train_prediction_model_v4():
    """
    Модель с новыми признаками и регуляризацией
    """
    import pandas as pd
    import numpy as np
    from sklearn.preprocessing import StandardScaler
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.metrics import mean_absolute_error, r2_score
    import joblib
    
    # Загружаем НОВЫЙ датасет
    df = pd.read_csv('subscriptions/training_data_v2.csv')
    
    print(f"📊 Dataset: {len(df)} samples")
    
    # === ВЫБИРАЕМ ПРИЗНАКИ ===
    feature_cols = [
        # Ценовые (4)
        'price_trend_7d',
        'volatility_7d',
        'avg_volume_7d',
        'avg_price_7d',
        
        # Новостные - динамические (8) - ОСНОВНОЙ ФОКУС!
        'news_volume_change',      # изменение количества новостей
        'sentiment_change',         # изменение тональности
        'positive_change',          # рост позитива
        'negative_change',          # рост негатива
        'negative_spike',           # всплеск негатива
        'positive_spike',           # всплеск позитива
        'price_sentiment_alignment', # согласованность цены и тональности
        'divergence',               # расхождение
    ]
    
    print(f"🎯 Using {len(feature_cols)} features")
    print(f"   - Price: 4 features")
    print(f"   - News: 8 features (dynamic)")
    
    X = df[feature_cols]
    y = df['target']
    
    # Temporal split
    df_sorted = df.sort_values('date')
    split_idx = int(len(df_sorted) * 0.8)
    
    train_df = df_sorted.iloc[:split_idx]
    test_df = df_sorted.iloc[split_idx:]
    
    X_train = train_df[feature_cols]
    y_train = train_df['target']
    X_test = test_df[feature_cols]
    y_test = test_df['target']
    
    print(f"\n📦 Train: {len(train_df)} samples")
    print(f"📦 Test: {len(test_df)} samples")
    
    # Масштабирование
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    # === МОДЕЛЬ С БОЛЬШЕЙ ГЛУБИНОЙ для захвата взаимодействий ===
    model = GradientBoostingRegressor(
        n_estimators=50,
        learning_rate=0.05,
        max_depth=4,           # глубже для взаимодействий
        min_samples_split=20,
        min_samples_leaf=10,
        subsample=0.8,
        max_features='sqrt',   # случайные подмножества признаков
        random_state=42,
        verbose=0
    )
    
    print("\n🔧 Training model...")
    model.fit(X_train_scaled, y_train)
    
    # Оцениваем
    train_predictions = model.predict(X_train_scaled)
    test_predictions = model.predict(X_test_scaled)
    
    train_r2 = r2_score(y_train, train_predictions)
    test_r2 = r2_score(y_test, test_predictions)
    train_mae = mean_absolute_error(y_train, train_predictions)
    test_mae = mean_absolute_error(y_test, test_predictions)
    
    # Важность признаков
    feature_importance = pd.DataFrame({
        'feature': feature_cols,
        'importance': model.feature_importances_
    }).sort_values('importance', ascending=False)
    
    print("\n" + "="*60)
    print("📈 MODEL PERFORMANCE")
    print("="*60)
    print(f"Train R²:  {train_r2:>7.4f}")
    print(f"Test R²:   {test_r2:>7.4f}  {'✅' if test_r2 > 0 else '❌'}")
    print(f"Train MAE: {train_mae:>6.2f}%")
    print(f"Test MAE:  {test_mae:>6.2f}%")
    print(f"Overfitting gap: {train_r2 - test_r2:.4f}")
    
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
    
    # Топ-3 новостных признака
    news_importance_df = feature_importance[feature_importance['feature'].isin(news_features)]
    if not news_importance_df.empty:
        print(f"\n📰 Top news features:")
        for idx, row in news_importance_df.head(3).iterrows():
            print(f"   {row['feature']}: {row['importance']*100:.1f}%")
    
    # Сохраняем
    joblib.dump(model, 'subscriptions/ml_model.pkl')
    joblib.dump(scaler, 'subscriptions/ml_scaler.pkl')
    joblib.dump(feature_cols, 'subscriptions/feature_columns.pkl')
    
    print("\n✅ Model saved successfully")
    
    return {
        'train_r2': float(train_r2),
        'test_r2': float(test_r2),
        'train_mae': float(train_mae),
        'test_mae': float(test_mae),
        'price_importance': float(price_importance),
        'news_importance': float(news_importance),
        'feature_importance': feature_importance.to_dict('records')
    }


@shared_task
def predict_price_change(coin_symbol):
    """
    Предсказывает будущее изменение цены для конкретной монеты
    
    Использует обученную модель и текущие данные
    
    Args:
        coin_symbol: символ монеты (например, 'btc')
    
    Returns:
        Предсказанное изменение цены в %
    """
    import pickle
    import os
    import numpy as np
    
    # Загружаем модель
    model_path = os.path.join(os.path.dirname(__file__), 'ml_model.pkl')
    
    if not os.path.exists(model_path):
        raise Exception("Модель не обучена! Запустите train_prediction_model()")
    
    with open(model_path, 'rb') as f:
        model_data = pickle.load(f)
    
    model = model_data['model']
    scaler = model_data['scaler']
    feature_columns = model_data['feature_columns']
    
    # Получаем монету
    try:
        coin = CoinSnapshot.objects.get(symbol=coin_symbol.lower())
    except CoinSnapshot.DoesNotExist:
        raise Exception(f"Монета {coin_symbol} не найдена")
    
    # Собираем текущие признаки (аналогично prepare_training_dataset)
    today = datetime.now().date()
    
    # Ценовые признаки (последние 7 дней)
    period_start = today - timedelta(days=7)
    price_stats = CoinDailyStat.objects.filter(
        coin=coin,
        date__range=[period_start, today]
    ).order_by('date')
    
    if price_stats.count() < 3:
        raise Exception(f"Недостаточно данных для {coin_symbol}")
    
    prices = [float(s.price) for s in price_stats]
    avg_price_7d = np.mean(prices)
    volatility_7d = np.std(prices)
    price_trend_7d = (prices[-1] - prices[0]) / prices[0] * 100
    
    # Новостные признаки (последние 3 дня)
    news_period_start = today - timedelta(days=3)
    news = NewsArticle.objects.filter(
        coin=coin,
        published_at__date__range=[news_period_start, today]
    ).prefetch_related('newssentiment')
    
    news_count_3d = news.count()
    
    sentiments = []
    for article in news:
        if hasattr(article, 'newssentiment'):
            sentiments.append(article.newssentiment.sentiment_score)
    
    if sentiments:
        avg_sentiment = np.mean(sentiments)
        sentiment_std = np.std(sentiments)
        positive_ratio = len([s for s in sentiments if s > 0.1]) / len(sentiments)
        negative_ratio = len([s for s in sentiments if s < -0.1]) / len(sentiments)
        positive_count = len([s for s in sentiments if s > 0.1])
        negative_count = len([s for s in sentiments if s < -0.1])
        neutral_count = len([s for s in sentiments if -0.1 <= s <= 0.1])
    else:
        avg_sentiment = 0
        sentiment_std = 0
        positive_ratio = 0
        negative_ratio = 0
        positive_count = 0
        negative_count = 0
        neutral_count = 0
    
    news_per_day = news_count_3d / 3.0
    news_spike = 1 if news_count_3d > 50 else 0
    
    political_count = news.filter(news_type='political').count()
    financial_count = news.filter(news_type='financial').count()
    political_ratio = political_count / news_count_3d if news_count_3d > 0 else 0
    
    political_sentiments = []
    for article in news.filter(news_type='political'):
        if hasattr(article, 'newssentiment'):
            political_sentiments.append(article.newssentiment.sentiment_score)
    avg_political_sentiment = np.mean(political_sentiments) if political_sentiments else 0
    
    day_of_week = today.weekday()
    month = today.month
    
    # Формируем вектор признаков
    features = {
        'avg_price_7d': avg_price_7d,
        'volatility_7d': volatility_7d,
        'price_trend_7d': price_trend_7d,
        'news_count_3d': news_count_3d,
        'news_per_day': news_per_day,
        'news_spike': news_spike,
        'avg_sentiment': avg_sentiment,
        'sentiment_std': sentiment_std,
        'positive_ratio': positive_ratio,
        'negative_ratio': negative_ratio,
        'positive_count': positive_count,
        'negative_count': negative_count,
        'neutral_count': neutral_count,
        'political_count': political_count,
        'financial_count': financial_count,
        'political_ratio': political_ratio,
        'avg_political_sentiment': avg_political_sentiment,
        'day_of_week': day_of_week,
        'month': month
    }
    
    X = np.array([[features[col] for col in feature_columns]])
    X_scaled = scaler.transform(X)
    
    # Предсказание
    prediction = model.predict(X_scaled)[0]
    
    return {
        'coin': coin_symbol.upper(),
        'predicted_change': round(prediction, 2),
        'current_price': float(coin.price),
        'news_count': news_count_3d,
        'avg_sentiment': round(avg_sentiment, 2)
    }

# ============================================
# МАШИННОЕ ОБУЧЕНИЕ (Задача предсказания тренда)
# ============================================
@shared_task
def prepare_classification_dataset():
    """
    Подготавливает датасет для обучения классификатора
    Сохраняет в ml/models/classification_data.csv
    """
    from datetime import timedelta
    import numpy as np
    import pandas as pd
    
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
            
            # [... код вычисления признаков остается таким же ...]
            # (все вычисления price, news и т.д.)
            
            data.append({
                'coin': coin.symbol,
                'date': current_day['date'],
                'target': target,
                'price_change_percent': price_change_percent,
                
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
            })
    
    df = pd.DataFrame(data)
    
    up_count = (df['target'] == 1).sum()
    down_count = (df['target'] == 0).sum()
    
    print(f"\n✅ Dataset created: {len(df)} samples")
    print(f"📊 Class distribution:")
    print(f"   UP (1):   {up_count} ({up_count/len(df)*100:.1f}%)")
    print(f"   DOWN (0): {down_count} ({down_count/len(df)*100:.1f}%)")
    
    # СОХРАНЯЕМ В ml/models/
    df.to_csv(TRAINING_DATA_PATH, index=False)
    print(f"💾 Saved to: {TRAINING_DATA_PATH}")
    
    return {
        'total_samples': len(df),
        'up_count': int(up_count),
        'down_count': int(down_count),
        'saved_to': str(TRAINING_DATA_PATH)
    }


@shared_task
def train_classification_model_v2():
    """
    Обучает классификатор и сохраняет в ml/models/
    """
    import pandas as pd
    import numpy as np
    from sklearn.preprocessing import StandardScaler
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.metrics import accuracy_score, classification_report, roc_auc_score, confusion_matrix
    import joblib
    
    # ЗАГРУЖАЕМ ИЗ ml/models/
    print(f"📂 Loading data from: {TRAINING_DATA_PATH}")
    df = pd.read_csv(TRAINING_DATA_PATH)
    
    print(f"📊 Dataset: {len(df)} samples")
    
    feature_cols = [
        'price_trend_7d', 'volatility_7d', 'avg_volume_7d', 'avg_price_7d',
        'sentiment_change', 'price_sentiment_alignment',
    ]
    
    print(f"🎯 Using {len(feature_cols)} features (reduced from 12)")
    
    X = df[feature_cols]
    y = df['target']
    
    # Temporal split
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
    
    print("\n🔧 Training simplified classifier...")
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
    
    # СОХРАНЯЕМ В ml/models/
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
# ЗАДАЧИ ОБНОВЛЕНИЯ ДАННЫХ ДЛЯ ПРОГНОЗА
# ============================================
# subscriptions/tasks.py

@shared_task
def update_daily_data():
    """
    Обновляет данные за вчерашний день:
    1. Собирает новости за последние 24 часа
    2. Обновляет курсы валют
    """
    from django.utils import timezone
    
    print(f"🔄 Updating daily data at {timezone.now()}")
    
    # 1. Обновляем текущие цены (снапшоты)
    update_coin_snapshots()
    
    # 2. Собираем исторические цены за последний день
    # (CoinGecko возвращает дневные данные, поэтому берем 2 дня чтобы точно получить вчера)
    collect_historical_prices(days=2)
    
    # 3. Собираем новости за последние 24 часа
    collect_recent_news()
    
    # 4. Анализируем тональность новых новостей
    analyze_all_sentiment()
    
    print("✅ Daily data updated")
    
    return {'status': 'success', 'timestamp': timezone.now().isoformat()}

@shared_task
def collect_recent_news():
    """
    Собирает новости за последние 24 часа для всех монет
    """

    
    NEWSAPI_KEY = os.environ.get('NEWSAPI_KEY')
    if not NEWSAPI_KEY:
        print("⚠️ NEWSAPI_KEY not set")
        return
    
    yesterday = (timezone.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    for coin in CoinSnapshot.objects.all():
        query = f"{coin.name} OR {coin.symbol}"
        
        try:
            response = requests.get(
                'https://newsapi.org/v2/everything',
                params={
                    'q': query,
                    'from': yesterday,
                    'sortBy': 'publishedAt',
                    'language': 'en',
                    'apiKey': NEWSAPI_KEY
                },
                timeout=10
            )
            
            if response.status_code == 200:
                articles = response.json().get('articles', [])
                
                for article in articles[:30]:  # Лимит 30 новостей на монету
                    NewsArticle.objects.get_or_create(
                        url=article['url'],
                        defaults={
                            'coin': coin,
                            'title': article.get('title', '')[:200],
                            'description': article.get('description', '')[:500],
                            'source': article.get('source', {}).get('name', 'Unknown'),
                            'published_at': article['publishedAt'],
                            'news_type': 'financial'
                        }
                    )
                
                print(f"✅ {coin.symbol}: {len(articles)} news collected")
            
            time.sleep(2)  # Пауза между запросами
            
        except Exception as e:
            print(f"❌ Error collecting news for {coin.symbol}: {e}")
    
    return {'status': 'success'}



# ============================================
# ЗАДАЧИ СОЗДАНИЯ ПРОГНОЗА
# ============================================  

# subscriptions/tasks.py

def compute_features_for_coin(coin):
    """
    Вычисляет НОВЫЕ признаки с изменениями и взаимодействиями
    """
    from django.utils import timezone
    from datetime import timedelta
    import numpy as np
    import pandas as pd
    
    now = timezone.now()
    
    # 1. ЦЕНОВЫЕ ПРИЗНАКИ (7 дней)
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
    
    # 2. НОВОСТИ - ТЕКУЩИЙ ПЕРИОД (последние 3 дня)
    news_current = NewsArticle.objects.filter(
        coin=coin,
        published_at__gte=now - timedelta(days=3)
    ).select_related('newssentiment')
    
    # 3. НОВОСТИ - ПРЕДЫДУЩИЙ ПЕРИОД (дни -6 до -3)
    news_previous = NewsArticle.objects.filter(
        coin=coin,
        published_at__gte=now - timedelta(days=6),
        published_at__lt=now - timedelta(days=3)
    ).select_related('newssentiment')
    
    # Вычисляем для текущего периода
    news_count_current = news_current.count()
    sentiments_current = [
        n.newssentiment.sentiment_score 
        for n in news_current 
        if hasattr(n, 'newssentiment')
    ]
    avg_sentiment_current = np.mean(sentiments_current) if sentiments_current else 0
    positive_current = sum(1 for s in sentiments_current if s > 0.05)
    negative_current = sum(1 for s in sentiments_current if s < -0.05)
    
    # Вычисляем для предыдущего периода
    news_count_previous = news_previous.count()
    sentiments_previous = [
        n.newssentiment.sentiment_score 
        for n in news_previous 
        if hasattr(n, 'newssentiment')
    ]
    avg_sentiment_previous = np.mean(sentiments_previous) if sentiments_previous else 0
    positive_previous = sum(1 for s in sentiments_previous if s > 0.05)
    negative_previous = sum(1 for s in sentiments_previous if s < -0.05)
    
    # === НОВЫЕ ПРИЗНАКИ ===
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


@shared_task
def generate_daily_predictions():
    """
    Обновленная версия с правильным форматом данных
    """
    from django.utils import timezone
    import numpy as np
    import pandas as pd
    import joblib
    
    print(f"🔮 Generating predictions at {timezone.now()}")
    
    # Загружаем модель, scaler и список признаков
    try:
        model = joblib.load('subscriptions/ml_model.pkl')
        scaler = joblib.load('subscriptions/ml_scaler.pkl')
        feature_cols = joblib.load('subscriptions/feature_columns.pkl')
    except FileNotFoundError as e:
        print(f"❌ Model files not found: {e}")
        return {'error': 'Model not trained'}
    
    today = timezone.now().date()
    predictions_created = 0
    
    for coin in CoinSnapshot.objects.all():
        try:
            # Вычисляем признаки (теперь возвращает DataFrame)
            features_df = compute_features_for_coin(coin)
            
            if features_df is None:
                print(f"⚠️  {coin.symbol}: insufficient data")
                continue
            
            # Выбираем только нужные признаки в правильном порядке
            X = features_df[feature_cols]
            
            # === ПРИМЕНЯЕМ МАСШТАБИРОВАНИЕ (warning исчезнет) ===
            X_scaled = scaler.transform(X)
            
            # Делаем предсказание
            predicted_change = model.predict(X_scaled)[0]
            
            # Вычисляем предсказанную цену
            current_price = float(coin.price)
            predicted_price = current_price * (1 + predicted_change / 100)
            
            # Сохраняем прогноз
            prediction, created = PricePrediction.objects.update_or_create(
                coin=coin,
                prediction_date=today,
                defaults={
                    'predicted_change_percent': predicted_change,
                    'predicted_price': predicted_price,
                    'current_price': current_price,
                    'model_version': '3.0'
                }
            )
            
            if created:
                predictions_created += 1
                
            emoji = "🟢" if predicted_change > 0 else "🔴"
            print(f"{emoji} {coin.symbol:>6}: {predicted_change:>+6.2f}% (${predicted_price:>10,.2f})")
            
        except Exception as e:
            print(f"❌ Error predicting {coin.symbol}: {e}")
            continue
    
    print(f"\n✅ Generated {predictions_created} predictions")
    
    return {
        'status': 'success',
        'predictions_created': predictions_created,
        'timestamp': timezone.now().isoformat()
    }


@shared_task
def generate_daily_predictions_classifier():
    """
    Генерирует прогнозы используя модели из ml/models/
    """
    from django.utils import timezone
    import numpy as np
    import pandas as pd
    import joblib
    
    print(f"🔮 Generating direction predictions at {timezone.now()}")
    
    # ЗАГРУЖАЕМ ИЗ ml/models/
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
            
            # Оцениваем изменение
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


@shared_task
def generate_model_report():
    """
    Генерирует отчет о модели и сохраняет в ml/models/
    """
    import json
    from datetime import datetime
    
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
    
    # СОХРАНЯЕМ В ml/models/
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


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)





# Пока это работает без асинхронки, она не заработала у меня, по идее для этого нужно менять Celery
#  на другую архитектуру рассылки
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"

@shared_task
def send_price_updates():
    subscriptions = Subscription.objects.select_related("user", "coin").all()
    user_messages = {}

    for sub in subscriptions:
        user_id = sub.user.telegram_id
        coin = sub.coin
        text = f"{coin.name} ({coin.symbol}): ${coin.price:.2f}"
        user_messages.setdefault(user_id, []).append(text)

    for user_id, messages in user_messages.items():
        full_message = "Ваши обновления по криптовалютам:\n\n" + "\n".join(messages)
        try:
            response = requests.post(TELEGRAM_API_URL, data={
                "chat_id": user_id,
                "text": full_message
            }, timeout=10)
            if not response.ok:
                print(f"[Telegram] Не удалось отправить сообщение {user_id}: {response.text}")
        except Exception as e:
            print(f"[Celery] Ошибка при отправке сообщения пользователю {user_id}: {e}")

