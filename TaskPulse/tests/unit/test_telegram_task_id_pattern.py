import re

import pytest

TASK_LINK_RE = re.compile(r"/tasks/(?P<task_id>\d+)")


def extract_task_id(text: str | None) -> int | None:
    """Локальный хелпер только для теста:"""

    if not text:
        return None

    m = TASK_LINK_RE.search(text)
    if not m:
        return None

    return int(m.group("task_id"))


@pytest.mark.unit
@pytest.mark.parametrize(
    "text, expected",
    [
        (None, None),
        ("", None),
        ("У вас новая задача: /tasks/123", 123),
        ("open /tasks/5 please", 5),
        ("prefix /tasks/0007 suffix", 7),
        ("несколько ссылок /tasks/1 и /tasks/2", 1),
        ("/tasks/abc", None),
        ("/task/123", None),
        ("no link here", None),
    ],
)
def test_task_id_regex_extracts_id(text, expected):
    """Проверяем извлечение task_id из типичного текста."""

    assert extract_task_id(text) == expected
