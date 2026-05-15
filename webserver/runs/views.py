from allauth.socialaccount.models import SocialAccount, SocialToken
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.decorators import method_decorator
from django.views import View
from django_q.tasks import async_task

from .models import Run
from .tasks import execute_run


def _resolve_api_key(user):
    """Return the API key to use for this user, or None if unavailable."""
    if user.model_api_key:
        return user.model_api_key
    social = SocialAccount.objects.filter(user=user, provider='huggingface').first()
    if social:
        token = SocialToken.objects.filter(account=social).first()
        if token:
            return token.token
    return None


@method_decorator(login_required, name='dispatch')
class SubmitRunView(View):
    def post(self, request):
        task_name = request.POST.get('task_name', '').strip()
        dataset   = request.POST.get('dataset', '').strip()

        if not task_name or not dataset:
            return JsonResponse({'error': 'Missing task_name or dataset.'}, status=400)

        user = request.user
        if not user.is_model_configured:
            return JsonResponse({'error': 'Model not configured. Go to Settings first.'}, status=400)

        if not _resolve_api_key(user):
            return JsonResponse({
                'error': 'HuggingFace session token not found. Please log out and sign in again with Hugging Face.'
            }, status=400)

        run = Run.objects.create(user=user, task_name=task_name, dataset=dataset)
        async_task(execute_run, run.pk)
        return JsonResponse({'run_id': str(run.uuid)})


@method_decorator(login_required, name='dispatch')
class RunStatusView(View):
    def get(self, request, uuid):
        run = get_object_or_404(Run, uuid=uuid, user=request.user)
        return JsonResponse({
            'status':        run.status,
            'reward':        run.reward,
            'public_score':  run.public_score,
            'private_score': run.private_score,
            'lint_score':    run.lint_score,
            'error':         f'Run failed — ref: {run.uuid}' if run.status == Run.Status.FAILED else None,
        })


@method_decorator(login_required, name='dispatch')
class RunHistoryView(View):
    def get(self, request):
        runs = Run.objects.filter(user=request.user)
        return render(request, 'runs/history.html', {'runs': runs})


@method_decorator(login_required, name='dispatch')
class RunDetailView(View):
    def get(self, request, uuid):
        run = get_object_or_404(Run, uuid=uuid, user=request.user)
        return render(request, 'runs/detail.html', {'run': run})
