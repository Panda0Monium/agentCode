import requests

from allauth.socialaccount.providers.oauth2.views import (
    OAuth2Adapter,
    OAuth2CallbackView,
    OAuth2LoginView,
)

from .provider import HuggingFaceProvider


class HuggingFaceOAuth2Adapter(OAuth2Adapter):
    provider_id = HuggingFaceProvider.id
    access_token_url = 'https://huggingface.co/oauth/token'
    authorize_url    = 'https://huggingface.co/oauth/authorize'
    profile_url      = 'https://huggingface.co/oauth/userinfo'

    def complete_login(self, request, app, token, **kwargs):
        resp = requests.get(
            self.profile_url,
            headers={'Authorization': f'Bearer {token.token}'},
            timeout=10,
        )
        resp.raise_for_status()
        return self.get_provider().sociallogin_from_response(request, resp.json())


HuggingFaceProvider.oauth2_adapter_class = HuggingFaceOAuth2Adapter

oauth2_login    = OAuth2LoginView.adapter_view(HuggingFaceOAuth2Adapter)
oauth2_callback = OAuth2CallbackView.adapter_view(HuggingFaceOAuth2Adapter)
