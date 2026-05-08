from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    model_api_url = models.CharField(max_length=500, blank=True)
    model_name    = models.CharField(max_length=200, blank=True)
    model_api_key = models.CharField(max_length=500, blank=True)
