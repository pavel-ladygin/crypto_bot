# subscriptions/admin.py

from django.contrib import admin
from django.utils.html import format_html
from .models import (
    CoinSnapshot, CoinDailyStat, NewsArticle, 
    NewsSentiment, PriceEvent, PricePrediction, DirectionPrediction, BotUser
)


@admin.register(BotUser)
class BotUserAdmin(admin.ModelAdmin):
    list_display = [
        'telegram_id_display',
        'full_name_display',
        'username_display',
        'subscription_count_display',
        'total_commands',
        'total_predictions_viewed',
        'last_active_display',
        'days_since_registration_display',
        'is_active_display'
    ]
    
    list_filter = ['is_active', 'is_blocked', 'language_code', 'created_at']
    search_fields = ['telegram_id', 'username', 'first_name', 'last_name']
    readonly_fields = ['telegram_id', 'created_at', 'last_active']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('telegram_id', 'username', 'first_name', 'last_name', 'language_code')
        }),
        ('Статистика', {
            'fields': ('total_commands', 'total_predictions_viewed', 'created_at', 'last_active')
        }),
        ('Статус', {
            'fields': ('is_active', 'is_blocked')
        }),
    )
    
    def telegram_id_display(self, obj):
        return format_html('<code>{}</code>', obj.telegram_id)
    telegram_id_display.short_description = 'Telegram ID'
    
    def full_name_display(self, obj):
        return obj.full_name
    full_name_display.short_description = 'Полное имя'
    
    def username_display(self, obj):
        if obj.username:
            return format_html('<a href="https://t.me/{}" target="_blank">@{}</a>', obj.username, obj.username)
        return '-'
    username_display.short_description = 'Username'
    
    def subscription_count_display(self, obj):
        count = obj.subscription_count
        if count > 0:
            return format_html('<span style="color: green; font-weight: bold;">📈 {}</span>', count)
        return format_html('<span style="color: gray;">-</span>')
    subscription_count_display.short_description = 'Подписок'
    
    def last_active_display(self, obj):
        from django.utils import timezone
        diff = timezone.now() - obj.last_active
        
        if diff.days == 0:
            if diff.seconds < 3600:
                return format_html('<span style="color: green;">🟢 {} мин назад</span>', diff.seconds // 60)
            return format_html('<span style="color: green;">🟢 {} ч назад</span>', diff.seconds // 3600)
        elif diff.days == 1:
            return format_html('<span style="color: orange;">🟡 Вчера</span>')
        elif diff.days < 7:
            return format_html('<span style="color: orange;">🟡 {} дн назад</span>', diff.days)
        else:
            return format_html('<span style="color: red;">🔴 {} дн назад</span>', diff.days)
    last_active_display.short_description = 'Активность'
    
    def days_since_registration_display(self, obj):
        days = obj.days_since_registration
        if days < 7:
            return format_html('<span style="color: green;">✨ {} дн</span>', days)
        elif days < 30:
            return format_html('<span style="color: blue;">{} дн</span>', days)
        else:
            return format_html('{} дн', days)
    days_since_registration_display.short_description = 'С момента регистрации'
    
    def is_active_display(self, obj):
        if obj.is_active:
            return format_html('<span style="color: green;">✅ Активен</span>')
        return format_html('<span style="color: red;">❌ Неактивен</span>')
    is_active_display.short_description = 'Статус'
    
    actions = ['mark_as_blocked', 'mark_as_unblocked']
    
    def mark_as_blocked(self, request, queryset):
        queryset.update(is_blocked=True)
        self.message_user(request, f"Заблокировано пользователей: {queryset.count()}")
    mark_as_blocked.short_description = "🚫 Заблокировать выбранных"
    
    def mark_as_unblocked(self, request, queryset):
        queryset.update(is_blocked=False)
        self.message_user(request, f"Разблокировано пользователей: {queryset.count()}")
    mark_as_unblocked.short_description = "✅ Разблокировать выбранных"

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



# subscriptions/admin.py

from django.contrib import admin
from django.utils.html import format_html
from subscriptions.models import NewsSentiment

# subscriptions/admin.py

from django.contrib import admin
from django.utils.html import format_html
from subscriptions.models import NewsSentiment

# subscriptions/admin.py

from django.contrib import admin
from django.utils.html import format_html
from subscriptions.models import NewsSentiment

# subscriptions/admin.py

from django.contrib import admin
from django.utils.html import format_html
from subscriptions.models import NewsSentiment, CustomModelSentiment

@admin.register(NewsSentiment)
class NewsSentimentAdmin(admin.ModelAdmin):
    list_display = ['article_title', 'coin_symbol', 'sentiment_display', 'confidence_display', 'analyzed_at']
    list_filter = ['sentiment_label', 'analyzed_at']
    search_fields = ['article__title', 'article__coin__symbol']
    
    def article_title(self, obj):
        return obj.article.title[:60]
    article_title.short_description = 'Новость'
    
    def coin_symbol(self, obj):
        return obj.article.coin.symbol
    coin_symbol.short_description = 'Монета'
    
    def sentiment_display(self, obj):
        emoji = {'positive': '🟢', 'neutral': '⚪', 'negative': '🔴'}
        colors = {'positive': 'green', 'neutral': 'gray', 'negative': 'red'}
        return format_html(
            '<span>{} <span style="color: {}; font-weight: bold;">{}</span></span>',
            emoji.get(obj.sentiment_label, ''),
            colors.get(obj.sentiment_label, 'black'),
            obj.sentiment_label.upper()
        )
    sentiment_display.short_description = 'FinBERT'
    
    def confidence_display(self, obj):
        confidence_pct = obj.confidence * 100
        color = 'green' if confidence_pct >= 80 else 'orange' if confidence_pct >= 60 else 'red'
        confidence_str = f'{confidence_pct:.1f}%'
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, confidence_str)
    confidence_display.short_description = 'Уверенность'


@admin.register(CustomModelSentiment)
class CustomModelSentimentAdmin(admin.ModelAdmin):
    list_display = ['article_title', 'coin_symbol', 'sentiment_display', 'confidence_display', 'model_version', 'analyzed_at']
    list_filter = ['sentiment_label', 'model_version', 'analyzed_at']
    search_fields = ['article__title', 'article__coin__symbol']
    
    def article_title(self, obj):
        return obj.article.title[:60]
    article_title.short_description = 'Новость'
    
    def coin_symbol(self, obj):
        return obj.article.coin.symbol
    coin_symbol.short_description = 'Монета'
    
    def sentiment_display(self, obj):
        emoji = {'positive': '🟢', 'neutral': '⚪', 'negative': '🔴'}
        colors = {'positive': 'green', 'neutral': 'gray', 'negative': 'red'}
        return format_html(
            '<span>{} <span style="color: {}; font-weight: bold;">{}</span></span>',
            emoji.get(obj.sentiment_label, ''),
            colors.get(obj.sentiment_label, 'black'),
            obj.sentiment_label.upper()
        )
    sentiment_display.short_description = 'Custom Model'
    
    def confidence_display(self, obj):
        confidence_pct = obj.confidence * 100
        color = 'green' if confidence_pct >= 80 else 'orange' if confidence_pct >= 60 else 'red'
        confidence_str = f'{confidence_pct:.1f}%'
        return format_html('<span style="color: {}; font-weight: bold;">{}</span>', color, confidence_str)
    confidence_display.short_description = 'Уверенность'






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
