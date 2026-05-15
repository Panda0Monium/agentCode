import uuid as _uuid

from django.conf import settings
from django.db import models


class Run(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        RUNNING = 'running', 'Running'
        DONE    = 'done',    'Done'
        FAILED  = 'failed',  'Failed'

    uuid          = models.UUIDField(default=_uuid.uuid4, unique=True, editable=False)
    user          = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='runs')
    task_name     = models.CharField(max_length=200)
    dataset       = models.CharField(max_length=100)
    status        = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reward        = models.FloatField(null=True, blank=True)
    public_score  = models.FloatField(null=True, blank=True)
    private_score = models.FloatField(null=True, blank=True)
    lint_score    = models.FloatField(null=True, blank=True)
    error         = models.TextField(blank=True)
    trajectory    = models.JSONField(null=True, blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)
    started_at    = models.DateTimeField(null=True, blank=True)
    completed_at  = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
