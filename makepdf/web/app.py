"""FastAPI application factory for the MakePDF web UI."""

import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from makepdf.exceptions import MakePdfError
from makepdf.web.shared import templates, STATIC_DIR
from makepdf.config import MAX_UPLOAD_SIZE, SERVICE_ENV
from makepdf.web.auth import Identity, authenticate_api_key, require_identity
from makepdf.web.operations import configuration_errors, metrics

from makepdf.web.routes import create, edit, merge, forms, extract, transform, ocr, sign
from makepdf.web.routes import redact, crop_route, stamp_route, bates_route
from makepdf.web.routes import compare_route, flatten_route, metadata_route, attach_route
from makepdf.web.routes import link_route, optimize_route, a11y_route, markup_route

# AI / async routers
from makepdf.web.routes import (
    jobs,
    summarize,
    smart_redact,
    ocr_async,
    ai_classify,
    ai_form_filler,
    ai_audit,
    ai_results,
    governance,
    runtime_ai,
    runtime_auth,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def service_lifespan(_app: FastAPI):
    errors = configuration_errors(require_worker=False)
    if errors:
        raise RuntimeError("Unsafe production configuration: " + "; ".join(errors))
    yield


# ---------------------------------------------------------------------------
# Helmet-equivalent security headers middleware
# ---------------------------------------------------------------------------
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add a baseline of security headers to every response."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        # Lock down COOP/COEP for any embedded SharedArrayBuffer use cases
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        # Conservative CSP: allow self + inline (Jinja templates use inline scripts)
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data: blob:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
            "font-src 'self' data:; object-src 'none'; frame-ancestors 'none';",
        )
        # Only emit HSTS over TLS
        if request.url.scheme == "https":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        started = time.monotonic()
        response = await call_next(request)
        metrics.observe(request.method, response.status_code, time.monotonic() - started)
        return response


class ProductionBoundaryMiddleware(BaseHTTPMiddleware):
    """Enforce identity and coarse body limits before mutable production routes."""

    _DURABLE_MUTATION_PREFIXES = (
        "/api/ocr/",
        "/api/jobs/",
        "/api/governance/",
        "/api/cloud-storage/",
    )

    async def dispatch(self, request: Request, call_next):
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_UPLOAD_SIZE + 1024 * 1024:
            return JSONResponse(status_code=413, content={"detail": "Request exceeds the configured limit."})
        if SERVICE_ENV == "production" and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            identity = authenticate_api_key(request.headers.get("X-API-Key"))
            if not identity:
                return JSONResponse(status_code=401, content={"detail": "A valid tenant user API key is required."})
            request.state.identity = identity
            if not request.url.path.startswith(self._DURABLE_MUTATION_PREFIXES):
                return JSONResponse(
                    status_code=410,
                    content={
                        "detail": (
                            "Legacy synchronous transformations are disabled in production; "
                            "use the local CLI/library or a durable API endpoint."
                        )
                    },
                )
        response = await call_next(request)
        response.headers.setdefault("X-Request-ID", request.headers.get("X-Request-ID", os.urandom(12).hex()))
        return response


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""

    app = FastAPI(
        title="MakePDF",
        description=(
            "PDF Toolkit Web UI.\n\n"
            "Protected endpoints require an ``X-API-Key`` header. "
            "AI endpoints are additionally rate-limited to 20/hr per key."
        ),
        lifespan=service_lifespan,
    )

    # ------------------------------------------------------------------
    # Security middleware (helmet-equivalent + CORS + trusted hosts)
    # ------------------------------------------------------------------
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(ProductionBoundaryMiddleware)

    cors_origins_env = os.getenv("MAKEPDF_CORS_ORIGINS", "").strip()
    if cors_origins_env:
        origins = [o.strip() for o in cors_origins_env.split(",") if o.strip()]
    else:
        origins = ["http://localhost:8000", "http://127.0.0.1:8000"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    trusted_hosts_env = os.getenv("MAKEPDF_TRUSTED_HOSTS", "").strip()
    if trusted_hosts_env:
        hosts = [h.strip() for h in trusted_hosts_env.split(",") if h.strip()]
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)

    # Static files
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # ------------------------------------------------------------------
    # Existing UI routers (HTML form pages)
    # ------------------------------------------------------------------
    app.include_router(create.router)
    app.include_router(edit.router)
    app.include_router(merge.router)
    app.include_router(forms.router)
    app.include_router(extract.router)
    app.include_router(transform.router)
    app.include_router(ocr.router)
    app.include_router(sign.router)
    app.include_router(redact.router)
    app.include_router(crop_route.router)
    app.include_router(stamp_route.router)
    app.include_router(bates_route.router)
    app.include_router(compare_route.router)
    app.include_router(flatten_route.router)
    app.include_router(metadata_route.router)
    app.include_router(attach_route.router)
    app.include_router(link_route.router)
    app.include_router(optimize_route.router)
    app.include_router(a11y_route.router)
    app.include_router(markup_route.router)

    # ------------------------------------------------------------------
    # AI / async routers (X-API-Key + 20/hr rate limit)
    # ------------------------------------------------------------------
    app.include_router(jobs.router)
    app.include_router(summarize.router)
    app.include_router(smart_redact.router)
    app.include_router(ocr_async.router)
    app.include_router(ai_classify.router)
    app.include_router(ai_form_filler.router)
    app.include_router(ai_audit.router)
    app.include_router(ai_results.router)
    app.include_router(governance.router)
    app.include_router(runtime_auth.router)
    app.include_router(runtime_ai.router)
    from makepdf.web.routes import cloud_storage as _cs, workspaces as _ws, a11y_remediation as _ar, smart_table as _st, ediscovery as _ed, ocr_translate as _ot  # noqa: E402
    app.include_router(_cs.router)
    app.include_router(_ws.router)
    app.include_router(_ar.router)
    app.include_router(_st.router)
    app.include_router(_ed.router)
    app.include_router(_ot.router)

    # ------------------------------------------------------------------
    # Root + health
    # ------------------------------------------------------------------
    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return templates.TemplateResponse("index.html", {
            "request": request,
            "demo_enabled": os.getenv("MAKEPDF_ENV", "production") != "production",
        })

    @app.get("/health")
    async def health():
        """Health check — no auth required."""
        return {"status": "ok"}

    @app.get("/ready")
    async def ready():
        errors = configuration_errors(require_worker=True)
        return JSONResponse(
            status_code=503 if errors else 200,
            content={"status": "not-ready" if errors else "ready", "errors": errors},
        )

    @app.get("/metrics", response_class=PlainTextResponse)
    async def service_metrics(_identity: Identity = Depends(require_identity)):
        return PlainTextResponse(metrics.render(), media_type="text/plain; version=0.0.4")

    # ------------------------------------------------------------------
    # Error handlers
    # ------------------------------------------------------------------
    @app.exception_handler(MakePdfError)
    async def makepdf_error_handler(request: Request, exc: MakePdfError):
        return JSONResponse(
            status_code=400,
            content={"error": str(exc), "type": type(exc).__name__},
        )

    @app.exception_handler(Exception)
    async def general_error_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "type": "ServerError"},
        )

    return app


app = create_app()
