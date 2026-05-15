from django import forms
from .models import User


class ModelConfigForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['model_api_url', 'model_name', 'model_api_key']
        labels = {
            'model_api_url': 'API Base URL',
            'model_name':    'Model Name',
            'model_api_key': 'API Key',
        }
        widgets = {
            'model_api_key': forms.PasswordInput(render_value=True),
        }
        help_texts = {
            'model_api_url': 'OpenAI-compatible base URL, e.g. https://api-inference.huggingface.co/v1',
            'model_name':    'Model ID as recognised by the provider.',
            'model_api_key': 'Stored in plaintext — use a dedicated key, not your main account password.',
        }


class HFModelConfigForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['model_name']
        labels = {'model_name': 'Model ID'}
        help_texts = {
            'model_name': 'HuggingFace model ID, e.g. Qwen/Qwen2.5-Coder-32B-Instruct',
        }
