# ml/prepare_dataset.py

import pandas as pd
from datasets import load_dataset
from pathlib import Path
import sys
import os

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Настраиваем Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
import django
django.setup()

# Теперь можем импортировать Django модели
from subscriptions.models import NewsArticle, NewsSentiment


class CryptoDatasetBuilder:
    """
    Сборщик датасета для обучения крипто-NLP модели
    """
    
    def __init__(self, output_dir='ml/data'):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def load_financial_phrasebank(self):
        """Загружаем Financial Phrase Bank"""
        print("📥 Загружаю Financial Phrase Bank...")
        
        dataset = load_dataset("financial_phrasebank", "sentences_allagree")
        
        # Преобразуем в DataFrame
        df = pd.DataFrame(dataset['train'])
        
        # Маппинг labels: 0=negative, 1=neutral, 2=positive
        label_map = {0: 'negative', 1: 'neutral', 2: 'positive'}
        df['sentiment'] = df['label'].map(label_map)
        df = df.rename(columns={'sentence': 'text'})
        df = df[['text', 'sentiment']]
        
        print(f"✅ Загружено {len(df)} примеров")
        return df
    
    def load_news_from_db(self):
        """Загружаем новости из вашей БД"""
        print("📥 Загружаю новости из БД...")
        
        # Новости с уже проставленным sentiment (от FinBERT)
        news_qs = NewsArticle.objects.filter(
            newssentiment__isnull=False
        ).select_related('newssentiment')[:10000]
        
        data = []
        for article in news_qs:
            text = f"{article.title}. {article.description or ''}"
            sentiment = article.newssentiment.sentiment_label
            
            # Нормализуем labels
            if sentiment in ['positive', 'negative', 'neutral']:
                data.append({'text': text, 'sentiment': sentiment})
        
        if data:
            df = pd.DataFrame(data)
            print(f"✅ Загружено {len(df)} новостей из БД")
            return df
        else:
            print("⚠️ Нет новостей с sentiment в БД")
            return pd.DataFrame()
    
    def combine_datasets(self):
        """
        Объединяет все датасеты
        """
        print("\n🔄 Объединяю датасеты...\n")
        
        dfs = []
        
        # 1. Financial Phrase Bank (основа)
        try:
            df1 = self.load_financial_phrasebank()
            dfs.append(df1)
        except Exception as e:
            print(f"⚠️ Ошибка Financial Phrase Bank: {e}")
        
        # 2. Ваши новости из БД
        try:
            df2 = self.load_news_from_db()
            if not df2.empty:
                dfs.append(df2)
        except Exception as e:
            print(f"⚠️ Ошибка загрузки из БД: {e}")
        
        # Объединяем
        if not dfs:
            print("❌ Нет данных для объединения!")
            return None
        
        combined = pd.concat(dfs, ignore_index=True)
        
        # Убираем дубликаты
        combined = combined.drop_duplicates(subset=['text'])
        
        print(f"\n📊 Статистика датасета:")
        print(f"   Всего примеров: {len(combined)}")
        print(f"\n   По классам:")
        print(combined['sentiment'].value_counts())
        
        # Сохраняем
        output_file = self.output_dir / 'combined_dataset.csv'
        combined.to_csv(output_file, index=False)
        print(f"\n✅ Сохранено в {output_file}")
        
        return combined


if __name__ == '__main__':
    print("="*60)
    print("📊 ПОДГОТОВКА ДАТАСЕТА")
    print("="*60)
    
    builder = CryptoDatasetBuilder()
    dataset = builder.combine_datasets()
    
    if dataset is not None:
        print(f"\n✅ Датасет готов! Можно начинать обучение.")
    else:
        print(f"\n❌ Не удалось создать датасет")
