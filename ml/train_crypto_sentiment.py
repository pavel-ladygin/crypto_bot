# ml/train_improved.py

import pandas as pd
import torch
from torch.utils.data import Dataset
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    Trainer,
    TrainingArguments
)
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report
from sklearn.utils.class_weight import compute_class_weight
import numpy as np
from pathlib import Path


class CryptoSentimentDataset(Dataset):
    """Dataset для обучения"""
    
    def __init__(self, texts, labels, tokenizer, max_length=128):
        self.texts = texts
        self.labels = labels
        self.tokenizer = tokenizer
        self.max_length = max_length
    
    def __len__(self):
        return len(self.texts)
    
    def __getitem__(self, idx):
        text = str(self.texts[idx])
        label = self.labels[idx]
        
        encoding = self.tokenizer(
            text,
            add_special_tokens=True,
            max_length=self.max_length,
            padding='max_length',
            truncation=True,
            return_tensors='pt'
        )
        
        return {
            'input_ids': encoding['input_ids'].flatten(),
            'attention_mask': encoding['attention_mask'].flatten(),
            'labels': torch.tensor(label, dtype=torch.long)
        }


class ImprovedCryptoTrainer:
    """
    Улучшенный тренер с балансировкой классов
    """
    
    def __init__(self, data_path='ml/data/combined_dataset.csv'):
        self.data_path = Path(data_path)
        self.model_dir = Path('ml/models/crypto_sentiment')
        self.model_dir.mkdir(parents=True, exist_ok=True)
        
        self.label_map = {
            'negative': 0,
            'neutral': 1,
            'positive': 2
        }
        self.id2label = {v: k for k, v in self.label_map.items()}
        
        print("🚀 Инициализация улучшенного тренера...")
    
    def load_data(self):
        """Загрузка данных с балансировкой"""
        print(f"📥 Загружаю данные из {self.data_path}...")
        
        df = pd.read_csv(self.data_path)
        df = df[df['sentiment'].isin(['negative', 'neutral', 'positive'])]
        df['label'] = df['sentiment'].map(self.label_map)
        
        print(f"✅ Загружено {len(df)} примеров")
        print(f"\n📊 Исходное распределение:")
        print(df['sentiment'].value_counts())
        
        # Балансировка через undersampling majority класса
        min_class_size = df['sentiment'].value_counts().min()
        
        df_balanced = pd.concat([
            df[df['sentiment'] == 'negative'].sample(n=min_class_size, random_state=42),
            df[df['sentiment'] == 'neutral'].sample(n=min_class_size, random_state=42),
            df[df['sentiment'] == 'positive'].sample(n=min_class_size, random_state=42),
        ]).sample(frac=1, random_state=42)  # Перемешиваем
        
        print(f"\n⚖️ После балансировки:")
        print(df_balanced['sentiment'].value_counts())
        
        # Разделяем
        train_df, temp_df = train_test_split(
            df_balanced, test_size=0.3, random_state=42, stratify=df_balanced['label']
        )
        val_df, test_df = train_test_split(
            temp_df, test_size=0.5, random_state=42, stratify=temp_df['label']
        )
        
        print(f"\n✂️ Разделение:")
        print(f"   Train: {len(train_df)}")
        print(f"   Val: {len(val_df)}")
        print(f"   Test: {len(test_df)}")
        
        return train_df, val_df, test_df
    
    def train(self, model_name='prajjwal1/bert-tiny', epochs=5, batch_size=16, learning_rate=2e-5):
        """Обучение с балансировкой"""
        print(f"\n🎯 Обучение: {model_name}")
        
        train_df, val_df, test_df = self.load_data()
        
        print(f"\n📦 Загружаю модель...")
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForSequenceClassification.from_pretrained(
            model_name,
            num_labels=3,
            id2label=self.id2label,
            label2id=self.label_map
        )
        
        # Datasets
        train_dataset = CryptoSentimentDataset(
            train_df['text'].values,
            train_df['label'].values,
            tokenizer
        )
        
        val_dataset = CryptoSentimentDataset(
            val_df['text'].values,
            val_df['label'].values,
            tokenizer
        )
        
        # Class weights для loss function
        class_weights = compute_class_weight(
            'balanced',
            classes=np.unique(train_df['label']),
            y=train_df['label']
        )
        class_weights = torch.tensor(class_weights, dtype=torch.float)
        
        print(f"\n⚖️ Class weights: {class_weights.tolist()}")
        
        # Custom Trainer с weighted loss
        class WeightedTrainer(Trainer):
            def compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None):
                labels = inputs.pop("labels")
                outputs = model(**inputs)
                logits = outputs.logits
                loss_fct = torch.nn.CrossEntropyLoss(weight=class_weights.to(logits.device))
                loss = loss_fct(logits, labels)
                return (loss, outputs) if return_outputs else loss
        
        # Training arguments
        training_args = TrainingArguments(
            output_dir=str(self.model_dir / 'checkpoints'),
            num_train_epochs=epochs,
            per_device_train_batch_size=batch_size,
            per_device_eval_batch_size=batch_size,
            learning_rate=learning_rate,
            warmup_steps=100,
            weight_decay=0.01,
            logging_steps=50,
            eval_strategy='epoch',
            save_strategy='epoch',
            load_best_model_at_end=True,
            metric_for_best_model='accuracy',
        )
        
        def compute_metrics(pred):
            labels = pred.label_ids
            preds = pred.predictions.argmax(-1)
            acc = accuracy_score(labels, preds)
            return {'accuracy': acc}
        
        trainer = WeightedTrainer(
            model=model,
            args=training_args,
            train_dataset=train_dataset,
            eval_dataset=val_dataset,
            compute_metrics=compute_metrics,
        )
        
        print("\n🏋️ Обучение началось...")
        trainer.train()
        
        # Test evaluation
        print("\n📊 Оценка на test set...")
        test_dataset = CryptoSentimentDataset(
            test_df['text'].values,
            test_df['label'].values,
            tokenizer
        )
        
        predictions = trainer.predict(test_dataset)
        preds = predictions.predictions.argmax(-1)
        labels = predictions.label_ids
        
        print("\n" + "="*60)
        print("РЕЗУЛЬТАТЫ НА TEST SET:")
        print("="*60)
        print(f"\nAccuracy: {accuracy_score(labels, preds):.4f}")
        print("\nClassification Report:")
        print(classification_report(
            labels, preds,
            target_names=['negative', 'neutral', 'positive']
        ))
        
        # Сохраняем
        print(f"\n💾 Сохраняю модель...")
        model.save_pretrained(self.model_dir)
        tokenizer.save_pretrained(self.model_dir)
        
        print("✅ Обучение завершено!")
        
        return model, tokenizer, accuracy_score(labels, preds)


if __name__ == '__main__':
    print("="*60)
    print("🎓 УЛУЧШЕННОЕ ОБУЧЕНИЕ МОДЕЛИ")
    print("="*60)
    
    trainer = ImprovedCryptoTrainer()
    
    # Используем bert-tiny для быстрого теста
    model, tokenizer, accuracy = trainer.train(
        model_name='distilbert-base-uncased',  # ← ИЗМЕНИТЬ (было bert-tiny)
        epochs=5,                               # ← ИЗМЕНИТЬ (было 8)
        batch_size=16,                          # ← ИЗМЕНИТЬ (было 32)
        learning_rate=2e-5,
    )
    
    print(f"\n🎉 Финальная точность: {accuracy:.4f}")
