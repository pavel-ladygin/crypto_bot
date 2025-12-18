# subscriptions/urls.py

from django.urls import path
from . import views

urlpatterns = [
    # Старые endpoints (для совместимости)
    path('api/predict/<str:coin_symbol>/', views.get_prediction, name='get_prediction'),
    path('api/predictions/', views.get_all_predictions, name='get_all_predictions'),
    
    # Новые endpoints для направлений
    path('api/direction/<str:coin_symbol>/', views.get_direction_prediction, name='get_direction_prediction'),
    path('api/directions/', views.get_all_direction_predictions, name='get_all_direction_predictions'),
    
    # Информация о модели
    path('api/model/info/', views.get_model_info, name='get_model_info'),
]
