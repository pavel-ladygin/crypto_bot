"""Django Admin configuration for chart vision models."""

from django.contrib import admin

from .models import BybitKline, ChartVisionResult


@admin.register(BybitKline)
class BybitKlineAdmin(admin.ModelAdmin):
    list_display = [
        "symbol",
        "interval",
        "open_time",
        "open_price",
        "close_price",
        "volume",
    ]
    list_filter = ["symbol", "interval", "source"]
    search_fields = ["symbol"]
    date_hierarchy = "open_time"
    readonly_fields = ["created_at"]


@admin.register(ChartVisionResult)
class ChartVisionResultAdmin(admin.ModelAdmin):
    list_display = [
        "symbol",
        "interval",
        "source",
        "predicted_label",
        "confidence",
        "model_version",
        "created_at",
    ]
    list_filter = [
        "source",
        "predicted_label",
        "symbol",
        "interval",
        "model_version",
        "created_at",
    ]
    search_fields = ["symbol", "model_version", "predicted_label"]
    readonly_fields = ["created_at"]
