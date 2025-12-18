from django.db import models

# subscriptions/models.py

from django.db import models
from django.utils import timezone

class BotUser(models.Model):
    telegram_id = models.BigIntegerField(unique=True, verbose_name="Telegram ID")
    
    # Основная информация
    username = models.CharField(max_length=255, null=True, blank=True, verbose_name="Username")
    first_name = models.CharField(max_length=255, null=True, blank=True, verbose_name="Имя")
    last_name = models.CharField(max_length=255, null=True, blank=True, verbose_name="Фамилия")
    language_code = models.CharField(max_length=10, null=True, blank=True, verbose_name="Язык")
    
    # Статистика активности
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата регистрации")
    last_active = models.DateTimeField(auto_now=True, verbose_name="Последняя активность")
    total_commands = models.IntegerField(default=0, verbose_name="Всего команд")
    total_predictions_viewed = models.IntegerField(default=0, verbose_name="Просмотров прогнозов")
    
    # Статус
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    is_blocked = models.BooleanField(default=False, verbose_name="Заблокирован")
    
    class Meta:
        verbose_name = "Пользователь бота"
        verbose_name_plural = "Пользователи бота"
        ordering = ['-last_active']
    
    def __str__(self):
        if self.username:
            return f"@{self.username} ({self.telegram_id})"
        elif self.first_name:
            return f"{self.first_name} ({self.telegram_id})"
        return f"User {self.telegram_id}"
    
    @property
    def full_name(self):
        """Полное имя пользователя"""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        elif self.first_name:
            return self.first_name
        elif self.username:
            return f"@{self.username}"
        return f"User {self.telegram_id}"
    
    @property
    def subscription_count(self):
        """Количество подписок"""
        return self.subscription_set.count()
    
    @property
    def days_since_registration(self):
        """Дней с момента регистрации"""
        return (timezone.now() - self.created_at).days
    
    @property
    def is_new_user(self):
        """Новый пользователь (меньше 7 дней)"""
        return self.days_since_registration < 7



class CoinSnapshot(models.Model):
    coingecko_id = models.CharField(max_length=100, unique=True, null=True)
    name = models.CharField(max_length=100)
    symbol = models.CharField(max_length=20)
    price = models.FloatField()
    market_cap = models.BigIntegerField(null=True, blank=True)  # новое поле
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.symbol})"


class CoinDailyStat(models.Model):
    coin = models.ForeignKey(CoinSnapshot, on_delete=models.CASCADE, related_name="daily_stats") # название монеты
    date = models.DateField()
    price = models.FloatField() # текущая цена
    price_change_percent = models.FloatField(null=True, blank=True) # изменение цены
    market_cap = models.BigIntegerField(null=True, blank=True)     # капитализация
    market_cap_change = models.BigIntegerField(null=True, blank=True)   # изменение капитализации
    volume = models.BigIntegerField(null=True, blank=True)   #

    class Meta:
        unique_together = ("coin", "date")
        ordering = ["-date"]

    def __str__(self):
        return f"{self.coin.symbol.upper()} — {self.date}"


class Subscription(models.Model):  # модель для подписок
    user = models.ForeignKey(BotUser, on_delete=models.CASCADE)  # связь с таблицей пользователей
    coin = models.ForeignKey(CoinSnapshot, on_delete=models.CASCADE)  # связь с таблицей монет
    time_add = models.DateTimeField(auto_now_add=True)  # время создания

    class Meta:
        unique_together = ("user", "coin")  # избавляет от повторных подписок на одну монету

    def __str__(self):
        return f"{self.user.telegram_id} подписан на {self.coin}"
    


class NewsArticle(models.Model):
    NEWS_TYPE_CHOICES = [
        ('financial', 'Financial'),
        ('political', 'Political'),
        ('market', 'Market General'),
        ('technical', 'Technical Analysis'),
    ]
    
    coin = models.ForeignKey(CoinSnapshot, on_delete=models.CASCADE)
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True, null=True)
    url = models.URLField(unique=True, max_length=500)
    source = models.CharField(max_length=200)
    published_at = models.DateTimeField()
    
    # НОВОЕ ПОЛЕ
    news_type = models.CharField(
        max_length=20, 
        choices=NEWS_TYPE_CHOICES, 
        default='financial'
    )
    
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.coin.symbol.upper()} - {self.title[:50]}"
    
    class Meta:
        ordering = ['-published_at']



# subscriptions/models.py
class NewsSentiment(models.Model):
    """Основная таблица - FinBERT"""
    article = models.OneToOneField(NewsArticle, on_delete=models.CASCADE)
    sentiment_label = models.CharField(max_length=50)
    sentiment_score = models.FloatField()
    confidence = models.FloatField(default=0.0)
    analyzed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "FinBERT Sentiment"
        verbose_name_plural = "FinBERT Sentiments"
    
    def __str__(self):
        return f"{self.article.coin.symbol} - {self.sentiment_label}"


class CustomModelSentiment(models.Model):
    """Новая таблица - Custom DistilBERT для A/B тестирования"""
    article = models.ForeignKey(NewsArticle, on_delete=models.CASCADE, related_name='custom_sentiments')
    sentiment_label = models.CharField(max_length=50)
    sentiment_score = models.FloatField()
    confidence = models.FloatField(default=0.0)
    model_version = models.CharField(max_length=50, default='custom_distilbert_v1')
    analyzed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Custom Model Sentiment"
        verbose_name_plural = "Custom Model Sentiments"
        # Можно анализировать одну новость несколько раз разными версиями
        unique_together = ['article', 'model_version']
    
    def __str__(self):
        return f"{self.article.coin.symbol} - {self.sentiment_label} ({self.model_version})"



class PriceEvent(models.Model):
    coin = models.ForeignKey(CoinSnapshot, on_delete=models.CASCADE, related_name='events')
    date = models.DateField()
    event_type = models.CharField(max_length=20)  # spike/crash
    price_change_percent = models.FloatField()
    price_before = models.DecimalField(max_digits=20, decimal_places=8)
    price_after = models.DecimalField(max_digits=20, decimal_places=8)
    is_anomaly = models.BooleanField(default=False)
    news_count = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['-date']
        unique_together = ['coin', 'date']
        
    def __str__(self):
        return f"{self.coin.symbol} - {self.date} ({self.price_change_percent:+.2f}%)"
    

# subscriptions/models.py

class PricePrediction(models.Model):
    """Прогнозы изменения цен"""
    coin = models.ForeignKey(CoinSnapshot, on_delete=models.CASCADE, related_name='predictions')
    
    # Когда сделан прогноз
    created_at = models.DateTimeField(auto_now_add=True)
    prediction_date = models.DateField()  # Дата, на которую делается прогноз
    
    # Прогнозируемые значения
    predicted_change_percent = models.FloatField(
        help_text="Предсказанное изменение цены в %"
    )
    predicted_price = models.DecimalField(
        max_digits=20, 
        decimal_places=8,
        help_text="Предсказанная цена"
    )
    
    # Контекст прогноза
    current_price = models.DecimalField(
        max_digits=20, 
        decimal_places=8,
        help_text="Цена на момент прогноза"
    )
    
    # Метаданные модели
    model_version = models.CharField(max_length=50, default='1.0')
    confidence_score = models.FloatField(null=True, blank=True)
    
    class Meta:
        ordering = ['-prediction_date']
        unique_together = ['coin', 'prediction_date']
        indexes = [
            models.Index(fields=['coin', '-prediction_date']),
        ]
    
    def __str__(self):
        return f"{self.coin.symbol} на {self.prediction_date}: {self.predicted_change_percent:+.2f}%"


# subscriptions/models.py

# Добавляем новую модель для прогнозов направления
class DirectionPrediction(models.Model):
    """Прогнозы направления движения цены (UP/DOWN)"""
    
    DIRECTION_CHOICES = [
        ('UP', 'Upward'),
        ('DOWN', 'Downward'),
    ]
    
    coin = models.ForeignKey(CoinSnapshot, on_delete=models.CASCADE, related_name='direction_predictions')
    prediction_date = models.DateField(help_text="Дата, на которую делается прогноз")
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Прогноз направления
    predicted_direction = models.CharField(max_length=4, choices=DIRECTION_CHOICES)
    confidence_score = models.FloatField(help_text="Уверенность модели (0-1)")
    
    # Вероятности
    probability_up = models.FloatField(help_text="Вероятность роста")
    probability_down = models.FloatField(help_text="Вероятность падения")
    
    # Оценочное изменение цены
    estimated_change_percent = models.FloatField(
        help_text="Оценка изменения в % (положительное = рост)"
    )
    
    # Контекст прогноза
    current_price = models.DecimalField(max_digits=20, decimal_places=8)
    estimated_price = models.DecimalField(
        max_digits=20, 
        decimal_places=8,
        help_text="Оценочная цена на основе направления"
    )
    
    # Метаданные
    model_version = models.CharField(max_length=50, default='classifier_v2')
    
    class Meta:
        ordering = ['-prediction_date', '-confidence_score']
        unique_together = ['coin', 'prediction_date']
        indexes = [
            models.Index(fields=['coin', '-prediction_date']),
            models.Index(fields=['predicted_direction']),
        ]
    
    def __str__(self):
        return f"{self.coin.symbol} on {self.prediction_date}: {self.predicted_direction} ({self.confidence_score*100:.0f}%)"
    
    @property
    def signal_strength(self):
        """Возвращает силу сигнала"""
        if self.confidence_score >= 0.7:
            return 'strong'
        elif self.confidence_score >= 0.6:
            return 'moderate'
        else:
            return 'weak'
