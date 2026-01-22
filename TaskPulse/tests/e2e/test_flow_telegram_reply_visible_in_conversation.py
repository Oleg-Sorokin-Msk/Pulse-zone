import pytest
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from accounts.models import User
from tasks.models import Task, TaskMessage
from integrations.models import TelegramLinkToken, TelegramProfile

pytestmark = [pytest.mark.django_db, pytest.mark.e2e, pytest.mark.api]


@pytest.fixture
def api_client():
    return APIClient()


def auth(api_client: APIClient, user: User) -> APIClient:
    token, _ = Token.objects.get_or_create(user=user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return api_client


def tg_update_start(update_id: int, user_id: int, chat_id: int, token: str) -> dict:
    """Формируем payload для webhook: /start <token>"""

    return {
        "update_id": update_id,
        "message": {
            "message_id": 10,
            "from": {"id": user_id, "is_bot": False, "first_name": "Test"},
            "chat": {"id": chat_id, "type": "private"},
            "date": 1700000000,
            "text": f"/start {token}",
        },
    }


def tg_update_reply_to_task(update_id: int, user_id: int, chat_id: int, task_id: int) -> dict:
    """Формируем payload "reply" на сообщение бота, где в original message есть ссылка /tasks/<id>."""

    return {
        "update_id": update_id,
        "message": {
            "message_id": 11,
            "from": {"id": user_id, "is_bot": False, "first_name": "Test"},
            "chat": {"id": chat_id, "type": "private"},
            "date": 1700000001,
            "text": "Мой ответ по задаче",
            "reply_to_message": {
                "message_id": 9,
                "from": {"id": 999999, "is_bot": True, "first_name": "Bot"},
                "chat": {"id": chat_id, "type": "private"},
                "date": 1700000000,
                "text": f"У вас новая задача: /tasks/{task_id}",
            },
        },
    }


def post_webhook(api_client: APIClient, secret: str, payload: dict):
    """
    Отправляем webhook в твой endpoint:
    /api/integrations/telegram/webhook/<secret>/
    """

    return api_client.post(
        f"/api/integrations/telegram/webhook/{secret}/",
        data=payload,
        format="json",
    )


def as_list(resp_data):
    """
    conversation-messages может быть ReturnList (list),
    иногда может быть {"results": [...]}.
    """

    if isinstance(resp_data, list):
        return resp_data
    if isinstance(resp_data, dict) and isinstance(resp_data.get("results"), list):
        return resp_data["results"]
    return []


def has_text(items, text: str) -> bool:
    for it in items:
        if isinstance(it, dict) and it.get("text") == text:
            return True
    return False


def test_e2e_telegram_reply_creates_task_message_and_visible_in_conversation(api_client, settings):
    """Сквозной тест без фронта."""

    settings.TELEGRAM_WEBHOOK_SECRET = "test-secret"

    creator = User.objects.create_user(
        email="creator_tg_flow@example.com",
        password="pass12345",
        role=User.Role.CREATOR,
    )

    executor = User.objects.create_user(
        email="executor_tg_flow@example.com",
        password="pass12345",
        role=User.Role.EXECUTOR,
        company=creator.company,
    )

    exec_client = auth(api_client, executor)
    link_resp = exec_client.post("/api/integrations/telegram/link-start/", data={}, format="json")
    assert link_resp.status_code == status.HTTP_200_OK, getattr(link_resp, "data", None)

    link = TelegramLinkToken.objects.filter(user=executor).order_by("-created_at").first()
    assert link is not None

    payload_start = tg_update_start(update_id=300, user_id=700001, chat_id=800001, token=str(link.token))
    wh1 = post_webhook(api_client, settings.TELEGRAM_WEBHOOK_SECRET, payload_start)
    assert wh1.status_code == status.HTTP_200_OK, getattr(wh1, "data", None)

    prof = TelegramProfile.objects.get(user=executor)
    assert prof.telegram_user_id == 700001
    assert prof.chat_id == 800001

    creator_client = auth(api_client, creator)
    create_task = creator_client.post(
        "/api/tasks/",
        data={
            "title": "TG created",
            "description": "",
            "priority": Task.Priority.MEDIUM,
            "status": Task.Status.NEW,
            "assignee": executor.id,
        },
        format="json",
    )
    assert create_task.status_code in (status.HTTP_201_CREATED, status.HTTP_200_OK), getattr(create_task, "data", None)

    task_id = create_task.data["id"]

    payload_reply = tg_update_reply_to_task(update_id=301, user_id=700001, chat_id=800001, task_id=task_id)
    wh2 = post_webhook(api_client, settings.TELEGRAM_WEBHOOK_SECRET, payload_reply)
    assert wh2.status_code == status.HTTP_200_OK, getattr(wh2, "data", None)

    assert TaskMessage.objects.filter(task_id=task_id).exists()

    expected_text = "Мой ответ по задаче"

    urls = [
        f"/api/tasks/conversation-messages/?task_id={task_id}",
        f"/api/tasks/conversation-messages/?task_id={task_id}&user_id={executor.id}",
        f"/api/tasks/conversation-messages/?task_id={task_id}&user_id={creator.id}",
    ]

    last_debug = []

    for url in urls:
        conv = creator_client.get(url)
        assert conv.status_code == status.HTTP_200_OK, getattr(conv, "data", None)

        items = as_list(conv.data)
        last_debug.append((url, len(items), items[:2]))

        if has_text(items, expected_text):
            return

    assert False, f"Conversation GET не вернул сообщение ни по одному контракту. Debug: {last_debug}"
