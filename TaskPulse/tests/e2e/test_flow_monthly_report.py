import datetime as dt

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token

from accounts.models import User
from tasks.models import Task
from integrations.models import TelegramProfile

pytestmark = [pytest.mark.django_db, pytest.mark.e2e, pytest.mark.api]


def _aware(y: int, m: int, d: int, hh: int = 0, mm: int = 0) -> dt.datetime:
    """Создаём timezone-aware datetime для due_at/updated_at."""

    return timezone.make_aware(dt.datetime(y, m, d, hh, mm))


def test_e2e_creator_creates_tasks_and_gets_monthly_report(api_client):
    """
    Сквозной сценарий:
    1) Создаём CREATOR и авторизуемся через DRF Token
    2) Создаём EXECUTOR + TelegramProfile (чтобы проходила валидация assignee)
    3) CREATOR создаёт 2 задачи в 2026-01 на EXECUTOR через /api/tasks/
    4) Обновляем задачи: DONE вовремя/поздно (через ORM update updated_at)
    5) CREATOR получает monthly report и видит корректные totals
    """

    # 1) Создаём CREATOR в БД.
    creator = User.objects.create_user(
        email="creator_e2e@example.com",
        password="pass12345",
        role=User.Role.CREATOR,
    )

    # 1.1) Создаём DRF Token и подставляем в Authorization header.
    token, _ = Token.objects.get_or_create(user=creator)
    api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    # 2) Создаём EXECUTOR в той же company, чтобы совпадали ограничения по компании.
    executor = User.objects.create_user(
        email="exec_e2e@example.com",
        password="pass12345",
        role=User.Role.EXECUTOR,
        company=creator.company,
    )

    # 2.1) Создаём TelegramProfile (твой валидатор assignee проверяет наличие telegram_user_id).
    TelegramProfile.objects.create(
        user=executor,
        telegram_user_id=123456789,
        chat_id=987654321,
    )

    # 3) Создаём 2 задачи через API.
    due_1 = _aware(2026, 1, 10, 12, 0)
    due_2 = _aware(2026, 1, 11, 12, 0)

    resp1 = api_client.post(
        "/api/tasks/",
        data={
            "title": "E2E task 1",
            "description": "first",
            "priority": Task.Priority.MEDIUM,
            "status": Task.Status.NEW,
            "due_at": due_1.isoformat(),
            "assignee": executor.id,
        },
        format="json",
    )
    assert resp1.status_code in (status.HTTP_201_CREATED, status.HTTP_200_OK), resp1.data
    task1_id = resp1.data["id"]

    resp2 = api_client.post(
        "/api/tasks/",
        data={
            "title": "E2E task 2",
            "description": "second",
            "priority": Task.Priority.MEDIUM,
            "status": Task.Status.NEW,
            "due_at": due_2.isoformat(),
            "assignee": executor.id,
        },
        format="json",
    )
    assert resp2.status_code in (status.HTTP_201_CREATED, status.HTTP_200_OK), resp2.data
    task2_id = resp2.data["id"]

    # 4) Завершаем задачи и фиксируем updated_at.
    Task.objects.filter(pk=task1_id).update(status=Task.Status.DONE, updated_at=_aware(2026, 1, 10, 11, 0))  # вовремя
    Task.objects.filter(pk=task2_id).update(status=Task.Status.DONE, updated_at=_aware(2026, 1, 11, 13, 0))  # поздно

    # 5) Получаем отчёт по исполнителю.
    report = api_client.get(f"/api/tasks/reports/monthly/?month=2026-01&user={executor.id}")
    assert report.status_code == status.HTTP_200_OK, report.data

    assert report.data["user_id"] == executor.id
    assert report.data["month"] == "2026-01"
    assert report.data["total"] == 2
    assert report.data["done"] == 2
    assert report.data["done_on_time"] == 1
    assert report.data["done_late"] == 1
