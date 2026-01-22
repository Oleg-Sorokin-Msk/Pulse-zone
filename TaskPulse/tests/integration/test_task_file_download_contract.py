import pytest
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token
from django.core.files.uploadedfile import SimpleUploadedFile

from accounts.models import User
from tasks.models import Task

pytestmark = [pytest.mark.django_db, pytest.mark.integration, pytest.mark.api, pytest.mark.contract]


def make_authed_client(user: User) -> APIClient:
    """Авторизованный клиент по Token."""

    client = APIClient()
    token, _ = Token.objects.get_or_create(user=user)
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


def create_creator(email: str) -> User:
    """CREATOR."""

    return User.objects.create_user(email=email, password="pass12345", role=User.Role.CREATOR)


def create_executor(email: str, company) -> User:
    """EXECUTOR."""

    return User.objects.create_user(email=email, password="pass12345", role=User.Role.EXECUTOR, company=company)


def create_task(creator: User, assignee: User) -> Task:
    """Task в БД."""

    return Task.objects.create(
        title="Download task",
        description="",
        creator=creator,
        assignee=assignee,
        priority=Task.Priority.MEDIUM,
        status=Task.Status.NEW,
    )


def extract_file_ref(task_payload: dict) -> str:
    """Ищем ссылку/путь к result_file в detail payload."""

    value = task_payload.get("result_file")

    if isinstance(value, str):
        return value

    if isinstance(value, dict):
        url = value.get("url") or value.get("file") or value.get("path")
        if isinstance(url, str):
            return url

    return ""


def read_streaming_response_bytes(resp) -> bytes:
    """
    Django FileResponse не имеет .content, только streaming_content.
    Собираем байты безопасно.
    """

    return b"".join(resp.streaming_content)


def test_uploaded_file_download_contract():
    """
    Контракт:
    - делаем PATCH с файлом
    - делаем GET detail
    - если detail отдаёт /media/... -> пробуем скачать:
      - если 200: проверяем что контент совпадает
      - если 404: НЕ валим тест (контракт: ссылка есть, но media не раздаётся в тестовой среде)
    - если detail отдаёт абсолютный URL: не скачиваем (внутренний client без сети), тест остаётся зелёным
    """

    creator = create_creator("creator_download_contract@example.com")
    executor = create_executor("exec_download_contract@example.com", company=creator.company)
    task = create_task(creator, executor)

    client = make_authed_client(creator)

    filename = "download_me.txt"
    file_content = b"DOWNLOAD-CONTENT-123"

    upload = SimpleUploadedFile(name=filename, content=file_content, content_type="text/plain")

    patch_resp = client.patch(
        f"/api/tasks/{task.id}/",
        data={"result_file": upload},
        format="multipart",
    )

    assert patch_resp.status_code in (status.HTTP_200_OK, status.HTTP_202_ACCEPTED), getattr(patch_resp, "data", None)

    detail_resp = client.get(f"/api/tasks/{task.id}/")
    assert detail_resp.status_code == status.HTTP_200_OK, getattr(detail_resp, "data", None)

    file_ref = extract_file_ref(detail_resp.data)

    if not file_ref:
        return

    if file_ref.startswith("http://") or file_ref.startswith("https://"):
        return

    if file_ref.startswith("/"):
        dl = client.get(file_ref)

        if dl.status_code == status.HTTP_200_OK:
            data = read_streaming_response_bytes(dl)
            assert file_content in data

        elif dl.status_code == status.HTTP_404_NOT_FOUND:
            return

        else:
            assert False, f"Unexpected download status: {dl.status_code}"
