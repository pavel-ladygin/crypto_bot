from django.contrib import admin
from subscriptions.models import BotUser, Subscription, CoinSnapshot

@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'coin', 'time_add')


@admin.register(BotUser)
class BotUserAdmin(admin.ModelAdmin):
    list_display = ('telegram_id',)

@admin.register(CoinSnapshot)
class CoinSnapshotAdmin(admin.ModelAdmin):
    list_display = ('name', 'symbol', 'price', 'updated_at')

