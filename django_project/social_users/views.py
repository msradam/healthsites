# -*- coding: utf-8 -*-
import os
import logging

from django.conf import settings
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect, HttpResponseForbidden
from django.views.generic import TemplateView, View
from rest_framework.views import APIView

from braces.views import LoginRequiredMixin

from api.models.user_api_key import UserApiKey
from localities.models import Locality
from social_users.models import (
    Profile, Organisation, TrustedUser, OrganisationSupported)
from social_users.utils import get_profile

LOG = logging.getLogger(__name__)


class UserProfilePage(LoginRequiredMixin, TemplateView):
    template_name = 'social_users/profilepage.html'

    def get_context_data(self, *args, **kwargs):
        context = super(UserProfilePage, self).get_context_data(*args, **kwargs)
        context['auths'] = [
            auth.provider for auth in self.request.user.social_auth.all()
        ]
        return context


class ProfilePage(TemplateView):
    template_name = 'social_users/profile.html'

    def get_context_data(self, *args, **kwargs):
        """
        *debug* toggles GoogleAnalytics support on the main page
        """

        context = super(ProfilePage, self).get_context_data(*args, **kwargs)
        context['api_keys'] = None
        try:
            user = User.objects.get(username=kwargs['username'])
            user = get_profile(user, self.request)
            osm_user = False

            if self.request.user == user:
                # this is for checking availability old data
                old_data = Locality.objects.filter(
                    changeset__social_user__username=user, migrated=False
                )

                if old_data:
                    context['old_data_available'] = True

                pathname = \
                    os.path.join(
                        settings.CACHE_DIR, 'data-migration-progress')
                progress_file = \
                    os.path.join(pathname, '{}.txt'.format(user))
                found = os.path.exists(progress_file)

                if found:
                    context['data_migration_in_progress'] = True

                autogenerate_api_key = False
                if user.is_superuser:
                    autogenerate_api_key = True
                context['api_keys'] = UserApiKey.get_user_api_key(
                    self.request.user, autogenerate=autogenerate_api_key)
        except User.DoesNotExist:
            user = {
                'username': kwargs['username']
            }
            osm_user = True

        context['user'] = user
        context['osm_user'] = osm_user
        context['osm_API'] = settings.OSM_API_URL
        return context


class UserSigninPage(TemplateView):
    template_name = 'social_users/signinpage.html'


class LogoutUser(View):
    def get(self, request, *args, **kwargs):
        auth_logout(request)
        return HttpResponseRedirect('/')


def save_profile(backend, user, response, *args, **kwargs):
    # get old user
    if kwargs['is_new']:
        if 'username' in kwargs['details']:
            new_username = kwargs['details']['username']
            new_username = new_username.replace(' ', '')
            if user.username != new_username:
                try:
                    old_username = user.username
                    user = User.objects.get(username=new_username)
                    User.objects.get(username=old_username).delete()
                except User.DoesNotExist:
                    pass

    profile_picture = None
    if backend.name == 'facebook':
        profile_picture = 'http://graph.facebook.com/%s/picture?type=large' % response['id']
    elif backend.name == 'twitter':
        profile_picture = response.get('profile_image_url', '').replace('_normal', '')
    elif backend.name == 'google-oauth2':
        profile_picture = response['image'].get('url')
    elif backend.name == 'openstreetmap':
        profile_picture = response['avatar']

    profile, created = Profile.objects.get_or_create(user=user)
    if profile_picture:
        profile.profile_picture = profile_picture
    profile.save()

    kwargs['request'].session['social_auth'] = {
        'profile_picture': profile_picture,
        'provider': backend.name
    }

    return {'user': user}


class ProfileUpdate(APIView):
    """API for listing all database record of source reference."""

    def post(self, request, *args):
        if not request.user.is_authenticated():
            return HttpResponseForbidden()
        data = request.data
        request.user.first_name = data.get('first-name', None)
        request.user.last_name = data.get('last-name', None)
        request.user.email = data.get('email', None)
        request.user.save()

        org_name = data.get('organisation-name', None)
        site_url = data.get('site-url', None)
        if org_name and site_url:
            if site_url:
                site, created = Site.objects.get_or_create(
                    domain=site_url, name=site_url)
                organisation, created = Organisation.objects.get_or_create(
                    name=org_name,
                    site=site
                )
                trusted_user, created = TrustedUser.objects.get_or_create(user=request.user)
                OrganisationSupported.objects.get_or_create(
                    user=trusted_user,
                    organisation=organisation)

        UserApiKey.get_user_api_key(
            self.request.user, autogenerate=True)

        return HttpResponseRedirect(
            reverse('profile', kwargs={'username': request.user.username}))
