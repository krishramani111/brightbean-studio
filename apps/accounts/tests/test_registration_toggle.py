"""Tests for registration enable/disable toggle."""

from datetime import timedelta

import pytest
from allauth.socialaccount.models import SocialAccount as AllAuthSocialAccount
from allauth.socialaccount.models import SocialLogin
from django.test import Client, RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.adapters import AccountAdapter, SocialAccountAdapter
from apps.accounts.models import User
from apps.members.models import Invitation
from apps.organizations.models import Organization


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def rf():
    return RequestFactory()


@pytest.fixture
def organization(db):
    return Organization.objects.create(name="Acme Corp")


@pytest.fixture
def owner(db):
    return User.objects.create_user(email="owner@example.com", password="password123")


@pytest.fixture
def active_invitation(db, organization, owner):
    return Invitation.objects.create(
        organization=organization,
        email="invitee@example.com",
        invited_by=owner,
        expires_at=timezone.now() + timedelta(days=7),
    )


@pytest.fixture
def expired_invitation(db, organization, owner):
    return Invitation.objects.create(
        organization=organization,
        email="expired@example.com",
        invited_by=owner,
        expires_at=timezone.now() - timedelta(days=1),
    )


@pytest.mark.django_db
class TestRegistrationToggleUI:
    @override_settings(REGISTRATION_ENABLED=True)
    def test_signup_enabled_shows_link_and_renders_form(self, client):
        login_resp = client.get(reverse("account_login"))
        assert login_resp.status_code == 200
        assert "Sign up" in login_resp.content.decode()

        signup_resp = client.get(reverse("account_signup"))
        assert signup_resp.status_code == 200
        assert "Create your account" in signup_resp.content.decode()

    @override_settings(REGISTRATION_ENABLED=False)
    def test_signup_disabled_hides_link_and_blocks_page(self, client):
        login_resp = client.get(reverse("account_login"))
        assert login_resp.status_code == 200
        # The signup link to account_signup is hidden
        content = login_resp.content.decode()
        assert reverse("account_signup") not in content

        signup_resp = client.get(reverse("account_signup"))
        assert signup_resp.status_code == 403
        assert "Registration Closed" in signup_resp.content.decode()
        assert "Public signups are not available" in signup_resp.content.decode()


@pytest.mark.django_db
class TestRegistrationToggleAPIAndSubmission:
    @override_settings(REGISTRATION_ENABLED=False)
    def test_disabled_form_post_rejected(self, client):
        resp = client.post(
            reverse("account_signup"),
            {"email": "newuser@example.com", "password": "securepassword123"},
        )
        assert resp.status_code == 403
        assert "Registration Closed" in resp.content.decode()
        assert not User.objects.filter(email="newuser@example.com").exists()

    @override_settings(REGISTRATION_ENABLED=False)
    def test_disabled_json_request_returns_json_403(self, client):
        resp = client.get(reverse("account_signup"), HTTP_ACCEPT="application/json")
        assert resp.status_code == 403
        data = resp.json()
        assert data["error"] == "registration_disabled"
        assert "disabled" in data["detail"].lower()

        post_resp = client.post(
            reverse("account_signup"),
            {"email": "jsonuser@example.com"},
            HTTP_ACCEPT="application/json",
        )
        assert post_resp.status_code == 403
        assert post_resp.json()["error"] == "registration_disabled"


@pytest.mark.django_db
class TestRegistrationToggleWithInvitations:
    @override_settings(REGISTRATION_ENABLED=False)
    def test_active_invitation_allows_signup(self, client, active_invitation):
        # Place invitation token in session
        session = client.session
        session["pending_invite_token"] = active_invitation.token
        session.save()

        resp = client.get(reverse("account_signup"))
        assert resp.status_code == 200
        assert "Create your account" in resp.content.decode()
        assert active_invitation.email in resp.content.decode()

    @override_settings(REGISTRATION_ENABLED=False)
    def test_expired_invitation_denied(self, client, expired_invitation):
        session = client.session
        session["pending_invite_token"] = expired_invitation.token
        session.save()

        resp = client.get(reverse("account_signup"))
        assert resp.status_code == 403
        assert "Registration Closed" in resp.content.decode()


@pytest.mark.django_db
class TestAdaptersRegistrationOpen:
    @override_settings(REGISTRATION_ENABLED=True)
    def test_adapters_open_by_default(self, rf):
        account_adapter = AccountAdapter()
        social_adapter = SocialAccountAdapter()
        req = rf.get("/")

        assert account_adapter.is_open_for_signup(req) is True

        user = User(email="test@example.com")
        account = AllAuthSocialAccount(provider="google", uid="g123")
        sociallogin = SocialLogin(user=user, account=account)
        assert social_adapter.is_open_for_signup(req, sociallogin) is True

    @override_settings(REGISTRATION_ENABLED=False)
    def test_adapters_closed_when_disabled(self, rf):
        account_adapter = AccountAdapter()
        social_adapter = SocialAccountAdapter()
        req = rf.get("/")
        req.session = {}

        assert account_adapter.is_open_for_signup(req) is False

        user = User(email="test@example.com")
        account = AllAuthSocialAccount(provider="google", uid="g123")
        sociallogin = SocialLogin(user=user, account=account)
        assert social_adapter.is_open_for_signup(req, sociallogin) is False

    @override_settings(REGISTRATION_ENABLED=False)
    def test_adapters_allow_valid_invite_session(self, rf, active_invitation):
        account_adapter = AccountAdapter()
        social_adapter = SocialAccountAdapter()
        req = rf.get("/")
        req.session = {"pending_invite_token": active_invitation.token}

        assert account_adapter.is_open_for_signup(req) is True

        user = User(email="invitee@example.com")
        account = AllAuthSocialAccount(provider="google", uid="g123")
        sociallogin = SocialLogin(user=user, account=account)
        assert social_adapter.is_open_for_signup(req, sociallogin) is True
