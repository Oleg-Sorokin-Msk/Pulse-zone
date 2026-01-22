from datetime import datetime, timezone

import pytest
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from accounts.models import User
from tasks.models import Task

pytestmark = [pytest.mark.django_db, pytest.mark.e2e, pytest.mark.api]


def make_authed_client(user: User) -> APIClient:
    """Создаём отдельный APIClient и авторизуем токеном."""

    client = APIClient()
    token, _ = Token.objects.get_or_create(user=user)
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


def dt(y, m, d, hh=0, mm=0):
    """aware datetime UTC."""

    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


def test_e2e_monthly_report_creator_counts_tasks_for_executor_in_month():
    """Сквозной сценарий monthly report по реальному контракту:"""

    creator = User.objects.create_user(
        email="creator_monthly@example.com",
        password="pass12345",
        role=User.Role.CREATOR,
    )

    executor = User.objects.create_user(
        email="executor_monthly@example.com",
        password="pass12345",
        role=User.Role.EXECUTOR,
        company=creator.company,
    )

    creator_client = make_authed_client(creator)

    month_str = "2026-01"
    due_1 = dt(2026, 1, 10, 12, 0)
    due_2 = dt(2026, 1, 20, 12, 0)

    r1 = creator_client.post(
        "/api/tasks/",
        data={
            "title": "Monthly 1",
            "description": "",
            "priority": Task.Priority.MEDIUM,
            "status": Task.Status.NEW,
            "assignee": executor.id,
            "due_at": due_1.isoformat().replace("+00:00", "Z"),
        },
        format="json",
    )
    assert r1.status_code in (status.HTTP_201_CREATED, status.HTTP_200_OK), getattr(r1, "data", None)
    task1_id = r1.data["id"]

    r2 = creator_client.post(
        "/api/tasks/",
        data={
            "title": "Monthly 2",
            "description": "",
            "priority": Task.Priority.MEDIUM,
            "status": Task.Status.NEW,
            "assignee": executor.id,
            "due_at": due_2.isoformat().replace("+00:00", "Z"),
        },
        format="json",
    )
    assert r2.status_code in (status.HTTP_201_CREATED, status.HTTP_200_OK), getattr(r2, "data", None)
    task2_id = r2.data["id"]

    Task.objects.filter(id=task1_id).update(due_at=due_1)
    Task.objects.filter(id=task2_id).update(due_at=due_2)

    Task.objects.filter(id=task1_id).update(
        status=Task.Status.DONE,
        updated_at=dt(2026, 1, 10, 11, 0),  # вовремя
    )
    Task.objects.filter(id=task2_id).update(
        status=Task.Status.DONE,
        updated_at=dt(2026, 1, 21, 12, 0),  # поздно
    )

    assert Task.objects.filter(assignee=executor, due_at__year=2026, due_at__month=1).count() == 2

    resp = creator_client.get(f"/api/tasks/reports/monthly/?month={month_str}&user={executor.id}")
    assert resp.status_code == status.HTTP_200_OK, getattr(resp, "data", None)

    data = resp.data
    assert isinstance(data, dict), data

    assert data.get("month") == month_str, data
    assert int(data.get("user_id")) == executor.id, data

    assert int(data.get("total", 0)) >= 2, data
    assert int(data.get("done", 0)) >= 2, data
    assert int(data.get("done_on_time", 0)) >= 1, data
    assert int(data.get("done_late", 0)) >= 1, data
