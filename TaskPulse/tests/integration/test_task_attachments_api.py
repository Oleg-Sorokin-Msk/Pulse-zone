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
    creator = User.objects.create_user(email="creator_attach@example.com", password="pass12345", role=User.Role.CREATOR)
    executor = User.objects.create_user(
        email="exec_attach@example.com",
        password="pass12345",
        role=User.Role.EXECUTOR,
        company=creator.company,
    )
    ensure_executor_has_telegram(executor)

    task = Task.objects.create(
        title="Attach task",
        description="",
        creator=creator,
        assignee=executor,
        priority=Task.Priority.MEDIUM,
        status=Task.Status.NEW,
    )
    return creator, executor, task


def _assert_file_saved_for_task(task: Task):
    """Универсальная проверка:"""

    task.refresh_from_db()

    if hasattr(task, "result_file"):
        rf = getattr(task, "result_file")
        assert bool(rf), "result_file не сохранился в Task"
        assert rf.name, "result_file.name пустой"
    else:
        from tasks.models import TaskAttachment

        assert TaskAttachment.objects.filter(task=task).exists(), "Не создался TaskAttachment"


def test_creator_can_upload_result_file_via_patch(api_client):
    creator, executor, task = make_users_and_task()
    client = auth(api_client, creator)

    upload = SimpleUploadedFile(name="result.txt", content=b"result content", content_type="text/plain")

    resp = client.patch(
        f"/api/tasks/{task.id}/",
        data={"result_file": upload},
        format="multipart",
    )
    assert resp.status_code in (status.HTTP_200_OK, status.HTTP_202_ACCEPTED), resp.data

    # В твоём API PATCH-serializer не возвращает result_file в response,
    # поэтому проверяем факт сохранения в БД.
    _assert_file_saved_for_task(task)


def test_executor_can_upload_result_file_if_allowed(api_client):
    creator, executor, task = make_users_and_task()
    client = auth(api_client, executor)

    upload = SimpleUploadedFile(name="exec_result.txt", content=b"executor result", content_type="text/plain")

    resp = client.patch(
        f"/api/tasks/{task.id}/",
        data={"result_file": upload},
        format="multipart",
    )

    if resp.status_code in (status.HTTP_200_OK, status.HTTP_202_ACCEPTED):
        _assert_file_saved_for_task(task)
    else:
        assert resp.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_405_METHOD_NOT_ALLOWED), resp.data


def test_other_company_cannot_upload_result_file(api_client):
    creator, executor, task = make_users_and_task()

    outsider_creator = User.objects.create_user(
        email="outsider_creator@example.com",
        password="pass12345",
        role=User.Role.CREATOR,
    )
    client = auth(api_client, outsider_creator)

    upload = SimpleUploadedFile(name="hack.txt", content=b"hacked", content_type="text/plain")

    resp = client.patch(
        f"/api/tasks/{task.id}/",
        data={"result_file": upload},
        format="multipart",
    )

    assert resp.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)
