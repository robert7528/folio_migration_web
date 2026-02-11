# FOLIO Migration Web Portal - Claude Code Instructions

## Development Environment

### Workflow: Windows (edit) → GitHub → Linux (run)
- **Windows local**: Source code editing only. No Python runtime available.
- **GitHub**: Central repository. All code changes must be pushed here.
- **Linux server**: Pull from GitHub to deploy and run.

**IMPORTANT**: Never attempt to run Python, start servers, or execute tests on this Windows machine.
When code changes are done, commit/push to GitHub and remind the user to pull on the Linux server.

### Deploy (Linux server)
```bash
cd /folio/folio_migration_web
git pull
sudo systemctl restart folio-migration-web
```

## Project Structure

```
D:\folio_migration_web\                # Git repo root (this directory)
├── CLAUDE.md                          # This file
├── pyproject.toml
├── src/folio_migration_web/           # Python source
│   ├── main.py                        # FastAPI app + uvicorn entry point
│   ├── config.py                      # Pydantic settings
│   ├── api/                           # FastAPI routers
│   │   ├── clients.py
│   │   ├── credentials.py
│   │   ├── config_editor.py
│   │   ├── executions.py
│   │   ├── files.py
│   │   ├── folio_reference.py
│   │   ├── health.py
│   │   ├── validation.py
│   │   ├── deletion.py
│   │   └── tasks.py
│   ├── services/                      # Business logic
│   ├── db/                            # SQLAlchemy models + SQLite
│   ├── models/                        # Pydantic schemas
│   └── utils/
├── templates/                         # Jinja2 HTML templates
├── static/                            # CSS, JS assets
├── deployment/                        # Nginx, systemd configs
└── docs/                              # Migration documentation
```

## Reference Data (outside this repo)

Migration data and config examples are at `D:\FOLIO-FSE\`:
- `D:\FOLIO-FSE\migration_thu\mapping_files\` - THU migration configs & mappings
- `D:\FOLIO-FSE\migration_example\` - Example migration project

Use absolute paths to read these files when needed.

## Technology Stack

- **Backend**: Python 3, FastAPI, SQLAlchemy, SQLite, httpx (async)
- **Frontend**: Jinja2 templates, vanilla JavaScript, custom CSS
- **Migration Tool**: folio_migration_tools (installed in .venv on Linux)
- **FOLIO API**: Okapi gateway with token-based auth

## Git

- **GitHub**: https://github.com/robert7528/folio_migration_web.git
- **Branch**: `main`
- This is the only repo to commit/push to.

## Key Patterns

- API routes use `/api/clients/{client_code}/...` prefix
- DB migrations handled via `_run_migrations()` in database.py (ALTER TABLE for SQLite)
- Credentials are encrypted at rest (Fernet encryption)
- Background tasks use FastAPI BackgroundTasks or threading
- FOLIO API client uses async httpx with token auth
