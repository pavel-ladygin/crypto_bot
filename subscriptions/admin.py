from django.contrib import admin
from subscriptions.models import BotUser, Coin, Subscription

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'coin', 'time_add')

@admin.register(Coin)
class CoinAdmin(admin.ModelAdmin):
    list_display = ('coin_id', 'coin_name')

@admin.register(BotUser)
class BotUserAdmin(admin.ModelAdmin):
    list_display = ('telegram_id',)