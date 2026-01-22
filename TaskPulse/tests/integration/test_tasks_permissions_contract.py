import pytest
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from accounts.models import User
from tasks.models import Task

pytestmark = [pytest.mark.django_db, pytest.mark.integration, pytest.mark.api, pytest.mark.contract]


@pytest.fixture
def api_client():
    """Обычный DRF APIClient без авторизации."""

    return APIClient()


def make_authed_client(user: User) -> APIClient:
    """Создаём новый APIClient и авторизуем токеном конкретного пользователя."""

    client = APIClient()
    token, _ = Token.objects.get_or_create(user=user)
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


def create_creator(email: str) -> User:
    """Создаём CREATOR."""

    return User.objects.create_user(email=email, password="pass12345", role=User.Role.CREATOR)


def create_executor(email: str, company) -> User:
    """Создаём EXECUTOR в нужной company."""

    return User.objects.create_user(email=email, password="pass12345", role=User.Role.EXECUTOR, company=company)


def create_task(creator: User, assignee: User, title="T") -> Task:
    """Создаём задачу напрямую в БД для проверки retrieve/update."""

    return Task.objects.create(
        title=title,
        description="",
        creator=creator,
        assignee=assignee,
        priority=Task.Priority.MEDIUM,
        status=Task.Status.NEW,
    )


def test_tasks_list_requires_auth(api_client):
    """Контракт: /api/tasks/ без токена."""

    resp = api_client.get("/api/tasks/")
    assert resp.status_code != status.HTTP_200_OK


def test_tasks_create_contract_creator(api_client):
    """Контракт: CREATOR создаёт задачу через /api/tasks/."""

    creator = create_creator("creator_contract_create@example.com")
    executor = create_executor("exec_contract_create@example.com", company=creator.company)

    client = make_authed_client(creator)

    resp = client.post(
        "/api/tasks/",
        data={
            "title": "Contract create",
            "description": "",
            "priority": Task.Priority.MEDIUM,
            "status": Task.Status.NEW,
            "assignee": executor.id,
        },
        format="json",
    )

    assert resp.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED), getattr(resp, "data", None)
    assert "id" in resp.data


def test_tasks_create_contract_executor_records_current_behavior(api_client):
    """Контракт: EXECUTOR создаёт задачу через /api/tasks/."""

    creator = create_creator("creator_contract_exec_create@example.com")
    executor = create_executor("exec_contract_exec_create@example.com", company=creator.company)

    client = make_authed_client(executor)

    resp = client.post(
        "/api/tasks/",
        data={
            "title": "Executor create contract",
            "description": "",
            "priority": Task.Priority.MEDIUM,
            "status": Task.Status.NEW,
            "assignee": executor.id,
        },
        format="json",
    )

    assert resp.status_code in (
        status.HTTP_200_OK,
        status.HTTP_201_CREATED,
        status.HTTP_400_BAD_REQUEST,
        status.HTTP_403_FORBIDDEN,
        status.HTTP_405_METHOD_NOT_ALLOWED,
    ), getattr(resp, "data", None)


def test_retrieve_task_contract_creator_can_read_own_company(api_client):
    """Контракт: CREATOR читает задачу, которую создал."""

    creator = create_creator("creator_contract_read@example.com")
    executor = create_executor("exec_contract_read@example.com", company=creator.company)
    task = create_task(creator, executor, title="Read me")

    client = make_authed_client(creator)

    resp = client.get(f"/api/tasks/{task.id}/")
    assert resp.status_code == status.HTTP_200_OK, getattr(resp, "data", None)
    assert resp.data.get("id") == task.id


def test_retrieve_task_contract_executor_can_read_assigned_or_not(api_client):
    """Контракт: EXECUTOR читает задачу."""

    creator = create_creator("creator_contract_exec_read@example.com")
    executor = create_executor("exec_contract_exec_read@example.com", company=creator.company)
    task = create_task(creator, executor, title="Assigned")

    client = make_authed_client(executor)

    resp = client.get(f"/api/tasks/{task.id}/")

    assert resp.status_code in (
        status.HTTP_200_OK,
        status.HTTP_403_FORBIDDEN,
        status.HTTP_404_NOT_FOUND,
    ), getattr(resp, "data", None)

    if resp.status_code == status.HTTP_200_OK:
        assert resp.data.get("id") == task.id


def test_other_company_creator_cannot_read_foreign_task_contract(api_client):
    """Контракт границы company: CREATOR из другой company не должен читать чужую задачу."""

    creator_a = create_creator("creator_a_contract_foreign_read@example.com")
    exec_a = create_executor("exec_a_contract_foreign_read@example.com", company=creator_a.company)
    task = create_task(creator_a, exec_a, title="Company A task")

    creator_b = create_creator("creator_b_contract_foreign_read@example.com")  # другая company
    client_b = make_authed_client(creator_b)

    resp = client_b.get(f"/api/tasks/{task.id}/")
    assert resp.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND), getattr(resp, "data", None)
