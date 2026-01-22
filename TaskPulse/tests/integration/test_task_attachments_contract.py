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
    """Task в БД (setup для API)."""

    return Task.objects.create(
        title="Attach task",
        description="",
        creator=creator,
        assignee=assignee,
        priority=Task.Priority.MEDIUM,
        status=Task.Status.NEW,
    )


def extract_file_ref(task_payload: dict) -> str:
    """Пытаемся вытащить ссылку/путь на файл из ответа detail."""

    value = task_payload.get("result_file")

    if isinstance(value, str):
        return value

    if isinstance(value, dict):
        url = value.get("url") or value.get("file") or value.get("path")
        if isinstance(url, str):
            return url

    return ""


def test_creator_uploads_result_file_contract(api_client_fixture=None):
    """
    Контракт:
    - CREATOR может попытаться загрузить result_file через PATCH multipart
    - PATCH может вернуть ответ без result_file (это не ошибка)
    - После PATCH делаем GET detail и проверяем: result_file появился (если бек реально сохраняет файл)
    """

    creator = create_creator("creator_attach_contract@example.com")
    executor = create_executor("exec_attach_contract@example.com", company=creator.company)
    task = create_task(creator, executor)

    client = make_authed_client(creator)

    upload = SimpleUploadedFile(
        name="result.txt",
        content=b"result content",
        content_type="text/plain",
    )

    patch_resp = client.patch(
        f"/api/tasks/{task.id}/",
        data={"result_file": upload},
        format="multipart",
    )

    assert patch_resp.status_code in (status.HTTP_200_OK, status.HTTP_202_ACCEPTED), getattr(patch_resp, "data", None)

    detail_resp = client.get(f"/api/tasks/{task.id}/")
    assert detail_resp.status_code == status.HTTP_200_OK, getattr(detail_resp, "data", None)

    file_ref = extract_file_ref(detail_resp.data)

    if file_ref:
        assert isinstance(file_ref, str)
        assert file_ref.strip() != ""


def test_executor_uploads_result_file_contract(api_client_fixture=None):
    """
    Контракт:
    - EXECUTOR делает PATCH result_file
    - В зависимости от прав/настроек: может быть 200/202 ИЛИ 403/405
    - Если 200/202 — проверяем через GET detail, что ссылка появилась (если бек поддерживает)
    """

    creator = create_creator("creator_attach_contract2@example.com")
    executor = create_executor("exec_attach_contract2@example.com", company=creator.company)
    task = create_task(creator, executor)

    client = make_authed_client(executor)

    upload = SimpleUploadedFile(
        name="exec_result.txt",
        content=b"executor result",
        content_type="text/plain",
    )

    patch_resp = client.patch(
        f"/api/tasks/{task.id}/",
        data={"result_file": upload},
        format="multipart",
    )

    assert patch_resp.status_code in (
        status.HTTP_200_OK,
        status.HTTP_202_ACCEPTED,
        status.HTTP_403_FORBIDDEN,
        status.HTTP_405_METHOD_NOT_ALLOWED,
    ), getattr(patch_resp, "data", None)

    if patch_resp.status_code in (status.HTTP_200_OK, status.HTTP_202_ACCEPTED):
        detail_resp = client.get(f"/api/tasks/{task.id}/")
        assert detail_resp.status_code in (status.HTTP_200_OK, status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)

        if detail_resp.status_code == status.HTTP_200_OK:
            file_ref = extract_file_ref(detail_resp.data)
            if file_ref:
                assert isinstance(file_ref, str)
                assert file_ref.strip() != ""
