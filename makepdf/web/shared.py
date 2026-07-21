"""Shared web configuration (breaks circular imports between app and routes)."""

from pathlib import Path

from fastapi.templating import Jinja2Templates


class CompatibleTemplates(Jinja2Templates):
    """Keep the project's explicit context style across Starlette releases."""

    def TemplateResponse(
        self,
        name,
        context,
        status_code=200,
        headers=None,
        media_type=None,
        background=None,
    ):
        request = context.get("request")
        return super().TemplateResponse(
            request=request,
            name=name,
            context=context,
            status_code=status_code,
            headers=headers,
            media_type=media_type,
            background=background,
        )

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

templates = CompatibleTemplates(directory=str(TEMPLATES_DIR))
