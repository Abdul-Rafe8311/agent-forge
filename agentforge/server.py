"""Optional authenticated single-project service. No requests occur during import or creation."""

import hmac
import logging
import threading
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass, field
from typing import Callable
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from . import __version__
from .config import AgentConfig
from .core import AgentWrapper
from .exceptions import ConfigurationError
from .server_schemas import RESULT_ADAPTER, ApiError, GenerateRequest, HealthResponse


@dataclass
class ServerConfig:
    agent: AgentConfig
    token: str = field(repr=False)
    host: str = "127.0.0.1"
    port: int = 8000
    max_task_chars: int = 16000
    max_body_bytes: int = 65536
    origins: list[str] = field(default_factory=list)

    def validate_settings(self) -> None:
        """Validate operator settings without constructing SDKs or binding sockets."""
        self.agent.validate_settings()
        if not isinstance(self.token, str) or not self.token.strip():
            raise ConfigurationError("Set AGENTFORGE_SERVER_TOKEN privately before serving")
        if not self.host.strip() or type(self.port) is not int or not 1 <= self.port <= 65535:
            raise ConfigurationError("Invalid server host/port")
        if not 1 <= self.max_task_chars <= 16000 or self.max_body_bytes < 1:
            raise ConfigurationError("Invalid request limits")
        if "*" in self.origins:
            raise ConfigurationError("CORS requires explicit allowed origins")


def authenticate_request(authorization: str | None, configured_token: str) -> None:
    """Compare a bearer token in constant time; header values never enter diagnostics."""
    supplied = authorization[7:] if authorization and authorization.startswith("Bearer ") else ""
    if not supplied or not hmac.compare_digest(supplied.encode(), configured_token.encode()):
        raise HTTPException(401, "Unauthorized", headers={"WWW-Authenticate": "Bearer"})


def _error(code: str, message: str, status: int, headers=None) -> JSONResponse:
    return JSONResponse(
        ApiError(code=code, message=message, request_id=str(uuid4())).model_dump(),
        status_code=status,
        headers=headers,
    )


class _BodyGate:
    def __init__(self, app: ASGIApp, config: ServerConfig):
        self.app, self.config = app, config

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http" or scope["path"] != "/generate" or scope["method"] != "POST":
            return await self.app(scope, receive, send)
        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])
        }
        try:
            authenticate_request(headers.get("authorization"), self.config.token)
        except HTTPException:
            return await _error(
                "unauthorized", "Unauthorized", 401, {"WWW-Authenticate": "Bearer"}
            )(scope, receive, send)
        if headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
            return await _error("unsupported_media_type", "Use application/json", 415)(
                scope, receive, send
            )
        # Buffer bounded chunks before FastAPI JSON parsing; independently cap decoded task length.
        chunks = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > self.config.max_body_bytes:
                return await _error("body_too_large", "Request exceeds body byte limit", 413)(
                    scope, receive, send
                )
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        sent = False

        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


def create_app(
    config: ServerConfig, wrapper_factory: Callable[[], AgentWrapper] | None = None
) -> FastAPI:
    """Create a fixed-project service with fresh wrappers and owned cleanup."""
    config.validate_settings()
    guard = threading.Lock()

    @asynccontextmanager
    async def lifespan(app):
        yield

    app = FastAPI(title="AgentForge", version=__version__, lifespan=lifespan)
    app.state.generation_guard = guard
    app.add_middleware(_BodyGate, config=config)
    if config.origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=config.origins,
            allow_methods=["POST", "GET"],
            allow_headers=["Authorization", "Content-Type"],
            allow_credentials=False,
        )

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError):
        return _error("invalid_request", "Request does not match the task-only schema", 422)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return _error(
            "unauthorized" if exc.status_code == 401 else "http_error",
            str(exc.detail),
            exc.status_code,
            exc.headers,
        )

    @app.get("/health", response_model=HealthResponse)
    def health():
        return HealthResponse(status="ok", version=__version__)

    @app.post("/generate")
    def generate(body: GenerateRequest, request: Request):
        authenticate_request(request.headers.get("authorization"), config.token)
        if len(body.task) > config.max_task_chars:
            return _error("invalid_request", "Task exceeds character limit", 422)
        if not guard.acquire(blocking=False):
            return _error("server_busy", "One generation is already active", 429)
        wrapper = None
        try:
            wrapper = wrapper_factory() if wrapper_factory else AgentWrapper(**asdict(config.agent))
            # Project identity cannot be chosen by the HTTP body or changed by a factory.
            if wrapper.config.project_id != config.agent.project_id:
                raise ConfigurationError("Wrapper project differs from configured server project")
            result = wrapper.run(body.task)
            payload = RESULT_ADAPTER.dump_python(result, mode="json")
            return JSONResponse(payload, headers={"Cache-Control": "no-store"})
        except Exception:
            return _error("internal_error", "Generation could not be completed", 500)
        finally:
            try:
                if wrapper is not None:
                    try:
                        wrapper.close()
                    except Exception:
                        logging.getLogger("agentforge").warning("Server resource cleanup failed")
            finally:
                guard.release()

    return app
