import pytest
from rest_framework import status
from rest_framework.authtoken.models import Token

from accounts.models import User
from tasks.models import Task, TaskMessage

pytestmark = [pytest.mark.django_db, pytest.mark.integration, pytest.mark.api]


def auth(api_client, user: User):
    """Авторизуем APIClient под конкретного пользователя через DRF Token."""

    token, _ = Token.objects.get_or_create(user=user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return api_client


def test_conversation_messages_requires_auth(api_client):
    """Без авторизации endpoint должен быть недоступен."""

    resp = api_client.get("/api/tasks/conversation-messages/?task_id=1")
    assert resp.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


def test_conversation_messages_get_returns_messages(api_client):
    """
    GET должен вернуть список сообщений по task_id.
    По факту: resp.data — это list (ReturnList), не dict.
    """

    creator = User.objects.create_user(
        email="c_cm@example.com",
        password="pass12345",
        role=User.Role.CREATOR,
    )
    executor = User.objects.create_user(
        email="e_cm@example.com",
        password="pass12345",
        role=User.Role.EXECUTOR,
        company=creator.company,
    )

    task = Task.objects.create(
        title="Chat",
        description="",
        creator=creator,
        assignee=executor,
        priority=Task.Priority.MEDIUM,
        status=Task.Status.NEW,
    )

    TaskMessage.objects.create(task=task, sender=creator, text="hello")

    client = auth(api_client, creator)

    resp = client.get(f"/api/tasks/conversation-messages/?task_id={task.id}&user_id={executor.id}")
    assert resp.status_code == status.HTTP_200_OK

    items = list(resp.data)

    assert len(items) >= 1

    possible_text_keys = ("text", "message", "content", "body")

    extracted_texts = []
    for it in items:
        for key in possible_text_keys:
            if key in it and it[key] is not None:
                extracted_texts.append(str(it[key]))
                break

    assert extracted_texts, f"Не найдено текстовое поле. Keys in first item: {list(items[0].keys())}"

    assert any(t == "hello" for t in extracted_texts), f"Тексты в ответе: {extracted_texts}"


def test_conversation_messages_post_creates_message(api_client):
    """POST должен создать сообщение."""

    creator = User.objects.create_user(
        email="c_cmp@example.com",
        password="pass12345",
        role=User.Role.CREATOR,
    )
    executor = User.objects.create_user(
        email="e_cmp@example.com",
        password="pass12345",
        role=User.Role.EXECUTOR,
        company=creator.company,
    )

    task = Task.objects.create(
        title="Chat2",
        description="",
        creator=creator,
        assignee=executor,
        priority=Task.Priority.MEDIUM,
        status=Task.Status.NEW,
    )

    client = auth(api_client, creator)

    resp = client.post(
        "/api/tasks/conversation-messages/",
        data={
            "task_id": task.id,
            "user_id": executor.id,  # <-- обязательное поле по твоему API
            "text": "new msg",
        },
        format="json",
    )
    assert resp.status_code in (status.HTTP_201_CREATED, status.HTTP_200_OK), resp.data

    assert TaskMessage.objects.filter(task=task, sender=creator, text="new msg").exists()
