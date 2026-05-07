from allauth.socialaccount.providers.oauth2.provider import OAuth2Provider


class HuggingFaceProvider(OAuth2Provider):
    id = 'huggingface'
    name = 'HuggingFace'

    def extract_uid(self, data):
        return str(data['sub'])

    def extract_common_fields(self, data):
        return {
            'email':    data.get('email', ''),
            'username': data.get('preferred_username', ''),
            'name':     data.get('name', ''),
        }

    def get_default_scope(self):
        return ['openid', 'profile', 'email', 'inference-api']


provider_classes = [HuggingFaceProvider]
