from django.urls import path
from . import views

app_name = 'dataviz'  # important for template URL reversing

urlpatterns = [
    path('', views.home, name='home'),
    path('analysis/', views.data_analysis, name='data_analysis'),
]
