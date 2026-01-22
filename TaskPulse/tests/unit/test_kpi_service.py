import datetime as dt

import pytest
from django.utils import timezone

from accounts.models import User
from tasks.models import Task
from tasks.services.kpi import calc_user_month_kpi

pytestmark = [pytest.mark.django_db, pytest.mark.unit]


def _aware(y: int, m: int, d: int, hh: int = 0, mm: int = 0) -> dt.datetime:
    """Хелпер: создаёт timezone-aware datetime в текущей TZ Django."""

    return timezone.make_aware(dt.datetime(y, m, d, hh, mm))


def _create_task(
        *,
        creator: User,
        assignee: User,
        due_at: dt.datetime | None,
        status: str,
        priority: str,
        updated_at: dt.datetime | None = None,
) -> Task:
    """
    Хелпер: создаёт задачу и (если нужно) принудительно выставляет updated_at.
    """

    task = Task.objects.create(
        title="KPI task",
        description="",
        creator=creator,
        assignee=assignee,
        due_at=due_at,
        status=status,
        priority=priority,
    )

    if updated_at is not None:
        Task.objects.filter(pk=task.pk).update(updated_at=updated_at)
        task.refresh_from_db()

    return task


def test_kpi_counts_only_target_month_and_assignee(db):
    """функция считает только задачи нужного assignee"""

    creator = User.objects.create_user(email="creator@example.com", password="pass12345")
    assignee = User.objects.create_user(email="exec@example.com", password="pass12345")
    other_assignee = User.objects.create_user(email="other@example.com", password="pass12345")

    _create_task(
        creator=creator,
        assignee=assignee,
        due_at=_aware(2026, 1, 10),
        status=Task.Status.NEW,
        priority=Task.Priority.LOW,
    )

    _create_task(
        creator=creator,
        assignee=assignee,
        due_at=_aware(2026, 2, 10),
        status=Task.Status.NEW,
        priority=Task.Priority.MEDIUM,
    )

    _create_task(
        creator=creator,
        assignee=other_assignee,
        due_at=_aware(2026, 1, 12),
        status=Task.Status.NEW,
        priority=Task.Priority.HIGH,
    )

    data = calc_user_month_kpi(assignee, 2026, 1)

    assert data["user_id"] == assignee.id
    assert data["month"] == "2026-01"
    assert data["total"] == 1  # только первая задача
    assert data["done"] == 0
    assert data["done_on_time"] == 0
    assert data["done_late"] == 0


def test_kpi_done_on_time_vs_late(db):
    """Проверяем логику"""

    creator = User.objects.create_user(email="creator2@example.com", password="pass12345")
    assignee = User.objects.create_user(email="exec2@example.com", password="pass12345")

    due_1 = _aware(2026, 1, 10, 12, 0)
    due_2 = _aware(2026, 1, 11, 12, 0)

    _create_task(
        creator=creator,
        assignee=assignee,
        due_at=due_1,
        status=Task.Status.DONE,
        priority=Task.Priority.MEDIUM,
        updated_at=_aware(2026, 1, 10, 11, 0),
    )

    _create_task(
        creator=creator,
        assignee=assignee,
        due_at=due_2,
        status=Task.Status.DONE,
        priority=Task.Priority.MEDIUM,
        updated_at=_aware(2026, 1, 11, 13, 0),
    )

    data = calc_user_month_kpi(assignee, 2026, 1)

    assert data["total"] == 2
    assert data["done"] == 2
    assert data["done_on_time"] == 1
    assert data["done_late"] == 1


def test_kpi_by_priority_breakdown(db):
    """
        Проверяем, что by_priority:
    - содержит все priority из Task.Priority.choices (low/medium/high)
    - корректно считает total/done/done_on_time/done_late по каждому priority
    """

    creator = User.objects.create_user(email="creator3@example.com", password="pass12345")
    assignee = User.objects.create_user(email="exec3@example.com", password="pass12345")

    _create_task(
        creator=creator,
        assignee=assignee,
        due_at=_aware(2026, 1, 5, 10, 0),
        status=Task.Status.DONE,
        priority=Task.Priority.LOW,
        updated_at=_aware(2026, 1, 5, 9, 0),
    )
    _create_task(
        creator=creator,
        assignee=assignee,
        due_at=_aware(2026, 1, 6, 10, 0),
        status=Task.Status.NEW,
        priority=Task.Priority.LOW,
    )

    _create_task(
        creator=creator,
        assignee=assignee,
        due_at=_aware(2026, 1, 7, 10, 0),
        status=Task.Status.DONE,
        priority=Task.Priority.MEDIUM,
        updated_at=_aware(2026, 1, 7, 11, 0),
    )

    data = calc_user_month_kpi(assignee, 2026, 1)

    by_p = {item["priority"]: item for item in data["by_priority"]}

    assert set(by_p.keys()) == {Task.Priority.LOW, Task.Priority.MEDIUM, Task.Priority.HIGH}

    assert by_p[Task.Priority.LOW]["total"] == 2
    assert by_p[Task.Priority.LOW]["done"] == 1
    assert by_p[Task.Priority.LOW]["done_on_time"] == 1
    assert by_p[Task.Priority.LOW]["done_late"] == 0

    assert by_p[Task.Priority.MEDIUM]["total"] == 1
    assert by_p[Task.Priority.MEDIUM]["done"] == 1
    assert by_p[Task.Priority.MEDIUM]["done_on_time"] == 0
    assert by_p[Task.Priority.MEDIUM]["done_late"] == 1

    assert by_p[Task.Priority.HIGH]["total"] == 0
    assert by_p[Task.Priority.HIGH]["done"] == 0
    assert by_p[Task.Priority.HIGH]["done_on_time"] == 0
    assert by_p[Task.Priority.HIGH]["done_late"] == 0


def test_kpi_ignores_tasks_with_null_due_at(db):
    """
    Тест фиксирует текущее поведение (как контракт),
    чтобы случайно не “сломать” KPI изменением фильтра.
    """

    creator = User.objects.create_user(email="creator4@example.com", password="pass12345")
    assignee = User.objects.create_user(email="exec4@example.com", password="pass12345")

    _create_task(
        creator=creator,
        assignee=assignee,
        due_at=None,
        status=Task.Status.DONE,
        priority=Task.Priority.HIGH,
    )

    data = calc_user_month_kpi(assignee, 2026, 1)

    assert data["total"] == 0
    assert data["done"] == 0
