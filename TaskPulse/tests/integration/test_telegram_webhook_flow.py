import json
import pytest
from rest_framework import status
from django.conf import settings

from accounts.models import User
from tasks.models import Task, TaskMessage
from integrations.models import TelegramProfile, TelegramLinkToken

from tests.helpers.telegram_payloads import tg_update_start, tg_update_reply_to_task

pytestmark = [pytest.mark.django_db, pytest.mark.integration, pytest.mark.api]


def post_webhook(api_client, secret: str, payload: dict):
    """Утилита: POST webhook с JSON."""

    return api_client.post(
        f"/api/integrations/telegram/webhook/{secret}/",
        data=json.dumps(payload),
        content_type="application/json",
    )


def test_webhook_rejects_wrong_secret(api_client, settings):
    """Неверный secret должен блокировать webhook."""

    settings.TELEGRAM_WEBHOOK_SECRET = "correct"

    resp = post_webhook(api_client, "wrong", {})
    assert resp.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)


def test_webhook_start_links_profile_and_marks_token_used(api_client, settings):
    """
    /start <uuid>:
    - создаёт/обновляет TelegramProfile(user)
    - устанавливает telegram_user_id, chat_id
    - помечает TelegramLinkToken.is_used=True
    """

    settings.TELEGRAM_WEBHOOK_SECRET = "test-secret"

    user = User.objects.create_user(email="tg_user@example.com", password="pass12345", role=User.Role.EXECUTOR)

    link = TelegramLinkToken.objects.create(user=user)

    payload = tg_update_start(
        update_id=100,
        user_id=999001,
        chat_id=888001,
        token=str(link.token),
    )

    resp = post_webhook(api_client, settings.TELEGRAM_WEBHOOK_SECRET, payload)
    assert resp.status_code == status.HTTP_200_OK

    profile = TelegramProfile.objects.get(user=user)
    assert profile.telegram_user_id == 999001
    assert profile.chat_id == 888001

    link.refresh_from_db()
    assert link.is_used is True


def test_webhook_reply_creates_task_message(api_client, settings):
    """
    Reply-сообщение:
    - в reply_to_message.text есть "/tasks/<id>"
    - сообщение пользователя становится TaskMessage(task=<id>)
    """

    settings.TELEGRAM_WEBHOOK_SECRET = "test-secret"

    creator = User.objects.create_user(email="creator_tg@example.com", password="pass12345", role=User.Role.CREATOR)
    executor = User.objects.create_user(
        email="exec_tg@example.com",
        password="pass12345",
        role=User.Role.EXECUTOR,
        company=creator.company,
    )

    TelegramProfile.objects.create(user=executor, telegram_user_id=999002, chat_id=888002)

    task = Task.objects.create(
        title="From TG",
        description="",
        creator=creator,
        assignee=executor,
        priority=Task.Priority.MEDIUM,
        status=Task.Status.NEW,
    )

    payload = tg_update_reply_to_task(
        update_id=101,
        user_id=999002,
        chat_id=888002,
        task_id=task.id,
    )

    resp = post_webhook(api_client, settings.TELEGRAM_WEBHOOK_SECRET, payload)
    assert resp.status_code == status.HTTP_200_OK

    assert TaskMessage.objects.filter(task=task).exists()
    msg = TaskMessage.objects.filter(task=task).order_by("-id").first()
    assert msg is not None
    assert "Мой ответ из Telegram" in (msg.text or "")
