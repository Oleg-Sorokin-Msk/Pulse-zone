import json
import pytest
from rest_framework import status
from rest_framework.authtoken.models import Token

from accounts.models import User
from tasks.models import Task
from integrations.models import TelegramProfile, TelegramLinkToken

from tests.helpers.telegram_payloads import tg_update_start, tg_update_reply_to_task

pytestmark = [pytest.mark.django_db, pytest.mark.e2e, pytest.mark.api]


def auth(api_client, user: User):
    token, _ = Token.objects.get_or_create(user=user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return api_client


def post_webhook(api_client, secret: str, payload: dict):
    return api_client.post(
        f"/api/integrations/telegram/webhook/{secret}/",
        data=json.dumps(payload),
        content_type="application/json",
    )


def test_e2e_telegram_reply_creates_task_message_and_visible_in_conversation(api_client, settings):
    settings.TELEGRAM_WEBHOOK_SECRET = "test-secret"

    # 1) CREATOR
    creator = User.objects.create_user(email="c_tg_e2e@example.com", password="pass12345", role=User.Role.CREATOR)
    auth(api_client, creator)

    # 2) EXECUTOR
    executor = User.objects.create_user(
        email="e_tg_e2e@example.com",
        password="pass12345",
        role=User.Role.EXECUTOR,
        company=creator.company,
    )

    # 3) От имени EXECUTOR запускаем link-start (эндпоинт требует auth).
    exec_client = auth(api_client, executor)
    link_resp = exec_client.post("/api/integrations/telegram/link-start/", data={}, format="json")
    assert link_resp.status_code == status.HTTP_200_OK, link_resp.data

    # Проверяем, что реально создался token в БД.
    link = TelegramLinkToken.objects.filter(user=executor).order_by("-created_at").first()
    assert link is not None

    # 4) webhook /start привязывает telegram_user_id/chat_id
    payload_start = tg_update_start(update_id=300, user_id=700001, chat_id=800001, token=str(link.token))
    wh_resp = post_webhook(api_client, settings.TELEGRAM_WEBHOOK_SECRET, payload_start)
    assert wh_resp.status_code == status.HTTP_200_OK

    prof = TelegramProfile.objects.get(user=executor)
    assert prof.telegram_user_id == 700001
    assert prof.chat_id == 800001

    # 5) CREATOR создаёт задачу
    auth(api_client, creator)
    create_task = api_client.post(
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
    assert create_task.status_code in (status.HTTP_201_CREATED, status.HTTP_200_OK), create_task.data
    task_id = create_task.data["id"]

    # 6) webhook reply создаёт TaskMessage
    payload_reply = tg_update_reply_to_task(update_id=301, user_id=700001, chat_id=800001, task_id=task_id)
    wh2 = post_webhook(api_client, settings.TELEGRAM_WEBHOOK_SECRET, payload_reply)
    assert wh2.status_code == status.HTTP_200_OK

    # 7) conversation-messages должен показать сообщение
    auth(api_client, creator)

    # ВАЖНО: по контракту endpoint нужен user_id, иначе фильтр может вернуть пусто.
    conv = api_client.get(f"/api/tasks/conversation-messages/?task_id={task_id}&user_id={executor.id}")
    assert conv.status_code == status.HTTP_200_OK, getattr(conv, "data", None)

    # По факту conv.data — это список (ReturnList), без пагинации.
    items = list(conv.data)

    assert any("Мой ответ из Telegram" in (it.get("text") or it.get("message") or it.get("content") or "") for it in
               items), items
