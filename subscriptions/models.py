from django.db import models

class BotUser(models.Model):  # Модель для таблицы с пользователями по tg-id
    telegram_id = models.BigIntegerField(unique=True)

    def __str__(self):  # Магический метод, для нормального представления объекта
                        # (например при print(user1) его tg-id корректно отобразиться
        return str(self.telegram_id)


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