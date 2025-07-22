from django.db import models

class BotUser(models.Model):  # Модель для таблицы с пользователями по tg-id
    telegram_id = models.BigIntegerField(unique=True)

    def __str__(self):  # Магический метод, для нормального представления объекта
                        # (например при print(user1) его tg-id корректно отобразиться
        return str(self.telegram_id)


class CoinSnapshot(models.Model):       # Модель для хранения списка монет
    name = models.CharField(max_length=100)
    symbol = models.CharField(max_length=20)
    price = models.FloatField()
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.symbol})"

class Subscription(models.Model):  # модель для подписок
    user = models.ForeignKey(BotUser, on_delete=models.CASCADE)  # связь с таблицей пользователей
    coin = models.ForeignKey(CoinSnapshot, on_delete=models.CASCADE)  # связь с таблицей монет
    time_add = models.DateTimeField(auto_now_add=True)  # время создания

    class Meta:
        unique_together = ("user", "coin")  # избавляет от повторных подписок на одну монету

    def __str__(self):
        return f"{self.user.telegram_id} подписан на {self.coin}"