__author__ = 'Irwan Fathurrahman <irwan@kartoza.com>'
__date__ = '28/01/19'

from rest_framework import authentication
from rest_framework import exceptions
from api.models.user_api_key import UserApiKey


class APIKeyAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        api_key = request.GET.get('api-key', None)
        if not api_key:
            raise exceptions.AuthenticationFailed('api-key is needed')
        user = UserApiKey.get_user_from_api_key(api_key)
        if not user:
            raise exceptions.AuthenticationFailed('api-key is invalid')

        return (user, None)
