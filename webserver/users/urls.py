from django.urls import path
from . import views

urlpatterns = [
    path('account/model/', views.ModelConfigView.as_view(), name='model_config'),
]
