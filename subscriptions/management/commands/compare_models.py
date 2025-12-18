# subscriptions/management/commands/compare_models.py

from django.core.management.base import BaseCommand
from subscriptions.models import NewsSentiment, CustomModelSentiment
from django.db.models import Count, Avg

class Command(BaseCommand):
    help = 'Сравнение результатов FinBERT и Custom модели'

    def handle(self, *args, **options):
        self.stdout.write("="*60)
        self.stdout.write("📊 СРАВНЕНИЕ МОДЕЛЕЙ")
        self.stdout.write("="*60)
        
        # FinBERT статистика
        finbert_count = NewsSentiment.objects.count()
        finbert_confidence = NewsSentiment.objects.aggregate(Avg('confidence'))['confidence__avg']
        finbert_dist = NewsSentiment.objects.values('sentiment_label').annotate(count=Count('id'))
        
        self.stdout.write(f"\n🤖 FinBERT (основная модель)")
        self.stdout.write(f"   Количество анализов: {finbert_count}")
        self.stdout.write(f"   Средняя уверенность: {finbert_confidence*100:.1f}%")
        self.stdout.write(f"   Распределение:")
        for item in finbert_dist:
            emoji = {'negative': '🔴', 'neutral': '⚪', 'positive': '🟢'}
            self.stdout.write(f"      {emoji.get(item['sentiment_label'])} {item['sentiment_label']}: {item['count']}")
        
        # Custom Model статистика
        custom_count = CustomModelSentiment.objects.count()
        if custom_count > 0:
            custom_confidence = CustomModelSentiment.objects.aggregate(Avg('confidence'))['confidence__avg']
            custom_dist = CustomModelSentiment.objects.values('sentiment_label').annotate(count=Count('id'))
            
            self.stdout.write(f"\n🤖 Custom DistilBERT")
            self.stdout.write(f"   Количество анализов: {custom_count}")
            self.stdout.write(f"   Средняя уверенность: {custom_confidence*100:.1f}%")
            self.stdout.write(f"   Распределение:")
            for item in custom_dist:
                emoji = {'negative': '🔴', 'neutral': '⚪', 'positive': '🟢'}
                self.stdout.write(f"      {emoji.get(item['sentiment_label'])} {item['sentiment_label']}: {item['count']}")
        else:
            self.stdout.write(f"\n⚠️ Custom модель еще не анализировала новости")
        
        self.stdout.write("\n" + "="*60)
