from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, Integer
from sqlalchemy.dialects import mysql
from sqlalchemy.types import TypeDecorator

# BIGINT primary keys on MySQL; SQLite only auto-increments INTEGER PRIMARY KEY.
BigIntPK = BigInteger().with_variant(Integer, "sqlite")


class UTCDateTime(TypeDecorator):
    """Stores naive UTC (MySQL DATETIME(6)), always returns timezone-aware UTC datetimes."""

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "mysql":
            return dialect.type_descriptor(mysql.DATETIME(fsp=6))
        return dialect.type_descriptor(DateTime())

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=UTC)


def utcnow() -> datetime:
    return datetime.now(UTC)
