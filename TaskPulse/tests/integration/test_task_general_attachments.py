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
        defaults={"telegram_user_id": 100_000 + executor.id, "chat_id": 200_000 + executor.id},
    )


def make_users_and_task():
    creator = User.objects.create_user(
        email="creator_general_attach@example.com",
        password="pass12345",
        role=User.Role.CREATOR,
    )

    executor = User.objects.create_user(
        email="executor_general_attach@example.com",
        password="pass12345",
        role=User.Role.EXECUTOR,
        company=creator.company,
    )
    ensure_executor_has_telegram(executor)

    task = Task.objects.create(
        title="General attach task",
        description="",
        creator=creator,
        assignee=executor,
        priority=Task.Priority.MEDIUM,
        status=Task.Status.NEW,
    )

    return creator, executor, task


def extract_first_attachment_ref(detail: dict) -> str | None:
    """Достаём ссылку/путь на первый general attachment из detail response."""

    attachments = detail.get("attachments")
    if not isinstance(attachments, list) or not attachments:
        return None

    first = attachments[0]
    if isinstance(first, str) and first:
        return first

    if isinstance(first, dict):
        for key in ("url", "file", "path", "name"):
            val = first.get(key)
            if isinstance(val, str) and val:
                return val

        # Иногда вложенный формат: {"file": {"url": "..."}}
        for key in ("file", "document"):
            obj = first.get(key)
            if isinstance(obj, dict):
                for k2 in ("url", "path", "name"):
                    v2 = obj.get(k2)
                    if isinstance(v2, str) and v2:
                        return v2

    return None


def try_upload_general_attachment(api_client, task_id: int, upload: SimpleUploadedFile) -> tuple[bool, str, object]:
    """Пытаемся загрузить файл несколькими вероятными способами."""

    resp = api_client.post(
        f"/api/tasks/{task_id}/attachments/",
        data={"file": upload, "kind": "general"},
        format="multipart",
    )
    if resp.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED):
        return True, "POST /api/tasks/{id}/attachments/ (file, kind=general)", resp

    resp = api_client.post(
        "/api/tasks/attachments/",
        data={"task": task_id, "file": upload, "kind": "general"},
        format="multipart",
    )
    if resp.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED):
        return True, "POST /api/tasks/attachments/ (task, file, kind=general)", resp

    resp = api_client.post(
        f"/api/tasks/{task_id}/upload-attachment/",
        data={"file": upload, "kind": "general"},
        format="multipart",
    )
    if resp.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED):
        return True, "POST /api/tasks/{id}/upload-attachment/ (file, kind=general)", resp

    resp = api_client.patch(
        f"/api/tasks/{task_id}/",
        data={"file": upload},
        format="multipart",
    )
    if resp.status_code in (status.HTTP_200_OK, status.HTTP_202_ACCEPTED):
        return True, "PATCH /api/tasks/{id}/ (file)", resp

    resp = api_client.patch(
        f"/api/tasks/{task_id}/",
        data={"attachment": upload},
        format="multipart",
    )
    if resp.status_code in (status.HTTP_200_OK, status.HTTP_202_ACCEPTED):
        return True, "PATCH /api/tasks/{id}/ (attachment)", resp

    resp = api_client.patch(
        f"/api/tasks/{task_id}/",
        data={"attachments": upload},
        format="multipart",
    )
    if resp.status_code in (status.HTTP_200_OK, status.HTTP_202_ACCEPTED):
        return True, "PATCH /api/tasks/{id}/ (attachments=file)", resp

    return False, "no method worked", resp


def test_creator_can_upload_general_attachment_and_see_in_detail_and_download(api_client, settings, tmp_path):
    settings.DEBUG = True
    settings.MEDIA_ROOT = tmp_path
    settings.MEDIA_URL = "/media/"

    creator, executor, task = make_users_and_task()
    client = auth(api_client, creator)

    filename = "general.txt"
    content = b"GENERAL-ATTACHMENT-CONTENT"

    upload = SimpleUploadedFile(name=filename, content=content, content_type="text/plain")

    ok, used, resp = try_upload_general_attachment(client, task.id, upload)
    assert ok, (
        "Не удалось загрузить general attachment ни одним способом.\n"
        f"Последний ответ: status={getattr(resp, 'status_code', None)} data={getattr(resp, 'data', None)}"
    )

    detail = client.get(f"/api/tasks/{task.id}/")
    assert detail.status_code == status.HTTP_200_OK, detail.data

    file_ref = extract_first_attachment_ref(detail.data)
    assert file_ref, f"После загрузки attachments не появился. Used={used}. Detail keys={list(detail.data.keys())}. Data={detail.data}"

    if file_ref.startswith("/"):
        dl = client.get(file_ref)
        assert dl.status_code == status.HTTP_200_OK, f"Не скачался attachment по {file_ref}"

        downloaded = b"".join(dl.streaming_content)
        assert content in downloaded, "Содержимое скачанного attachment не совпадает"
    else:
        assert filename in file_ref


def test_other_company_cannot_see_task_detail_with_attachments(api_client):
    """Минимальный security test:"""

    creator, executor, task = make_users_and_task()

    outsider = User.objects.create_user(
        email="outsider_general_attach@example.com",
        password="pass12345",
        role=User.Role.CREATOR,
    )

    client = auth(api_client, outsider)
    resp = client.get(f"/api/tasks/{task.id}/")

    assert resp.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)
