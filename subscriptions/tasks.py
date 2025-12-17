import logging
from bot.telegram_bot import TG_TOKEN
from celery import shared_task
from django.db import transaction
from .models import CoinSnapshot, Subscription, CoinDailyStat, NewsArticle, NewsSentiment, PriceEvent
import numpy as np
import requests
from datetime import datetime, timedelta
import time
import os
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer 


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
# МАШИННОЕ ОБУЧЕНИЕ
# ============================================

@shared_task
def prepare_training_dataset():
    """
    Подготавливает датасет для обучения модели
    
    Для каждой аномалии собирает признаки:
    - Ценовые: средняя цена, волатильность, тренд за 7 дней до события
    - Новостные: количество новостей, средняя тональность, распределение
    - Целевая переменная: процент изменения цены
    
    Returns:
        DataFrame с признаками и целевой переменной
    """
    import pandas as pd
    import numpy as np
    
    # Получаем только аномалии (исключаем стейблкоины без аномалий)
    events = PriceEvent.objects.filter(
        is_anomaly=True
    ).select_related('coin').order_by('date')
    
    if events.count() == 0:
        raise Exception("Нет аномалий! Запустите detect_all_anomalies()")
    
    print(f"📊 Подготовка датасета из {events.count()} аномалий...")
    
    data = []
    skipped = 0
    
    for event in events:
        try:
            coin = event.coin
            event_date = event.date
            
            # ============================================
            # 1. ЦЕНОВЫЕ ПРИЗНАКИ (за 7 дней ДО события)
            # ============================================
            
            # Период анализа: 7 дней до события
            period_start = event_date - timedelta(days=7)
            period_end = event_date - timedelta(days=1)  # не включая день события
            
            # Получаем историю цен
            price_stats = CoinDailyStat.objects.filter(
                coin=coin,
                date__range=[period_start, period_end]
            ).order_by('date')
            
            if price_stats.count() < 3:
                skipped += 1
                continue
            
            # Извлекаем цены
            prices = [float(s.price) for s in price_stats]
            
            # Рассчитываем признаки
            avg_price_7d = np.mean(prices)
            volatility_7d = np.std(prices)  # стандартное отклонение
            price_trend_7d = (prices[-1] - prices[0]) / prices[0] * 100  # тренд в %
            
            # ============================================
            # 2. НОВОСТНЫЕ ПРИЗНАКИ (за 3 дня ДО события)
            # ============================================
            
            news_period_start = event_date - timedelta(days=3)
            news_period_end = event_date
            
            news = NewsArticle.objects.filter(
                coin=coin,
                published_at__date__range=[news_period_start, news_period_end]
            ).prefetch_related('newssentiment')
            
            news_count_3d = news.count()
            
            # Извлекаем тональности
            sentiments = []
            for article in news:
                if hasattr(article, 'newssentiment'):
                    sentiments.append(article.newssentiment.sentiment_score)
            
            # Признаки тональности
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
            
            # Дополнительные новостные признаки
            news_per_day = news_count_3d / 3.0
            news_spike = 1 if news_count_3d > 50 else 0  # всплеск новостей
            
            # Разделение по типам новостей
            political_news = news.filter(news_type='political')
            financial_news = news.filter(news_type='financial')
            
            political_count = political_news.count()
            financial_count = financial_news.count()
            
            political_ratio = political_count / news_count_3d if news_count_3d > 0 else 0
            
            # Тональность политических новостей
            political_sentiments = []
            for article in political_news:
                if hasattr(article, 'newssentiment'):
                    political_sentiments.append(article.newssentiment.sentiment_score)
            
            avg_political_sentiment = np.mean(political_sentiments) if political_sentiments else 0
            
            # ============================================
            # 3. КОНТЕКСТНЫЕ ПРИЗНАКИ
            # ============================================
            
            # День недели (криптовалюты торгуются 24/7, но активность разная)
            day_of_week = event_date.weekday()  # 0=Monday, 6=Sunday
            
            # Месяц (сезонность)
            month = event_date.month
            
            # ============================================
            # 4. ЦЕЛЕВАЯ ПЕРЕМЕННАЯ
            # ============================================
            
            target = float(event.price_change_percent)
            
            # ============================================
            # СОХРАНЕНИЕ ПРИМЕРА
            # ============================================
            
            data.append({
                # Идентификаторы (для отладки)
                'coin_symbol': coin.symbol,
                'date': event_date,
                
                # Ценовые признаки
                'avg_price_7d': avg_price_7d,
                'volatility_7d': volatility_7d,
                'price_trend_7d': price_trend_7d,
                
                # Новостные признаки (количество)
                'news_count_3d': news_count_3d,
                'news_per_day': news_per_day,
                'news_spike': news_spike,
                
                # Новостные признаки (тональность)
                'avg_sentiment': avg_sentiment,
                'sentiment_std': sentiment_std,
                'positive_ratio': positive_ratio,
                'negative_ratio': negative_ratio,
                'positive_count': positive_count,
                'negative_count': negative_count,
                'neutral_count': neutral_count,
                
                # Новостные признаки (по типам)
                'political_count': political_count,
                'financial_count': financial_count,
                'political_ratio': political_ratio,
                'avg_political_sentiment': avg_political_sentiment,
                
                # Контекстные признаки
                'day_of_week': day_of_week,
                'month': month,
                
                # Целевая переменная
                'price_change_percent': target
            })
            
        except Exception as e:
            print(f"⚠️  Ошибка обработки события {event.id}: {e}")
            skipped += 1
            continue
    
    print(f"✅ Подготовлено примеров: {len(data)}")
    print(f"⚠️  Пропущено: {skipped}")
    
    if len(data) == 0:
        raise Exception("Не удалось подготовить данные!")
    
    # Создаем DataFrame
    df = pd.DataFrame(data)
    
    # Статистика
    print(f"\n📊 Статистика датасета:")
    print(f"  Всего примеров: {len(df)}")
    print(f"  Признаков: {len(df.columns) - 3}")  # исключая coin_symbol, date, target
    print(f"  Средний % изменения: {df['price_change_percent'].mean():.2f}%")
    print(f"  Min изменение: {df['price_change_percent'].min():.2f}%")
    print(f"  Max изменение: {df['price_change_percent'].max():.2f}%")
    
    return df


@shared_task
def train_prediction_model():
    """
    Обучает модель машинного обучения для предсказания изменений цен
    
    Алгоритм:
    1. Подготовка датасета (prepare_training_dataset)
    2. Разделение на train/test (80%/20%)
    3. Обучение Gradient Boosting Regressor
    4. Оценка качества (R², MAE)
    5. Сохранение модели
    
    Returns:
        Dict с метриками модели
    """
    import pandas as pd
    import numpy as np
    from sklearn.model_selection import train_test_split
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import r2_score, mean_absolute_error
    import pickle
    import os
    
    print("="*60)
    print("🤖 ОБУЧЕНИЕ МОДЕЛИ МАШИННОГО ОБУЧЕНИЯ")
    print("="*60)
    
    # ============================================
    # 1. ПОДГОТОВКА ДАННЫХ
    # ============================================
    
    print("\n[1/5] 📊 Подготовка датасета...")
    df = prepare_training_dataset()
    
    # Определяем признаки (features) и целевую переменную (target)
    feature_columns = [
        # Ценовые
        'avg_price_7d', 'volatility_7d', 'price_trend_7d',
        
        # Новостные (количество)
        'news_count_3d', 'news_per_day', 'news_spike',
        
        # Новостные (тональность)
        'avg_sentiment', 'sentiment_std', 
        'positive_ratio', 'negative_ratio',
        'positive_count', 'negative_count', 'neutral_count',
        
        # Новостные (по типам)
        'political_count', 'financial_count', 
        'political_ratio', 'avg_political_sentiment',
        
        # Контекстные
        'day_of_week', 'month'
    ]
    
    X = df[feature_columns].values
    y = df['price_change_percent'].values
    
    print(f"✅ Датасет готов: {X.shape[0]} примеров, {X.shape[1]} признаков")
    
    # ============================================
    # 2. РАЗДЕЛЕНИЕ НА TRAIN/TEST
    # ============================================
    
    print("\n[2/5] 🔀 Разделение на train/test...")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, 
        test_size=0.2,  # 20% на тестирование
        random_state=42,
        shuffle=True
    )
    
    print(f"✅ Train: {len(X_train)} примеров")
    print(f"✅ Test:  {len(X_test)} примеров")
    
    # ============================================
    # 3. НОРМАЛИЗАЦИЯ ПРИЗНАКОВ
    # ============================================
    
    print("\n[3/5] 📏 Нормализация признаков...")
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    print("✅ Признаки нормализованы (StandardScaler)")
    
    # ============================================
    # 4. ОБУЧЕНИЕ МОДЕЛИ
    # ============================================
    
    print("\n[4/5] 🧠 Обучение модели (Gradient Boosting)...")
    
    model = GradientBoostingRegressor(
        n_estimators=30,       # было 100 → стало 30
        learning_rate=0.05,    # было 0.1 → стало 0.05
        max_depth=3,           # было 5 → стало 3
        min_samples_split=20,  # было 5 → стало 20
        min_samples_leaf=10,   # было 3 → стало 10
        subsample=0.8,
        random_state=42,
        verbose=0
    )
    
    model.fit(X_train_scaled, y_train)
    
    print("✅ Модель обучена!")
    
    # ============================================
    # 5. ОЦЕНКА КАЧЕСТВА
    # ============================================
    
    print("\n[5/5] 📊 Оценка качества...")
    
    # Предсказания
    y_train_pred = model.predict(X_train_scaled)
    y_test_pred = model.predict(X_test_scaled)
    
    # Метрики
    train_r2 = r2_score(y_train, y_train_pred)
    test_r2 = r2_score(y_test, y_test_pred)
    
    train_mae = mean_absolute_error(y_train, y_train_pred)
    test_mae = mean_absolute_error(y_test, y_test_pred)
    
    print(f"✅ Train R² Score: {train_r2:.4f}")
    print(f"✅ Test R² Score:  {test_r2:.4f}")
    print(f"✅ Train MAE:      {train_mae:.2f}%")
    print(f"✅ Test MAE:       {test_mae:.2f}%")
    
    # Feature importance (важность признаков)
    feature_importance = pd.DataFrame({
        'feature': feature_columns,
        'importance': model.feature_importances_
    }).sort_values('importance', ascending=False)
    
    print(f"\n📊 Топ-10 важных признаков:")
    for i, row in feature_importance.head(10).iterrows():
        print(f"  {row['feature']:25} {row['importance']:.4f}")
    
    # ============================================
    # 6. СОХРАНЕНИЕ МОДЕЛИ
    # ============================================
    
    print("\n💾 Сохранение модели...")
    
    model_data = {
        'model': model,
        'scaler': scaler,
        'feature_columns': feature_columns,
        'train_r2': train_r2,
        'test_r2': test_r2,
        'train_mae': train_mae,
        'test_mae': test_mae,
        'trained_at': datetime.now(),
        'examples_count': len(X)
    }
    
    # Сохраняем в папку приложения
    model_path = os.path.join(os.path.dirname(__file__), 'ml_model.pkl')
    with open(model_path, 'wb') as f:
        pickle.dump(model_data, f)
    
    print(f"✅ Модель сохранена: {model_path}")
    
    print("\n" + "="*60)
    
    return {
        'examples': len(X),
        'features': len(feature_columns),
        'train_r2': train_r2,
        'test_r2': test_r2,
        'train_mae': train_mae,
        'test_mae': test_mae,
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

