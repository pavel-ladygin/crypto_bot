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



@shared_task
def collect_historical_news(days=30):
    """
    Собирает новости за последние 30 дней через NewsAPI.org
    """
    from newsapi import NewsApiClient
    
    NEWSAPI_KEY = os.environ.get('NEWSAPI_KEY')
    
    if not NEWSAPI_KEY:
        return "NEWSAPI_KEY не найден в переменных окружения"
    
    newsapi = NewsApiClient(api_key=NEWSAPI_KEY)
    coins = CoinSnapshot.objects.all()[:10]  # Можем взять 20 монет (20 запросов из 100)
    total_articles = 0
    
    for coin in coins:
        try:
            # Формируем поисковые запросы
            # NewsAPI ищет лучше по точным ключевым словам
            query = f"{coin.name} OR {coin.symbol.upper()}"
            
            # Дата начала (30 дней назад)
            from_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            to_date = datetime.now().strftime('%Y-%m-%d')
            
            # Запрос к API
            all_articles = newsapi.get_everything(
                q=query,
                from_param=from_date,
                to=to_date,
                language='en',
                sort_by='publishedAt',
                page_size=100  # максимум статей на запрос
            )
            
            articles = all_articles.get('articles', [])
            saved_count = 0
            
            for article in articles:
                try:
                    # Проверяем что есть необходимые поля
                    if not article.get('url') or not article.get('title'):
                        continue
                    
                    # Парсим дату
                    published_str = article.get('publishedAt', '')
                    if published_str:
                        # NewsAPI возвращает в формате: 2024-12-17T00:00:00Z
                        published_at = datetime.strptime(published_str, '%Y-%m-%dT%H:%M:%SZ')
                    else:
                        continue
                    
                    # Сохраняем новость
                    obj, created = NewsArticle.objects.get_or_create(
                        url=article['url'],
                        defaults={
                            'coin': coin,
                            'title': article['title'][:500],  # ограничение длины
                            'description': article.get('description', '')[:1000] if article.get('description') else '',
                            'source': article.get('source', {}).get('name', 'Unknown'),
                            'published_at': published_at
                        }
                    )
                    
                    if created:
                        saved_count += 1
                        
                except Exception as e:
                    print(f"⚠️ Ошибка сохранения статьи: {e}")
                    continue
            
            total_articles += saved_count
            print(f"✅ {coin.symbol.upper()} ({coin.name}) - собрано {saved_count} новых новостей (всего {len(articles)} получено)")
            time.sleep(1)  # небольшая пауза между запросами
            
        except Exception as e:
            print(f"❌ Ошибка для {coin.symbol}: {e}")
            continue
    
    return f"Собрано {total_articles} новых новостей для {len(coins)} монет"


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
            time.sleep(5)  # ← ИЗМЕНИЛ С 2 НА 5 СЕКУНД!
            
        except Exception as e:
            print(f"❌ Ошибка для {coin.symbol}: {e}")
    
    return f"Собрано данных для {len(coins)} монет"



@shared_task
def analyze_all_sentiment():
    """
    Анализирует тональность всех необработанных новостей
    """
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    
    analyzer = SentimentIntensityAnalyzer()
    articles = NewsArticle.objects.filter(newssentiment__isnull=True)
    
    analyzed_count = 0
    
    for article in articles:
        try:
            text = f"{article.title} {article.description}"
            scores = analyzer.polarity_scores(text)
            
            # compound: -1 (негатив) до +1 (позитив)
            sentiment_score = scores['compound']
            
            if sentiment_score >= 0.05:
                label = 'positive'
            elif sentiment_score <= -0.05:
                label = 'negative'
            else:
                label = 'neutral'
            
            NewsSentiment.objects.create(
                article=article,
                sentiment_score=sentiment_score,
                sentiment_label=label,
                confidence=max(scores['pos'], scores['neg'], scores['neu'])
            )
            
            analyzed_count += 1
            
        except Exception as e:
            print(f"❌ Ошибка анализа статьи {article.id}: {e}")
    
    print(f"✅ Проанализировано {analyzed_count} статей")
    return f"Проанализировано {analyzed_count} статей"


@shared_task
def detect_all_anomalies():
    """
    Находит аномалии в ценах и связывает с новостями
    """
    coins = CoinSnapshot.objects.all()[:20]
    anomaly_count = 0
    
    for coin in coins:
        try:
            stats = list(CoinDailyStat.objects.filter(coin=coin).order_by('date'))
            
            for i in range(1, len(stats)):
                prev_price = float(stats[i-1].price)
                curr_price = float(stats[i].price)
                change_percent = ((curr_price - prev_price) / prev_price) * 100
                
                # Аномалия если изменение > 3%
                if abs(change_percent) > 3:
                    # Считаем новости за 3 дня ДО события
                    news_period_start = stats[i].date - timedelta(days=3)
                    news_period_end = stats[i].date
                    
                    news_count = NewsArticle.objects.filter(
                        coin=coin,
                        published_at__date__range=[news_period_start, news_period_end]
                    ).count()
                    
                    event_type = 'spike' if change_percent > 0 else 'crash'
                    
                    PriceEvent.objects.update_or_create(
                        coin=coin,
                        date=stats[i].date,
                        defaults={
                            'event_type': event_type,
                            'price_change_percent': change_percent,
                            'price_before': prev_price,
                            'price_after': curr_price,
                            'is_anomaly': True,
                            'news_count': news_count
                        }
                    )
                    
                    anomaly_count += 1
            
            print(f"✅ {coin.symbol.upper()} - найдено аномалий")
            
        except Exception as e:
            print(f"❌ Ошибка для {coin.symbol}: {e}")
    
    return f"Найдено {anomaly_count} аномалий"





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

