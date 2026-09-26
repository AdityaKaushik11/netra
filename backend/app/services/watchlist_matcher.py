"""In-memory watchlist index used on the hot ingestion path.

* Exact matches: dict lookup on the normalised identifier.
* Fuzzy matches (ANPR OCR errors such as 0<->O, 8<->B, a dropped character): a
  SymSpell-style deletion index finds every entry within edit distance 1 in O(len) time,
  independent of watchlist size.

Replicas notice watchlist changes through a version counter in Redis, so no replica
serves a stale list for longer than one event.
"""

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import WatchlistEntry
from app.models.enums import EntityType, MatchType, Severity, WatchlistCategory
from app.services.redis_client import get_redis

VERSION_KEY = "netra:watchlist:version"


@dataclass(frozen=True)
class CachedEntry:
    id: int
    entity_type: EntityType
    identifier: str
    identifier_normalized: str
    category: WatchlistCategory
    severity: Severity
    description: str | None
    valid_until: datetime | None


@dataclass(frozen=True)
class Match:
    entry: CachedEntry
    match_type: MatchType


def _deletes(s: str) -> set[str]:
    return {s[:i] + s[i + 1 :] for i in range(len(s))}


def levenshtein_le1(a: str, b: str) -> bool:
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        return sum(x != y for x, y in zip(a, b, strict=True)) == 1
    if la > lb:
        a, b = b, a
    # b is longer by one: check a single insertion
    i = j = 0
    skipped = False
    while i < len(a) and j < len(b):
        if a[i] != b[j]:
            if skipped:
                return False
            skipped = True
            j += 1
        else:
            i += 1
            j += 1
    return True


class WatchlistMatcher:
    def __init__(self) -> None:
        self._exact: dict[tuple[EntityType, str], CachedEntry] = {}
        self._deletion_index: dict[str, set[int]] = {}
        self._by_id: dict[int, CachedEntry] = {}
        self._version: str | None = None
        self._local_version = 0
        self._loaded_at = 0.0
        self._lock = asyncio.Lock()

    async def _remote_version(self) -> str:
        r = get_redis()
        if r is None:
            return str(self._local_version)
        v = await r.get(VERSION_KEY)
        return v or "0"

    async def invalidate(self) -> None:
        r = get_redis()
        self._local_version += 1
        if r is not None:
            await r.incr(VERSION_KEY)

    async def ensure_loaded(self, db: AsyncSession) -> None:
        version = await self._remote_version()
        if version == self._version and time.monotonic() - self._loaded_at < 300:
            return
        async with self._lock:
            if version == self._version and time.monotonic() - self._loaded_at < 300:
                return
            rows = (await db.execute(select(WatchlistEntry).where(WatchlistEntry.is_active.is_(True)))).scalars()
            exact: dict[tuple[EntityType, str], CachedEntry] = {}
            deletion: dict[str, set[int]] = {}
            by_id: dict[int, CachedEntry] = {}
            for row in rows:
                entry = CachedEntry(
                    id=row.id,
                    entity_type=row.entity_type,
                    identifier=row.identifier,
                    identifier_normalized=row.identifier_normalized,
                    category=row.category,
                    severity=row.severity,
                    description=row.description,
                    valid_until=row.valid_until,
                )
                exact[(row.entity_type, row.identifier_normalized)] = entry
                by_id[row.id] = entry
                if row.entity_type == EntityType.VEHICLE:
                    for key in _deletes(row.identifier_normalized) | {row.identifier_normalized}:
                        deletion.setdefault(key, set()).add(row.id)
            self._exact, self._deletion_index, self._by_id = exact, deletion, by_id
            self._version = version
            self._loaded_at = time.monotonic()

    def match(self, entity_type: EntityType, identifier_normalized: str) -> list[Match]:
        now = datetime.now(UTC)

        def live(e: CachedEntry) -> bool:
            return e.valid_until is None or e.valid_until > now

        hit = self._exact.get((entity_type, identifier_normalized))
        if hit and live(hit):
            return [Match(hit, MatchType.EXACT)]
        if entity_type != EntityType.VEHICLE or not get_settings().fuzzy_match_enabled:
            return []
        if len(identifier_normalized) < 6:  # too short for a safe fuzzy match
            return []
        candidates: set[int] = set()
        for key in _deletes(identifier_normalized) | {identifier_normalized}:
            candidates |= self._deletion_index.get(key, set())
        matches = []
        for cid in candidates:
            e = self._by_id[cid]
            if live(e) and levenshtein_le1(e.identifier_normalized, identifier_normalized):
                matches.append(Match(e, MatchType.FUZZY))
        return matches

    @property
    def size(self) -> int:
        return len(self._by_id)


matcher = WatchlistMatcher()
