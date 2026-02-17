from __future__ import annotations

import threading
from typing import Callable, Protocol

from redis import Redis
from rq import Queue

from codex_home.config import Settings


class RedisLike(Protocol):
    def set(self, key: str, value: str) -> None: ...
    def get(self, key: str) -> str | None: ...
    def lock(self, key: str, timeout: int): ...


class _InMemoryLock:
    def __init__(self, lock: threading.Lock):
        self._lock = lock

    def acquire(self, blocking: bool = False) -> bool:
        return self._lock.acquire(blocking=blocking)

    def release(self) -> None:
        if self._lock.locked():
            self._lock.release()


class InMemoryRedis:
    def __init__(self):
        self._store: dict[str, str] = {}
        self._locks: dict[str, threading.Lock] = {}

    def set(self, key: str, value: str) -> None:
        self._store[key] = value

    def get(self, key: str) -> str | None:
        return self._store.get(key)

    def lock(self, key: str, timeout: int):  # noqa: ARG002
        if key not in self._locks:
            self._locks[key] = threading.Lock()
        return _InMemoryLock(self._locks[key])


def build_redis(settings: Settings) -> RedisLike:
    if settings.disable_queue:
        return InMemoryRedis()
    return Redis.from_url(
        settings.redis_url,
        decode_responses=False,
        socket_connect_timeout=2,
        socket_timeout=2,
    )


def build_queue(settings: Settings, redis_client: RedisLike) -> Queue:
    return Queue(name=settings.queue_name, connection=redis_client, default_timeout=60 * 60)


def enqueue_job(settings: Settings, redis_client: RedisLike, job_id: str) -> str:
    if settings.disable_queue:
        return "queue_disabled"
    queue = build_queue(settings, redis_client)
    queued_job = queue.enqueue("codex_home.job_runner.process_job", job_id)
    return str(queued_job.id)


def queue_size(settings: Settings, redis_client: RedisLike) -> int:
    if settings.disable_queue:
        return 0
    queue = build_queue(settings, redis_client)
    return int(queue.count)


def set_kill_switch(redis_client: RedisLike, enabled: bool) -> None:
    redis_client.set("agents_enabled", "true" if enabled else "false")


def agents_enabled(redis_client: RedisLike) -> bool:
    value = redis_client.get("agents_enabled")
    if value is None:
        return True
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore").strip().lower() == "true"
    return str(value).strip().lower() == "true"


def with_redis_lock(
    redis_client: RedisLike,
    key: str,
    timeout_seconds: int,
    action: Callable[[], None],
) -> bool:
    lock = redis_client.lock(key, timeout=timeout_seconds)
    acquired = lock.acquire(blocking=False)
    if not acquired:
        return False
    try:
        action()
        return True
    finally:
        lock.release()
