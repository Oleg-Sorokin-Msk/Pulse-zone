import pytest

from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

User = get_user_model()


@pytest.fixture
def api_client():
    """APIClient без авторизации.
    """
    return APIClient()


@pytest.fixture
def user(db):
    """
    Создаём пользователя в тестовой БД."""
    return User.objects.create_user(
        email="user@example.com",
        password="pass12345",
        first_name="User",
        last_name="Example",
    )


@pytest.fixture
def token(user):
    """Создаём DRF Token для TokenAuthentication."""

    return Token.objects.create(user=user)


@pytest.fixture
def auth_client(api_client, token):
    """DRF APIClient с авторизацией."""

    api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return api_client
