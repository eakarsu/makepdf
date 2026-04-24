"""FastAPI application factory for the MakePDF web UI."""

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from makepdf.exceptions import MakePdfError
from makepdf.web.shared import templates, STATIC_DIR

from makepdf.web.routes import create, edit, merge, forms, extract, transform, ocr, sign
from makepdf.web.routes import redact, crop_route, stamp_route, bates_route
from makepdf.web.routes import compare_route, flatten_route, metadata_route, attach_route
from makepdf.web.routes import link_route, optimize_route, a11y_route, markup_route


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""

    app = FastAPI(title="MakePDF", description="PDF Toolkit Web UI")

    # Static files
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Include route modules
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

    # Root route
    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return templates.TemplateResponse("index.html", {"request": request})

    # Global error handler for MakePDF exceptions
    @app.exception_handler(MakePdfError)
    async def makepdf_error_handler(request: Request, exc: MakePdfError):
        return JSONResponse(
            status_code=400,
            content={"error": str(exc), "type": type(exc).__name__},
        )

    # Catch-all for unexpected errors
    @app.exception_handler(Exception)
    async def general_error_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={"error": f"Internal server error: {exc}", "type": "ServerError"},
        )

    return app


app = create_app()
