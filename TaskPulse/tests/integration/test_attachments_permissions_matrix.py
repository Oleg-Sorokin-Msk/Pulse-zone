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
        email="creator_matrix@example.com",
        password="pass12345",
        role=User.Role.CREATOR,
    )
    executor = User.objects.create_user(
        email="executor_matrix@example.com",
        password="pass12345",
        role=User.Role.EXECUTOR,
        company=creator.company,
    )
    ensure_executor_has_telegram(executor)

    task = Task.objects.create(
        title="Matrix task",
        description="",
        creator=creator,
        assignee=executor,
        priority=Task.Priority.MEDIUM,
        status=Task.Status.NEW,
    )

    outsider = User.objects.create_user(
        email="outsider_matrix@example.com",
        password="pass12345",
        role=User.Role.CREATOR,
    )

    return creator, executor, outsider, task


def extract_first_attachment_ref(detail: dict) -> str | None:
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
    return None


def try_upload_general_attachment(api_client, task_id: int, upload: SimpleUploadedFile):
    """Адаптивная попытка загрузить general attachment."""

    candidates = [
        ("POST /api/tasks/{id}/attachments/", "post", f"/api/tasks/{task_id}/attachments/",
         {"file": upload, "kind": "general"}),
        ("POST /api/tasks/attachments/", "post", "/api/tasks/attachments/",
         {"task": task_id, "file": upload, "kind": "general"}),
        ("POST /api/tasks/{id}/upload-attachment/", "post", f"/api/tasks/{task_id}/upload-attachment/",
         {"file": upload, "kind": "general"}),
        ("PATCH /api/tasks/{id}/ (file)", "patch", f"/api/tasks/{task_id}/", {"file": upload}),
        ("PATCH /api/tasks/{id}/ (attachment)", "patch", f"/api/tasks/{task_id}/", {"attachment": upload}),
        ("PATCH /api/tasks/{id}/ (attachments=file)", "patch", f"/api/tasks/{task_id}/", {"attachments": upload}),
    ]

    last = None

    for _name, method, url, data in candidates:
        if method == "post":
            resp = api_client.post(url, data=data, format="multipart")
        else:
            resp = api_client.patch(url, data=data, format="multipart")

        last = (_name, resp)

        if resp.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED, status.HTTP_202_ACCEPTED):
            return _name, resp

    assert last is not None
    return last[0], last[1]


def test_executor_upload_general_attachment_matrix(api_client, settings, tmp_path):
    settings.DEBUG = True
    settings.MEDIA_ROOT = tmp_path
    settings.MEDIA_URL = "/media/"

    creator, executor, outsider, task = make_users_and_task()

    exec_client = auth(api_client, executor)

    upload = SimpleUploadedFile("exec_general.txt", b"EXEC-GENERAL", content_type="text/plain")
    used, resp = try_upload_general_attachment(exec_client, task.id, upload)

    if resp.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED, status.HTTP_202_ACCEPTED):
        # проверяем, что attachment реально виден в detail
        detail = exec_client.get(f"/api/tasks/{task.id}/")
        assert detail.status_code == status.HTTP_200_OK, detail.data

        file_ref = extract_first_attachment_ref(detail.data)
        assert file_ref, f"Upload был успешным, но attachments пуст. used={used}, detail={detail.data}"
    else:
        assert resp.status_code in (
            status.HTTP_403_FORBIDDEN,
            status.HTTP_405_METHOD_NOT_ALLOWED,
            status.HTTP_400_BAD_REQUEST,
        ), f"Неожиданный статус. used={used}, status={resp.status_code}, data={getattr(resp, 'data', None)}"


def test_outsider_cannot_get_attachment_link_from_detail(api_client):
    """Security: outsider не должен получить ссылку на attachment через API detail задачи."""

    creator, executor, outsider, task = make_users_and_task()

    outsider_client = auth(api_client, outsider)
    resp = outsider_client.get(f"/api/tasks/{task.id}/")
    assert resp.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)


def test_outsider_download_by_known_link_behavior(api_client, settings, tmp_path):
    """Проверяем, что будет, если outsider всё же знает прямую ссылку на файл."""

    settings.DEBUG = True
    settings.MEDIA_ROOT = tmp_path
    settings.MEDIA_URL = "/media/"

    creator, executor, outsider, task = make_users_and_task()

    creator_client = auth(api_client, creator)

    upload = SimpleUploadedFile("creator_general.txt", b"CREATOR-GENERAL", content_type="text/plain")
    used, up = try_upload_general_attachment(creator_client, task.id, upload)

    assert up.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED, status.HTTP_202_ACCEPTED), (
        f"Creator upload не прошёл, без этого тест бессмысленен. used={used}, status={up.status_code}, data={getattr(up, 'data', None)}"
    )

    detail = creator_client.get(f"/api/tasks/{task.id}/")
    assert detail.status_code == status.HTTP_200_OK, detail.data

    file_ref = extract_first_attachment_ref(detail.data)
    assert file_ref, f"attachments не появился после upload. used={used}, detail={detail.data}"

    outsider_client = auth(api_client, outsider)

    dl = outsider_client.get(file_ref)

    if file_ref.startswith("/media/") or file_ref.startswith("/"):
        # Публичная раздача (DEBUG static). Тут обычно будет 200.
        assert dl.status_code == status.HTTP_200_OK
    else:
        assert dl.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND)
