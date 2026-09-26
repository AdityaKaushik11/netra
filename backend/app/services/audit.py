from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog
from app.models.enums import ActorType


class Actor:
    """Who performed an action — a human user, a machine API client or the platform itself."""

    def __init__(self, type_: ActorType, id_: str | None, name: str | None, ip: str | None = None):
        self.type = type_
        self.id = id_
        self.name = name
        self.ip = ip

    @classmethod
    def system(cls, name: str = "system") -> "Actor":
        return cls(ActorType.SYSTEM, None, name)


def record(
    db: AsyncSession,
    actor: Actor,
    action: str,
    entity_type: str,
    entity_id: str | int | None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_type=actor.type,
        actor_id=actor.id,
        actor_name=actor.name,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        details=details,
        ip_address=actor.ip,
    )
    db.add(entry)
    return entry


def diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {k: {"from": before.get(k), "to": v} for k, v in after.items() if before.get(k) != v}
