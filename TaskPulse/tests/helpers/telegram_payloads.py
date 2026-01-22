def tg_update_start(*, update_id: int, user_id: int, chat_id: int, token: str) -> dict:
    """
    Создаёт Telegram update для сценария /start <token>.
    """

    return {
        "update_id": update_id,
        "message": {
            "message_id": 1,
            "from": {"id": user_id, "is_bot": False, "first_name": "Test"},
            "chat": {"id": chat_id, "type": "private"},
            "date": 1700000000,
            "text": f"/start {token}",
        },
    }


def tg_update_reply_to_task(*, update_id: int, user_id: int, chat_id: int, task_id: int,
                            reply_message_id: int = 50) -> dict:
    """
    Создаёт Telegram update для сценария:
    - пользователь отвечает Reply на сообщение, в тексте которого есть "/tasks/<id>"
    - пользовательский текст сообщения (новый) должен стать TaskMessage
    """

    return {
        "update_id": update_id,
        "message": {
            "message_id": 2,
            "from": {"id": user_id, "is_bot": False, "first_name": "Test"},
            "chat": {"id": chat_id, "type": "private"},
            "date": 1700000001,
            "text": "Мой ответ из Telegram",
            "reply_to_message": {
                "message_id": reply_message_id,
                # ВАЖНО: именно этот текст парсится в твоей логике
                "text": f"У вас новая задача: /tasks/{task_id}",
            },
        },
    }


def tg_update_plain_text(*, update_id: int, user_id: int, chat_id: int, text: str) -> dict:
    """
    Обычное сообщение без reply.
    По бизнес-логике должно игнорироваться (или отвечать подсказкой).
    """

    return {
        "update_id": update_id,
        "message": {
            "message_id": 3,
            "from": {"id": user_id, "is_bot": False, "first_name": "Test"},
            "chat": {"id": chat_id, "type": "private"},
            "date": 1700000002,
            "text": text,
        },
    }
