"""
Logging setup, isolated so it's configured exactly once regardless of
which module gets imported first.

IMPORTANT: nothing in this codebase should ever log
Settings.source_uid_env / source_utoken_env (or the loaded session's
uid/utoken), even at DEBUG level - those are the credentials that
authenticate as the upstream account. Log the fact that a request
happened / failed, never the credentials used to make it.
"""
import logging

from app.core.config import get_settings


def setup_logging() -> logging.Logger:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # httpx logs every request at INFO - at 1 poll/sec that drowns the
    # useful poller lines. Keep warnings/errors only.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    return logging.getLogger("goldbridge")


logger = setup_logging()