"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

from .config import get_settings
from .db.database import init_db

# Get settings
settings = get_settings()

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    init_db()
    settings.clients_dir.mkdir(parents=True, exist_ok=True)
    yield
    # Shutdown
    pass


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    description="Web application for FOLIO migration project management",
    version="0.1.0",
    lifespan=lifespan,
    root_path=settings.root_path,
)

# Mount static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Templates
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Add root_path to template globals
templates.env.globals["root_path"] = settings.root_path


# Import and include API routers
from .api import clients, credentials, files, config_editor, health, tasks, executions  # noqa: E402

app.include_router(clients.router)
app.include_router(credentials.router)
app.include_router(files.router)
app.include_router(config_editor.router)
app.include_router(health.router)
app.include_router(tasks.router)
app.include_router(executions.router)


# HTML Pages
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Home page - dashboard."""
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "title": "Dashboard"},
    )


@app.get("/clients", response_class=HTMLResponse)
async def clients_list_page(request: Request):
    """Clients list page."""
    return templates.TemplateResponse(
        "clients/list.html",
        {"request": request, "title": "Client Projects"},
    )


@app.get("/clients/new", response_class=HTMLResponse)
async def clients_create_page(request: Request):
    """Create new client page."""
    return templates.TemplateResponse(
        "clients/create.html",
        {"request": request, "title": "Create New Project"},
    )


@app.get("/clients/{client_code}", response_class=HTMLResponse)
async def clients_detail_page(request: Request, client_code: str):
    """Client detail page."""
    return templates.TemplateResponse(
        "clients/detail.html",
        {"request": request, "title": f"Project: {client_code}", "client_code": client_code},
    )


@app.get("/clients/{client_code}/credentials", response_class=HTMLResponse)
async def clients_credentials_page(request: Request, client_code: str):
    """Client credentials page."""
    return templates.TemplateResponse(
        "clients/credentials.html",
        {"request": request, "title": "FOLIO Credentials", "client_code": client_code},
    )


@app.get("/clients/{client_code}/files", response_class=HTMLResponse)
async def clients_files_page(request: Request, client_code: str):
    """Client files page."""
    return templates.TemplateResponse(
        "files/upload.html",
        {"request": request, "title": "File Management", "client_code": client_code},
    )


@app.get("/clients/{client_code}/config/{filename}", response_class=HTMLResponse)
async def clients_config_page(request: Request, client_code: str, filename: str):
    """Configuration editor page."""
    return templates.TemplateResponse(
        "config/editor.html",
        {
            "request": request,
            "title": f"Edit: {filename}",
            "client_code": client_code,
            "filename": filename,
        },
    )


@app.get("/clients/{client_code}/execute", response_class=HTMLResponse)
async def clients_execute_page(request: Request, client_code: str):
    """Task execution page."""
    return templates.TemplateResponse(
        "executions/run.html",
        {
            "request": request,
            "title": "Execute Tasks",
            "client_code": client_code,
        },
    )


@app.get("/clients/{client_code}/executions", response_class=HTMLResponse)
async def clients_executions_page(request: Request, client_code: str):
    """Execution history page."""
    return templates.TemplateResponse(
        "executions/history.html",
        {
            "request": request,
            "title": "Execution History",
            "client_code": client_code,
        },
    )


@app.get("/clients/{client_code}/executions/{execution_id}", response_class=HTMLResponse)
async def execution_detail_page(request: Request, client_code: str, execution_id: int):
    """Execution detail page."""
    return templates.TemplateResponse(
        "executions/detail.html",
        {
            "request": request,
            "title": f"Execution #{execution_id}",
            "client_code": client_code,
            "execution_id": execution_id,
        },
    )


def main():
    """Run the application."""
    import uvicorn

    uvicorn.run(
        "folio_migration_web.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
