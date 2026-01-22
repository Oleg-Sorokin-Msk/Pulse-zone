import pytest
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from accounts.models import User
from tasks.models import Task, TaskMessage

pytestmark = [pytest.mark.django_db, pytest.mark.integration, pytest.mark.api]


@pytest.fixture
def api_client():
    """Даём APIClient как fixture прямо в этом файле"""

    return APIClient()


def auth(api_client: APIClient, user: User) -> APIClient:
    """Авторизация через DRF Token."""

    token, _ = Token.objects.get_or_create(user=user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return api_client


def make_creator_executor_and_task():
    """Создаём creator/executor в одной company и одну задачу."""

    creator = User.objects.create_user(
        email="cm_creator@example.com",
        password="pass12345",
        role=User.Role.CREATOR,
    )

    executor = User.objects.create_user(
        email="cm_executor@example.com",
        password="pass12345",
        role=User.Role.EXECUTOR,
        company=creator.company,
    )

    task = Task.objects.create(
        title="CM Task",
        description="",
        creator=creator,
        assignee=executor,
        priority=Task.Priority.MEDIUM,
        status=Task.Status.NEW,
    )

    return creator, executor, task


def as_list(resp_data):
    """Приводим resp.data к list, потому что в твоём API это ReturnList."""

    if isinstance(resp_data, list):
        return resp_data

    if isinstance(resp_data, dict) and isinstance(resp_data.get("results"), list):
        return resp_data["results"]

    return []


def find_message_with_text(items, text: str) -> bool:
    """Ищем сообщение с нужным текстом в items (list[dict])."""

    for it in items:
        if isinstance(it, dict) and it.get("text") == text:
            return True
    return False


def test_conversation_messages_get_returns_messages_contract(api_client):
    """Контракт GET:"""

    creator, executor, task = make_creator_executor_and_task()

    TaskMessage.objects.create(task=task, sender=creator, text="hello-from-creator")

    assert TaskMessage.objects.filter(task=task).count() == 1

    client = auth(api_client, creator)

    candidates = [
        (f"/api/tasks/conversation-messages/?task_id={task.id}", "task_id only"),
        (f"/api/tasks/conversation-messages/?task_id={task.id}&user_id={executor.id}", "task_id + user_id=executor"),
        (f"/api/tasks/conversation-messages/?task_id={task.id}&user_id={creator.id}", "task_id + user_id=creator"),
    ]

    last_debug = []

    for url, label in candidates:
        resp = client.get(url)

        assert resp.status_code == status.HTTP_200_OK, getattr(resp, "data", None)

        items = as_list(resp.data)
        last_debug.append((label, len(items), items[:2]))

        if find_message_with_text(items, "hello-from-creator"):
            # успех: нашли сообщение
            return

    assert False, f"GET не вернул сообщение ни при одном контракте. Debug: {last_debug}"


def test_conversation_messages_post_creates_message_contract(api_client):
    """Контракт POST"""

    creator, executor, task = make_creator_executor_and_task()

    client = auth(api_client, creator)

    bad = client.post(
        "/api/tasks/conversation-messages/",
        data={"task_id": task.id, "text": "msg-without-user-id"},
        format="json",
    )
    assert bad.status_code == status.HTTP_400_BAD_REQUEST
    if isinstance(getattr(bad, "data", None), dict) and "detail" in bad.data:
        assert "user_id" in str(bad.data["detail"]).lower()

    good = client.post(
        "/api/tasks/conversation-messages/",
        data={
            "task_id": task.id,
            "user_id": executor.id,  # <-- ключевой параметр контракта
            "text": "msg-from-creator",
        },
        format="json",
    )

    assert good.status_code in (status.HTTP_201_CREATED, status.HTTP_200_OK), getattr(good, "data", None)

    assert TaskMessage.objects.filter(task=task, text="msg-from-creator").exists()
