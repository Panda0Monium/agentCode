from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('socialaccounts/huggingface/', include('huggingface_provider.urls')),
    path('', include('problems.urls')),
    path('', include('users.urls')),
    path('', include('runs.urls')),
]
