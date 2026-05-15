from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    model_api_url = models.CharField(max_length=500, blank=True)
    model_name    = models.CharField(max_length=200, blank=True)
    model_api_key = models.CharField(max_length=500, blank=True)

    @property
    def is_model_configured(self):
        if not (self.model_api_url and self.model_name):
            return False
        if self.model_api_key:
            return True
        # HF OAuth users don't store the key explicitly — token is fetched at run time
        return self.socialaccount_set.filter(provider='huggingface').exists()
