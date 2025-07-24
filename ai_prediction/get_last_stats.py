# services.py (можно создать отдельный файл)
from datetime import date, timedelta
from subscriptions.models import CoinDailyStat

def get_last_days_stats(name, days=7):
    today = date.today()
    start_date = today - timedelta(days=days)
    stats = CoinDailyStat.objects.filter(
        name=name,
        date__gte=start_date,
        date__lte=today
    ).order_by('date')
    return stats