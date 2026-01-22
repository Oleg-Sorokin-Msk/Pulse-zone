from datetime import datetime, timezone

import pytest

from accounts.models import User
from tasks.models import Task

pytestmark = [pytest.mark.django_db, pytest.mark.integration]


def dt(y, m, d, hh=0, mm=0):
    """Удобный генератор aware datetime."""

    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


def test_monthly_kpi_counts_done_on_time_and_late():
    """
    Сценарий:
- 1 done вовремя
- 1 done поздно
- ожидаем done=2, done_on_time=1, done_late=1
    """

    creator = User.objects.create_user(email="kpi_creator@example.com", password="pass12345", role=User.Role.CREATOR)
    executor = User.objects.create_user(
        email="kpi_executor@example.com",
        password="pass12345",
        role=User.Role.EXECUTOR,
        company=creator.company,
    )

    t1 = Task.objects.create(
        title="On time",
        description="",
        creator=creator,
        assignee=executor,
        priority=Task.Priority.MEDIUM,
        status=Task.Status.DONE,
        due_at=dt(2026, 1, 10, 12, 0),
    )
    t2 = Task.objects.create(
        title="Late",
        description="",
        creator=creator,
        assignee=executor,
        priority=Task.Priority.MEDIUM,
        status=Task.Status.DONE,
        due_at=dt(2026, 1, 20, 12, 0),
    )

    Task.objects.filter(id=t1.id).update(updated_at=dt(2026, 1, 10, 11, 0))  # вовремя
    Task.objects.filter(id=t2.id).update(updated_at=dt(2026, 1, 21, 12, 0))  # поздно

    from tasks.services.kpi import calc_user_month_kpi

    out = calc_user_month_kpi(user=executor, year=2026, month=1)

    assert out["total"] >= 2
    assert out["done"] >= 2
    assert out["done_on_time"] >= 1
    assert out["done_late"] >= 1
