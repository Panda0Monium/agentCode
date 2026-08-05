from django.contrib import admin

from .models import Run


@admin.register(Run)
class RunAdmin(admin.ModelAdmin):
    list_display  = ('user', 'task_name', 'dataset', 'architecture', 'status',
                     'reward', 'tokens_used', 'created_at')
    list_filter   = ('status', 'dataset', 'architecture')
    readonly_fields = ('created_at', 'completed_at')
