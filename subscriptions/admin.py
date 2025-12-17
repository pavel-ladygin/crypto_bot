from django.contrib import admin
from subscriptions.models import BotUser, Subscription, CoinSnapshot, CoinDailyStat, NewsArticle, NewsSentiment, PriceEvent

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'coin', 'time_add')


@admin.register(BotUser)
class BotUserAdmin(admin.ModelAdmin):
    list_display = ('telegram_id',)

@admin.register(CoinSnapshot)
class CoinSnapshotAdmin(admin.ModelAdmin):
    list_display = ('coingecko_id', 'name', 'symbol', 'price', 'market_cap' ,'updated_at' )

@admin.register(CoinDailyStat)
class CoinDailyStatAdmin(admin.ModelAdmin):
    list_display = ('coin', 'date', 'price', 'price_change_percent', 'market_cap', 'market_cap_change' , 'volume')


@admin.register(NewsArticle)
class NewsArticleAdmin(admin.ModelAdmin):
    list_display = ('coin', 'title', 'source', 'published_at', 'news_type')
    list_filter = ('coin', 'source', 'published_at')
    search_fields = ('title', 'description')

@admin.register(NewsSentiment)
class NewsSentimentAdmin(admin.ModelAdmin):
    list_display = ('article', 'sentiment_label', 'sentiment_score', 'confidence')
    list_filter = ('sentiment_label',)

@admin.register(PriceEvent)
class PriceEventAdmin(admin.ModelAdmin):
    list_display = ('coin', 'date', 'event_type', 'price_change_percent', 'news_count')
    list_filter = ('event_type', 'is_anomaly')
