from django.urls import path
from . import views

urlpatterns = [
    path('runs/', views.RunHistoryView.as_view(), name='run_history'),
    path('runs/submit/', views.SubmitRunView.as_view(), name='run_submit'),
    path('runs/<uuid:uuid>/status/', views.RunStatusView.as_view(), name='run_status'),
    path('runs/<uuid:uuid>/', views.RunDetailView.as_view(), name='run_detail'),
]
