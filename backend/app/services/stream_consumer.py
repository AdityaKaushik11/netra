"""Message-channel ingestion: analytics producers can XADD to a Redis Stream instead of calling
REST. A consumer group spreads messages over all API replicas; each message is ACKed only after
it is committed, un-parseable messages go to a dead-letter stream, and messages left pending by
a crashed replica are re-claimed. (At national scale the same contract moves to Kafka.)"""

import asyncio
import contextlib
import json
import logging
import socket

from pydantic import ValidationError

from app.core.config import get_settings
from app.db import SessionLocal
from app.schemas.event import DetectionEventIn
from app.services.ingestion import IngestError, ingest
from app.services.redis_client import get_redis

log = logging.getLogger(__name__)
GROUP = "netra-ingest"
DLQ = "netra:ingest:dlq"


async def _handle(msg_id: str, fields: dict, stream: str) -> None:
    r = get_redis()
    try:
        payload = DetectionEventIn.model_validate(json.loads(fields["payload"]))
        async with SessionLocal() as db:
            await ingest(db, payload, source_client=f"stream:{fields.get('client', 'unknown')}")
    except (ValidationError, IngestError, KeyError, json.JSONDecodeError) as exc:
        await r.xadd(DLQ, {"id": msg_id, "error": str(exc)[:500], **fields}, maxlen=10_000)
    await r.xack(stream, GROUP, msg_id)


async def run_consumer(stop: asyncio.Event) -> None:
    s = get_settings()
    r = get_redis()
    if r is None or not s.stream_ingest_enabled:
        return
    stream = s.stream_ingest_key
    consumer = socket.gethostname()
    with contextlib.suppress(Exception):
        await r.xgroup_create(stream, GROUP, id="0", mkstream=True)
    log.info("stream consumer %s listening on %s", consumer, stream)
    last_claim = 0.0
    loop = asyncio.get_running_loop()
    while not stop.is_set():
        try:
            if loop.time() - last_claim > 30:
                last_claim = loop.time()
                _, claimed, _ = await r.xautoclaim(stream, GROUP, consumer, min_idle_time=60_000, count=100)
                for msg_id, fields in claimed:
                    await _handle(msg_id, fields, stream)
            resp = await r.xreadgroup(GROUP, consumer, {stream: ">"}, count=100, block=1000)
            for _, messages in resp or []:
                for msg_id, fields in messages:
                    try:
                        await _handle(msg_id, fields, stream)
                    except Exception:
                        log.exception("stream message %s failed; left pending for retry", msg_id)
        except Exception:
            log.exception("stream consumer error")
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=2)
