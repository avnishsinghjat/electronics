"""Request-scoped context: the acting user, read by the audit hook and the base mixin.

Phase 3 sets the actor from the authenticated user; background jobs and the seed
script set it explicitly. ``None`` means "system".
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

current_actor_id: ContextVar[uuid.UUID | None] = ContextVar("current_actor_id", default=None)


@contextmanager
def acting_as(actor_id: uuid.UUID | None) -> Iterator[None]:
    token = current_actor_id.set(actor_id)
    try:
        yield
    finally:
        current_actor_id.reset(token)
