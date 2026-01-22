import pytest
from rest_framework import status
from rest_framework.authtoken.models import Token
from django.core.files.uploadedfile import SimpleUploadedFile

from accounts.models import User
from tasks.models import Task
from integrations.models import TelegramProfile

pytestmark = [pytest.mark.django_db, pytest.mark.integration, pytest.mark.api]


def auth(api_client, user: User):
    token, _ = Token.objects.get_or_create(user=user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return api_client


def ensure_executor_has_telegram(executor: User):
    TelegramProfile.objects.get_or_create(
        user=executor,
        defaults={"telegram_user_id": 111000 + executor.id, "chat_id": 222000 + executor.id},
    )


def make_users_and_task():
    creator = User.objects.create_user(email="creator_attach_get@example.com", password="pass12345", role=User.Role.CREATOR)
    executor = User.objects.create_user(
        email="exec_attach_get@example.com",
        password="pass12345",
        role=User.Role.EXECUTOR,
        company=creator.company,
    )
    ensure_executor_has_telegram(executor)

    task = Task.objects.create(
        title="Attach visibility",
        description="",
        creator=creator,
        assignee=executor,
        priority=Task.Priority.MEDIUM,
        status=Task.Status.NEW,
    )
    return creator, executor, task


def _extract_any_file_reference(task_detail: dict) -> str | None:
    """Универсально пытаемся извлечь ссылку/имя файла из detail response."""

    rf = task_detail.get("result_file")
    if isinstance(rf, str) and rf:
        return rf
    if isinstance(rf, dict):
        for key in ("url", "file", "path", "name"):
            val = rf.get(key)
            if isinstance(val, str) and val:
                return val

    att = task_detail.get("attachments")
    if isinstance(att, list) and att:
        first = att[0]
        if isinstance(first, dict):
            for key in ("file", "url", "path", "name"):
                val = first.get(key)
                if isinstance(val, str) and val:
                    return val

    return None


def test_upload_then_get_task_detail_shows_file(api_client):
    """
    Главный тест:
    1) CREATOR upload result_file
    2) GET detail задачи показывает ссылку/имя файла (в result_file или attachments)
    """

    creator, executor, task = make_users_and_task()
    client = auth(api_client, creator)

    upload = SimpleUploadedFile(name="result_visible.txt", content=b"hello file", content_type="text/plain")

    up = client.patch(
        f"/api/tasks/{task.id}/",
        data={"result_file": upload},
        format="multipart",
    )
    assert up.status_code in (status.HTTP_200_OK, status.HTTP_202_ACCEPTED), up.data

    detail = client.get(f"/api/tasks/{task.id}/")
    assert detail.status_code == status.HTTP_200_OK, detail.data

    file_ref = _extract_any_file_reference(detail.data)
    assert file_ref, f"Файл не отражён в detail response. Keys: {list(detail.data.keys())}. Data: {detail.data}"


def test_other_company_cannot_see_file_in_task_detail(api_client):
    """Пользователь из другой company не должен видеть задачу вообще (и значит не увидит файл)."""

    creator, executor, task = make_users_and_task()

    outsider = User.objects.create_user(email="outsider_get@example.com", password="pass12345", role=User.Role.CREATOR)
    client = auth(api_client, outsider)

    detail = client.get(f"/api/tasks/{task.id}/")
    assert detail.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)
