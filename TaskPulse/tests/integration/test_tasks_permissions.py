import pytest
from rest_framework import status
from rest_framework.authtoken.models import Token

from accounts.models import User
from tasks.models import Task
from integrations.models import TelegramProfile

pytestmark = [pytest.mark.django_db, pytest.mark.integration, pytest.mark.api]


def auth(api_client, user: User):
    """Авторизация APIClient через TokenAuthentication."""

    token, _ = Token.objects.get_or_create(user=user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return api_client


def ensure_executor_has_telegram(executor: User):
    """assignee должен быть привязан к Telegram."""

    TelegramProfile.objects.get_or_create(
        user=executor,
        defaults={"telegram_user_id": 111000 + executor.id, "chat_id": 222000 + executor.id},
    )


def create_creator(email: str) -> User:
    """Создаём CREATOR пользователя."""

    return User.objects.create_user(email=email, password="pass12345", role=User.Role.CREATOR)


def create_executor(email: str, company) -> User:
    """Создаём EXECUTOR пользователя в нужной компании и привязываем Telegram."""

    u = User.objects.create_user(email=email, password="pass12345", role=User.Role.EXECUTOR, company=company)
    ensure_executor_has_telegram(u)
    return u


def test_tasks_list_requires_auth(api_client):
    """Без авторизации доступ к /api/tasks/ должен быть запрещён."""

    resp = api_client.get("/api/tasks/")
    assert resp.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


def test_creator_can_create_task_in_own_company(api_client):
    """CREATOR должен уметь создавать задачу (assignee в своей company)."""

    creator = create_creator("creator_perm@example.com")
    executor = create_executor("exec_perm@example.com", company=creator.company)

    client = auth(api_client, creator)

    resp = client.post(
        "/api/tasks/",
        data={
            "title": "Perm task",
            "description": "",
            "priority": Task.Priority.MEDIUM,
            "status": Task.Status.NEW,
            "assignee": executor.id,
        },
        format="json",
    )

    assert resp.status_code in (status.HTTP_201_CREATED, status.HTTP_200_OK), resp.data
    assert resp.data.get("title") == "Perm task"


def test_creator_can_retrieve_own_task(api_client):
    """CREATOR должен читать свою задачу."""

    creator = create_creator("creator_read@example.com")
    executor = create_executor("exec_read@example.com", company=creator.company)

    task = Task.objects.create(
        title="Read me",
        description="",
        creator=creator,
        assignee=executor,
        priority=Task.Priority.MEDIUM,
        status=Task.Status.NEW,
    )

    client = auth(api_client, creator)

    resp = client.get(f"/api/tasks/{task.id}/")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data.get("id") == task.id


def test_creator_can_update_own_task(api_client):
    """CREATOR должен уметь обновлять свою задачу."""

    creator = create_creator("creator_upd@example.com")
    executor = create_executor("exec_upd@example.com", company=creator.company)

    task = Task.objects.create(
        title="Old",
        description="",
        creator=creator,
        assignee=executor,
        priority=Task.Priority.MEDIUM,
        status=Task.Status.NEW,
    )

    client = auth(api_client, creator)

    resp = client.patch(f"/api/tasks/{task.id}/", data={"title": "New"}, format="json")
    assert resp.status_code in (status.HTTP_200_OK, status.HTTP_202_ACCEPTED), resp.data

    task.refresh_from_db()
    assert task.title == "New"


def test_executor_can_create_task_for_self(api_client):
    """API EXECUTOR может создавать задачу (201)."""

    creator = create_creator("creator_for_exec_create_ok@example.com")
    executor = create_executor("exec_create_ok@example.com", company=creator.company)

    client = auth(api_client, executor)

    resp = client.post(
        "/api/tasks/",
        data={
            "title": "Executor created",
            "description": "",
            "priority": Task.Priority.MEDIUM,
            "status": Task.Status.NEW,
            "assignee": executor.id,
        },
        format="json",
    )

    assert resp.status_code in (status.HTTP_201_CREATED, status.HTTP_200_OK), resp.data
    assert resp.data.get("assignee") in (executor.id, str(executor.id), {"id": executor.id})


def test_executor_can_retrieve_assigned_task(api_client):
    """EXECUTOR должен читать задачу, где он assignee."""

    creator = create_creator("creator_for_exec_read@example.com")
    executor = create_executor("exec_read_task@example.com", company=creator.company)

    task = Task.objects.create(
        title="Assigned",
        description="",
        creator=creator,
        assignee=executor,
        priority=Task.Priority.MEDIUM,
        status=Task.Status.NEW,
    )

    client = auth(api_client, executor)

    resp = client.get(f"/api/tasks/{task.id}/")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data.get("id") == task.id


def test_other_company_creator_cannot_read_foreign_task(api_client):
    """CREATOR из другой company не должен читать задачу чужой компании."""

    creator_a = create_creator("creator_a@example.com")
    executor_a = create_executor("exec_a@example.com", company=creator_a.company)

    task = Task.objects.create(
        title="Company A task",
        description="",
        creator=creator_a,
        assignee=executor_a,
        priority=Task.Priority.MEDIUM,
        status=Task.Status.NEW,
    )

    creator_b = create_creator("creator_b@example.com")

    client = auth(api_client, creator_b)

    resp = client.get(f"/api/tasks/{task.id}/")

    assert resp.status_code in (status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN)


def test_other_company_creator_cannot_update_foreign_task(api_client):
    """CREATOR из другой company не должен обновлять чужую задачу."""

    creator_a = create_creator("creator_a2@example.com")
    executor_a = create_executor("exec_a2@example.com", company=creator_a.company)

    task = Task.objects.create(
        title="Company A task",
        description="",
        creator=creator_a,
        assignee=executor_a,
        priority=Task.Priority.MEDIUM,
        status=Task.Status.NEW,
    )

    creator_b = create_creator("creator_b2@example.com")
    client = auth(api_client, creator_b)

    resp = client.patch(f"/api/tasks/{task.id}/", data={"title": "Nope"}, format="json")
    assert resp.status_code in (status.HTTP_404_NOT_FOUND, status.HTTP_403_FORBIDDEN)
