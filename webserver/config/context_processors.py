from django.conf import settings


def theme(request):
    return {'theme': getattr(settings, 'SITE_THEME', 'light')}
