from allauth.socialaccount.models import SocialAccount, SocialToken
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views import View

from .forms import HFModelConfigForm, ModelConfigForm

HF_INFERENCE_URL = 'https://api-inference.huggingface.co/v1'

CURATED_HF_MODELS = [
    {'id': 'Qwen/Qwen2.5-Coder-32B-Instruct',          'name': 'Qwen2.5-Coder 32B',  'tag': 'Coding',     'desc': 'Best in class for code generation'},
    {'id': 'Qwen/Qwen2.5-72B-Instruct',                 'name': 'Qwen2.5 72B',         'tag': 'General',    'desc': 'Strong all-around performance'},
    {'id': 'meta-llama/Llama-3.3-70B-Instruct',         'name': 'Llama 3.3 70B',       'tag': 'General',    'desc': "Meta's latest flagship"},
    {'id': 'meta-llama/Llama-3.1-8B-Instruct',          'name': 'Llama 3.1 8B',        'tag': 'Fast',       'desc': 'Lightweight, low latency'},
    {'id': 'mistralai/Mistral-7B-Instruct-v0.3',        'name': 'Mistral 7B',           'tag': 'Fast',       'desc': 'Efficient, great throughput'},
    {'id': 'deepseek-ai/DeepSeek-R1-Distill-Qwen-32B', 'name': 'DeepSeek R1 32B',     'tag': 'Reasoning',  'desc': 'Strong on complex problems'},
]


def _hf_social(user):
    return SocialAccount.objects.filter(user=user, provider='huggingface').first()


def _get_hf_token(social):
    if social:
        token = SocialToken.objects.filter(account=social).first()
        return token.token if token else None
    return None


@method_decorator(login_required, name='dispatch')
class ModelConfigView(View):
    template_name = 'users/model_config.html'

    def get(self, request):
        social = _hf_social(request.user)
        form = HFModelConfigForm(instance=request.user) if social else ModelConfigForm(instance=request.user)
        ctx = {'form': form, 'is_hf_user': bool(social), 'curated_models': CURATED_HF_MODELS if social else []}
        return render(request, self.template_name, ctx)

    def post(self, request):
        social = _hf_social(request.user)
        if social:
            form = HFModelConfigForm(request.POST, instance=request.user)
            if form.is_valid():
                user = form.save(commit=False)
                user.model_api_url = HF_INFERENCE_URL
                hf_token = _get_hf_token(social)
                if hf_token:
                    user.model_api_key = hf_token
                user.save()
                return redirect('model_config')
        else:
            form = ModelConfigForm(request.POST, instance=request.user)
            if form.is_valid():
                form.save()
                return redirect('model_config')
        ctx = {'form': form, 'is_hf_user': bool(social), 'curated_models': CURATED_HF_MODELS if social else []}
        return render(request, self.template_name, ctx)
