import factory
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token

from tasks.models import Task, TaskMessage
from integrations.models import TelegramProfile, TelegramLinkToken

User = get_user_model()


class UserFactory(factory.django.DjangoModelFactory):
    """Фабрика пользователей."""

    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    first_name = "Test"
    last_name = "User"
    is_active = True

    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        raw = extracted or "pass12345"
        self.set_password(raw)
        if create:
            self.save()


class TokenFactory(factory.django.DjangoModelFactory):
    """Фабрика DRF токенов."""

    class Meta:
        model = Token

    user = factory.SubFactory(UserFactory)


class TaskFactory(factory.django.DjangoModelFactory):
    """Фабрика задач."""

    class Meta:
        model = Task

    title = factory.Faker("sentence", nb_words=4)
    description = factory.Faker("paragraph")

    status = "new"
    priority = "medium"

    creator = factory.SubFactory(UserFactory)
    assignee = factory.SubFactory(UserFactory)


class TaskMessageFactory(factory.django.DjangoModelFactory):
    """Фабрика сообщений чата задачи."""

    class Meta:
        model = TaskMessage

    task = factory.SubFactory(TaskFactory)
    sender = factory.SubFactory(UserFactory)
    text = factory.Faker("sentence", nb_words=10)


class TelegramProfileFactory(factory.django.DjangoModelFactory):
    """Фабрика TelegramProfile."""

    class Meta:
        model = TelegramProfile

    user = factory.SubFactory(UserFactory)
    telegram_user_id = factory.Sequence(lambda n: 100000 + n)
    chat_id = factory.Sequence(lambda n: 200000 + n)


class TelegramLinkTokenFactory(factory.django.DjangoModelFactory):
    """Фабрика одноразового токена привязки Telegram."""

    class Meta:
        model = TelegramLinkToken

    user = factory.SubFactory(UserFactory)
    is_used = False
