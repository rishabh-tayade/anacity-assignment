import logging
from typing import Protocol

from moveflow.domain.models import MoveRequest

logger = logging.getLogger(__name__)


class Notifier(Protocol):
    def notify_resident(self, request: MoveRequest, text: str) -> None: ...

    def notify_admin(self, request: MoveRequest, text: str) -> None: ...


class LogNotifier:
    """Stand-in for push / SMS / WhatsApp notifications.

    Messages are already visible in-app through the request's message thread,
    so for the prototype we only log what would have been sent.
    """

    def notify_resident(self, request: MoveRequest, text: str) -> None:
        logger.info("[to resident %s] %s: %s", request.phone, request.id, text)

    def notify_admin(self, request: MoveRequest, text: str) -> None:
        logger.info("[to %s admin desk] %s: %s", request.community_id, request.id, text)
