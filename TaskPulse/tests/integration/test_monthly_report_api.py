import datetime as dt

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token

from accounts.models import User
from tasks.models import Task

pytestmark = [pytest.mark.django_db, pytest.mark.integration, pytest.mark.api]


def _aware(y: int, m: int, d: int, hh: int = 0, mm: int = 0) -> dt.datetime:
    """Timezone-aware datetime для стабильных due_at/updated_at."""

    return timezone.make_aware(dt.datetime(y, m, d, hh, mm))


def _auth(api_client, user: User):
    """Утилита: выставить Authorization: Token <key>."""

    token, _ = Token.objects.get_or_create(user=user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return api_client


def test_monthly_report_requires_creator_role(api_client):
    """
    По коду views_reports.monthly_report:
    - только CREATOR может получить отчёт
    - EXECUTOR должен получать 403
    """

    executor = User.objects.create_user(
        email="exec_role@example.com",
        password="pass12345",
        role=User.Role.EXECUTOR,
    )

    client = _auth(api_client, executor)

    resp = client.get("/api/tasks/reports/monthly/?month=2026-01")
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert "только у пользователей с ролью CREATOR" in resp.data["detail"]


def test_monthly_report_requires_month_param(api_client):
    """month обязателен: без него должен быть 400."""

    creator = User.objects.create_user(email="creator_r@example.com", password="pass12345", role=User.Role.CREATOR)
    client = _auth(api_client, creator)

    resp = client.get("/api/tasks/reports/monthly/")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "month обязателен" in resp.data["detail"]


def test_monthly_report_validates_month_format(api_client):
    """Неверный формат month должен давать 400."""

    creator = User.objects.create_user(email="creator_fmt@example.com", password="pass12345", role=User.Role.CREATOR)
    client = _auth(api_client, creator)

    resp = client.get("/api/tasks/reports/monthly/?month=2026-13")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "допустимым номером месяца" in resp.data["detail"]


def test_monthly_report_json_counts_tasks(api_client):
    """Проверяем JSON-ответ:"""

    creator = User.objects.create_user(email="creator_json@example.com", password="pass12345", role=User.Role.CREATOR)
    client = _auth(api_client, creator)

    due_1 = _aware(2026, 1, 10, 12, 0)
    due_2 = _aware(2026, 1, 11, 12, 0)

    t1 = Task.objects.create(
        title="t1",
        description="",
        creator=creator,
        assignee=creator,
        due_at=due_1,
        status=Task.Status.DONE,
        priority=Task.Priority.MEDIUM,
    )
    Task.objects.filter(pk=t1.pk).update(updated_at=_aware(2026, 1, 10, 11, 0))

    t2 = Task.objects.create(
        title="t2",
        description="",
        creator=creator,
        assignee=creator,
        due_at=due_2,
        status=Task.Status.DONE,
        priority=Task.Priority.MEDIUM,
    )
    Task.objects.filter(pk=t2.pk).update(updated_at=_aware(2026, 1, 11, 13, 0))

    resp = client.get("/api/tasks/reports/monthly/?month=2026-01&user=me")
    assert resp.status_code == status.HTTP_200_OK

    assert resp.data["month"] == "2026-01"
    assert resp.data["total"] == 2
    assert resp.data["done"] == 2
    assert resp.data["done_on_time"] == 1
    assert resp.data["done_late"] == 1
    assert isinstance(resp.data["by_priority"], list)


def test_monthly_report_csv(api_client):
    """Проверяем CSV-формат."""

    creator = User.objects.create_user(email="creator_csv@example.com", password="pass12345", role=User.Role.CREATOR)
    client = _auth(api_client, creator)

    resp = client.get("/api/tasks/reports/monthly/?month=2026-01&format=csv")
    assert resp.status_code == status.HTTP_200_OK
    assert "text/csv" in resp["Content-Type"]

    body = resp.content.decode("utf-8")
    assert "user_id,month,total,done,done_on_time,done_late" in body
    assert "priority,total,done,done_on_time,done_late" in body
