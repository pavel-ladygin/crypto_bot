# Generated by Django 5.2.4 on 2025-07-22 20:59

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("subscriptions", "0002_coinsnapshot"),
    ]

    operations = [
        migrations.AlterField(
            model_name="subscription",
            name="coin",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                to="subscriptions.coinsnapshot",
            ),
        ),
    ]
