"""
goldbridge - a small, standalone service. Its ONLY job: poll a
third-party gold-trading platform (using credentials the platform
owner issued directly) and re-expose the current buy/sell price as a
plain local JSON endpoint.

This is intentionally NOT part of the main app's codebase - it's a
separate private service, with its own credentials, meant to be run on
its own (e.g. as its own systemd service, or even on its own small
VPS). The main app's existing generic API price source
(app/price_sources/api_source.py in goldapp) can already consume this
endpoint with zero code changes - see README.md.

Run: uvicorn app.main:app --host 127.0.0.1 --port 9100
(127.0.0.1 only - this should never be reachable from outside the
server it runs on; only the main app, running on the same machine or
over a private network, should ever talk to it.)

--- Security model ---
This is a private, internal-only service (bound to 127.0.0.1), but it
still carries real financial data and is one hop away from being
proxied or opened up by mistake, so it's hardened as if it weren't:
  - Every data endpoint requires `Authorization: Bearer <BRIDGE_API_KEY>`
    (see app/core/security.py). goldapp's ApiPriceSource already sends
    this if GOLDAPP_PRICE_API_KEY is set - no code changes needed there,
    just matching .env values.
  - Per-IP rate limiting on top of the API key.
  - Responses are typed Pydantic models (app/models/schemas.py), not
    raw dicts.
  - Source credentials (uID/uToken) are never logged, even on error
    paths (see app/services/poller.py).
  - /health is the only unauthenticated endpoint, and it leaks no
    price data or secrets.

--- Module layout ---
  app/core/       config, logging, security - cross-cutting concerns
  app/models/     Pydantic response schemas
  app/services/   session storage, source parsing, in-memory cache,
                  the background poller - all the actual logic
  app/routers/    thin HTTP-layer wiring over the services
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app.core.config import get_settings
from app.core.logging import logger
from app.core.security import warn_if_unprotected
from app.routers import health, prices
from app.services.poller import poll_loop

settings = get_settings()

tags_metadata = [
    {
        "name": "prices",
        "description": "Authenticated price data. Every route here requires "
                        "`Authorization: Bearer <BRIDGE_API_KEY>`.",
    },
    {
        "name": "health",
        "description": "Unauthenticated liveness check for process monitors. "
                        "Leaks no price data or secrets.",
    },
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    warn_if_unprotected()
    task = asyncio.create_task(poll_loop())
    yield
    task.cancel()


app = FastAPI(
    title="goldbridge",
    description=(
        "Private, internal-only gold price bridge.\n\n"
        "Polls a third-party gold-trading platform and re-exposes the "
        "current buy/sell price as a local JSON API for goldapp to consume. "
        "**Not for public exposure** - bind to 127.0.0.1 only.\n\n"
        "All `/prices` and `/price` requests require a Bearer API key "
        "(`BRIDGE_API_KEY`). Click **Authorize** below to set it once for "
        "this docs page."
    ),
    version="2.0.0",
    contact={"name": "goldbridge (internal)"},
    openapi_tags=tags_metadata,
    lifespan=lifespan,
)

app.include_router(prices.router, tags=["prices"])
app.include_router(health.router, tags=["health"])


def custom_openapi():
    """Registers the Bearer auth scheme so /docs shows an Authorize button
    and correctly marks which endpoints need it, instead of every request
    silently 401'ing with no explanation in the UI."""
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=tags_metadata,
    )
    schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "description": "Value of BRIDGE_API_KEY from .env. Leave the "
                            "Authorize dialog empty if BRIDGE_API_KEY is unset "
                            "(dev-only, unauthenticated mode).",
        }
    }
    for path, methods in schema["paths"].items():
        for method, operation in methods.items():
            if "health" not in path:
                operation["security"] = [{"BearerAuth": []}]
    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi