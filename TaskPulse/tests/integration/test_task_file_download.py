import pytest
from rest_framework import status
from rest_framework.authtoken.models import Token
from django.core.files.uploadedfile import SimpleUploadedFile

from accounts.models import User
from tasks.models import Task
from integrations.models import TelegramProfile

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.integration,
    pytest.mark.api,
]


def auth(api_client, user: User):
    """Авторизация через DRF Token."""

    token, _ = Token.objects.get_or_create(user=user)
    api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return api_client


def ensure_executor_has_telegram(executor: User):
    """executor обязан иметь TelegramProfile,"""

    TelegramProfile.objects.get_or_create(
        user=executor,
        defaults={
            "telegram_user_id": 100_000 + executor.id,
            "chat_id": 200_000 + executor.id,
        },
    )


def make_users_and_task():
    creator = User.objects.create_user(
        email="creator_download@example.com",
        password="pass12345",
        role=User.Role.CREATOR,
    )

    executor = User.objects.create_user(
        email="executor_download@example.com",
        password="pass12345",
        role=User.Role.EXECUTOR,
        company=creator.company,
    )

    ensure_executor_has_telegram(executor)

    task = Task.objects.create(
        title="Download task",
        description="",
        creator=creator,
        assignee=executor,
        priority=Task.Priority.MEDIUM,
        status=Task.Status.NEW,
    )

    return creator, executor, task


def extract_file_ref(detail: dict) -> str | None:
    """Универсально извлекаем ссылку/путь на файл из detail serializer."""

    rf = detail.get("result_file")
    if isinstance(rf, str) and rf:
        return rf

    if isinstance(rf, dict):
        for key in ("url", "file", "path", "name"):
            val = rf.get(key)
            if isinstance(val, str) and val:
                return val

    attachments = detail.get("attachments")
    if isinstance(attachments, list) and attachments:
        first = attachments[0]
        if isinstance(first, dict):
            for key in ("url", "file", "path", "name"):
                val = first.get(key)
                if isinstance(val, str) and val:
                    return val

    return None


def test_uploaded_file_can_be_downloaded(api_client, settings, tmp_path):
    """Полный end-to-end сценарий:"""

    settings.DEBUG = True
    settings.MEDIA_ROOT = tmp_path
    settings.MEDIA_URL = "/media/"

    creator, executor, task = make_users_and_task()
    client = auth(api_client, creator)

    filename = "download_me.txt"
    file_content = b"DOWNLOAD-CONTENT-123"

    upload = SimpleUploadedFile(
        name=filename,
        content=file_content,
        content_type="text/plain",
    )

    upload_resp = client.patch(
        f"/api/tasks/{task.id}/",
        data={"result_file": upload},
        format="multipart",
    )

    assert upload_resp.status_code in (
        status.HTTP_200_OK,
        status.HTTP_202_ACCEPTED,
    ), upload_resp.data

    detail_resp = client.get(f"/api/tasks/{task.id}/")
    assert detail_resp.status_code == status.HTTP_200_OK, detail_resp.data

    file_ref = extract_file_ref(detail_resp.data)
    assert file_ref, (
        f"Файл не найден в detail serializer. "
        f"Keys: {list(detail_resp.data.keys())}. "
        f"Data: {detail_resp.data}"
    )

    if file_ref.startswith("/"):
        download_resp = client.get(file_ref)

        assert download_resp.status_code == status.HTTP_200_OK, (
            f"Не удалось скачать файл по пути {file_ref}"
        )

        # FileResponse -> streaming_content
        downloaded_bytes = b"".join(download_resp.streaming_content)

        assert file_content in downloaded_bytes, (
            "Содержимое скачанного файла не совпадает"
        )

    else:
        assert filename in file_ref
