from allauth.socialaccount.models import SocialAccount, SocialToken
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views import View

from .forms import HFModelConfigForm, ModelConfigForm

HF_INFERENCE_URL     = 'https://router.huggingface.co/v1'
GITHUB_INFERENCE_URL = 'https://models.inference.ai.azure.com'

CURATED_HF_MODELS = [
    {'id': 'Qwen/Qwen2.5-Coder-32B-Instruct',          'name': 'Qwen2.5-Coder 32B',  'tag': 'Coding',    'desc': 'Best in class for code generation'},
    {'id': 'Qwen/Qwen2.5-72B-Instruct',                 'name': 'Qwen2.5 72B',         'tag': 'General',   'desc': 'Strong all-around performance'},
    {'id': 'meta-llama/Llama-3.3-70B-Instruct',         'name': 'Llama 3.3 70B',       'tag': 'General',   'desc': "Meta's latest flagship"},
    {'id': 'meta-llama/Llama-3.1-8B-Instruct',          'name': 'Llama 3.1 8B',        'tag': 'Fast',      'desc': 'Lightweight, low latency'},
    {'id': 'mistralai/Mistral-7B-Instruct-v0.3',        'name': 'Mistral 7B',           'tag': 'Fast',      'desc': 'Efficient, great throughput'},
    {'id': 'deepseek-ai/DeepSeek-R1-Distill-Qwen-32B', 'name': 'DeepSeek R1 32B',     'tag': 'Reasoning', 'desc': 'Strong on complex problems'},
]

CURATED_GH_MODELS = [
    {'id': 'gpt-4o-mini',              'name': 'GPT-4o mini',      'tag': 'Fast',      'desc': 'Fast and cost-efficient'},
    {'id': 'gpt-4o',                   'name': 'GPT-4o',           'tag': 'General',   'desc': 'OpenAI flagship model'},
    {'id': 'Llama-3.3-70B-Instruct',  'name': 'Llama 3.3 70B',   'tag': 'General',   'desc': "Meta's latest open model"},
    {'id': 'Mistral-large',            'name': 'Mistral Large',    'tag': 'Reasoning', 'desc': 'Strong reasoning and code'},
]


def _social(user, provider):
    return SocialAccount.objects.filter(user=user, provider=provider).first()


def _get_token(social):
    if social:
        token = SocialToken.objects.filter(account=social).first()
        return token.token if token else None
    return None


@method_decorator(login_required, name='dispatch')
class ModelConfigView(View):
    template_name = 'users/model_config.html'

    def _context(self, user, form):
        hf = _social(user, 'huggingface')
        gh = _social(user, 'github')
        return {
            'form': form,
            'is_hf_user': bool(hf),
            'is_gh_user': bool(gh),
            'curated_models': CURATED_GH_MODELS if gh else (CURATED_HF_MODELS if hf else []),
            'inference_url': GITHUB_INFERENCE_URL if gh else (HF_INFERENCE_URL if hf else ''),
        }

    def get(self, request):
        hf = _social(request.user, 'huggingface')
        gh = _social(request.user, 'github')
        use_simple = bool(hf or gh)
        form = HFModelConfigForm(instance=request.user) if use_simple else ModelConfigForm(instance=request.user)
        return render(request, self.template_name, self._context(request.user, form))

    def post(self, request):
        hf = _social(request.user, 'huggingface')
        gh = _social(request.user, 'github')

        if gh:
            form = HFModelConfigForm(request.POST, instance=request.user)
            if form.is_valid():
                user = form.save(commit=False)
                user.model_api_url = GITHUB_INFERENCE_URL
                user.model_api_key = _get_token(gh) or ''
                user.save()
                return redirect('model_config')
        elif hf:
            form = HFModelConfigForm(request.POST, instance=request.user)
            if form.is_valid():
                user = form.save(commit=False)
                user.model_api_url = HF_INFERENCE_URL
                user.model_api_key = _get_token(hf) or ''
                user.save()
                return redirect('model_config')
        else:
            form = ModelConfigForm(request.POST, instance=request.user)
            if form.is_valid():
                form.save()
                return redirect('model_config')

        return render(request, self.template_name, self._context(request.user, form))
