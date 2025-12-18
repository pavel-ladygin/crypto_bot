# subscriptions/admin.py

from django.contrib import admin
from django.utils.html import format_html
from .models import (
    CoinSnapshot, CoinDailyStat, NewsArticle, 
    NewsSentiment, PriceEvent, PricePrediction, DirectionPrediction
)

@admin.register(CoinSnapshot)
class CoinSnapshotAdmin(admin.ModelAdmin):
    list_display = ['symbol', 'name', 'price', 'market_cap', 'updated_at']
    search_fields = ['symbol', 'name']
    ordering = ['-market_cap']


@admin.register(CoinDailyStat)
class CoinDailyStatAdmin(admin.ModelAdmin):
    list_display = ['coin', 'date', 'price', 'volume', 'price_change_percent']
    list_filter = ['coin', 'date']
    ordering = ['-date']


@admin.register(NewsArticle)
class NewsArticleAdmin(admin.ModelAdmin):
    list_display = ['title', 'coin', 'source', 'news_type', 'published_at']
    list_filter = ['coin', 'news_type', 'source', 'published_at']
    search_fields = ['title', 'description']
    ordering = ['-published_at']


@admin.register(NewsSentiment)
class NewsSentimentAdmin(admin.ModelAdmin):
    list_display = ['article', 'sentiment_label', 'sentiment_score', 'confidence']
    list_filter = ['sentiment_label']
    ordering = ['-analyzed_at']


@admin.register(PriceEvent)
class PriceEventAdmin(admin.ModelAdmin):
    list_display = ['coin', 'date', 'event_type', 'price_change_percent', 'news_count']
    list_filter = ['coin', 'event_type', 'date']
    ordering = ['-date']

# subscriptions/admin.py

from django.contrib import admin
from django.utils.safestring import mark_safe
from .models import (
    CoinSnapshot, CoinDailyStat, NewsArticle, 
    NewsSentiment, PriceEvent, PricePrediction, DirectionPrediction
)

@admin.register(DirectionPrediction)
class DirectionPredictionAdmin(admin.ModelAdmin):
    list_display = [
        'coin',
        'prediction_date',
        'direction_colored',
        'confidence_colored',
        'signal_strength',
        'estimated_change_colored',
        'current_price',
        'estimated_price',
        'created_at'
    ]
    list_filter = ['prediction_date', 'predicted_direction', 'coin']
    search_fields = ['coin__symbol', 'coin__name']
    ordering = ['-prediction_date', '-confidence_score']
    readonly_fields = ['created_at']
    
    def direction_colored(self, obj):
        """Направление с цветом"""
        color = 'green' if obj.predicted_direction == 'UP' else 'red'
        emoji = '🟢' if obj.predicted_direction == 'UP' else '🔴'
        
        html = f'<span style="color: {color}; font-weight: bold;">{emoji} {obj.predicted_direction}</span>'
        return mark_safe(html)
    direction_colored.short_description = 'Направление'
    
    def confidence_colored(self, obj):
        """Уверенность с цветовой индикацией"""
        if obj.confidence_score >= 0.7:
            color = 'green'
        elif obj.confidence_score >= 0.6:
            color = 'orange'
        else:
            color = 'gray'
        
        confidence_percent = obj.confidence_score * 100
        html = f'<span style="color: {color}; font-weight: bold;">{confidence_percent:.1f}%</span>'
        return mark_safe(html)
    confidence_colored.short_description = 'Уверенность'
    
    def estimated_change_colored(self, obj):
        """Оценка изменения с цветом"""
        color = 'green' if obj.estimated_change_percent > 0 else 'red'
        change_value = obj.estimated_change_percent
        
        html = f'<span style="color: {color};">{change_value:+.2f}%</span>'
        return mark_safe(html)
    estimated_change_colored.short_description = 'Оценка изменения'


@admin.register(PricePrediction)
class PricePredictionAdmin(admin.ModelAdmin):
    list_display = [
        'coin', 
        'prediction_date', 
        'predicted_change_colored', 
        'current_price', 
        'predicted_price', 
        'model_version',
        'created_at'
    ]
    list_filter = ['prediction_date', 'coin', 'model_version']
    search_fields = ['coin__symbol', 'coin__name']
    ordering = ['-prediction_date', '-predicted_change_percent']
    readonly_fields = ['created_at']
    
    def predicted_change_colored(self, obj):
        """Отображает изменение цены с цветом"""
        color = 'green' if obj.predicted_change_percent > 0 else 'red'
        change_value = obj.predicted_change_percent
        
        html = f'<span style="color: {color}; font-weight: bold;">{change_value:+.2f}%</span>'
        return mark_safe(html)
    predicted_change_colored.short_description = 'Прогноз изменения'
