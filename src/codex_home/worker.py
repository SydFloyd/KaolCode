from __future__ import annotations

import logging
import time

from redis import Redis
from rq import Worker

from codex_home.config import get_settings
from codex_home.db import build_engine, build_session_factory, init_db
from codex_home.logging_utils import configure_logging
from codex_home.metrics import WORKER_HEARTBEAT
from codex_home.policy import load_repo_profiles
from codex_home.queueing import build_queue, build_redis
from codex_home.repository import Repository


logger = logging.getLogger(__name__)


def bootstrap_state() -> tuple:
    settings = get_settings()
    configure_logging(settings.log_level)

    engine = build_engine(settings.database_url)
    if settings.auto_migrate:
        init_db(engine)
    session_factory = build_session_factory(engine)
    redis_client = build_redis(settings)

    repo_profiles = load_repo_profiles(settings.repos_path)
    with session_factory() as session:
        Repository(session).upsert_repo_profiles(repo_profiles)

    return settings, redis_client


def run_worker(redis_client: Redis) -> None:
    settings = get_settings()
    queue = build_queue(settings, redis_client)
    worker = Worker([queue], connection=redis_client, name="codex-home-worker")
    logger.info("Starting worker for queue '%s'", settings.queue_name)
    worker.work(with_scheduler=True)


def main() -> None:
    settings, redis_client = bootstrap_state()
    WORKER_HEARTBEAT.set(time.time())
    logger.info("Worker bootstrap complete", extra={"queue": settings.queue_name})
    run_worker(redis_client)


if __name__ == "__main__":
    main()
