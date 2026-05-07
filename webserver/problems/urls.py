from django.urls import path
from .views import HomeView, ProblemListView, ProblemDetailView, ProblemDetailTemplateView

urlpatterns = [
    path('', HomeView.as_view(), name='home'),
    path('problems/<int:pk>/', ProblemDetailTemplateView.as_view(), name='problem-detail-html'),
    path('api/problems/', ProblemListView.as_view(), name='problem-list'),
    path('api/problems/<int:pk>/', ProblemDetailView.as_view(), name='problem-detail'),
]
