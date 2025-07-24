from django.contrib import admin
from subscriptions.models import BotUser, Subscription, CoinSnapshot, CoinDailyStat

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
