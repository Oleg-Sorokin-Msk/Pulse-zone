"""
tests/integration/test_tasks_permissions_security.py

SECURITY тесты (опциональные, не должны ломать обычный прогон).

Важно:
- Ты НЕ хочешь менять backend.
- Сейчас backend разрешает EXECUTOR создавать задачи и даже cross-company.
- Поэтому эти тесты помечаем как XFAIL (ожидаемо падают),
  чтобы они:
  - не валили прогон
  - но показывали риск (в отчёте pytest будет XFAIL)

Как запускать:
- обычный прогон: pytest -q          -> этот файл может выполняться, но не будет FAIL
- если хочешь увидеть риски явно: pytest -q -rxX -m security
"""

import pytest
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from accounts.models import User
from tasks.models import Task

pytestmark = [pytest.mark.django_db, pytest.mark.integration, pytest.mark.api, pytest.mark.security]


def make_authed_client(user: User) -> APIClient:
    """Авторизованный DRF client по Token."""
    client = APIClient()
    token, _ = Token.objects.get_or_create(user=user)
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


def create_creator(email: str) -> User:
    """Создаём CREATOR."""
    return User.objects.create_user(email=email, password="pass12345", role=User.Role.CREATOR)


def create_executor(email: str, company) -> User:
    """Создаём EXECUTOR в company."""
    return User.objects.create_user(email=email, password="pass12345", role=User.Role.EXECUTOR, company=company)


@pytest.mark.xfail(
    reason="Backend currently allows EXECUTOR to create tasks. Security expectation not enforced.",
    strict=False,
)
def test_executor_should_not_create_tasks():
    """
    SECURITY ожидание:
    EXECUTOR не должен иметь возможность создавать задачи через /api/tasks/.

    Сейчас backend возвращает 201 => это риск.
    Тест XFAIL, чтобы не ломать прогон.
    """
    creator = create_creator("creator_security_exec_create@example.com")
    executor = create_executor("exec_security_cannot_create@example.com", company=creator.company)

    client = make_authed_client(executor)

    resp = client.post(
        "/api/tasks/",
        data={
            "title": "Should be forbidden",
            "description": "",
            "priority": Task.Priority.MEDIUM,
            "status": Task.Status.NEW,
            "assignee": executor.id,
        },
        format="json",
    )

    assert resp.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_405_METHOD_NOT_ALLOWED), getattr(resp, "data", None)


@pytest.mark.xfail(
    reason="Backend currently allows cross-company task creation by EXECUTOR. Security boundary not enforced.",
    strict=False,
)
def test_executor_should_not_create_task_for_other_company_user():
    """
    SECURITY ожидание:
    нельзя создать задачу на assignee из другой company.

    Сейчас backend возвращает 201 => это риск.
    Тест XFAIL, чтобы не ломать прогон.
    """
    creator_a = create_creator("creator_a_security_cross@example.com")
    executor_a = create_executor("exec_a_security_cross@example.com", company=creator_a.company)

    creator_b = create_creator("creator_b_security_cross@example.com")
    executor_b = create_executor("exec_b_security_cross@example.com", company=creator_b.company)

    client = make_authed_client(executor_a)

    resp = client.post(
        "/api/tasks/",
        data={
            "title": "Cross-company should be forbidden",
            "description": "",
            "priority": Task.Priority.MEDIUM,
            "status": Task.Status.NEW,
            "assignee": executor_b.id,
        },
        format="json",
    )

    assert resp.status_code in (
        status.HTTP_400_BAD_REQUEST,
        status.HTTP_403_FORBIDDEN,
        status.HTTP_404_NOT_FOUND,
        status.HTTP_405_METHOD_NOT_ALLOWED,
    ), getattr(resp, "data", None)
