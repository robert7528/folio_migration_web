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
│   │   ├── clients.py                 # Client CRUD
│   │   ├── credentials.py            # FOLIO credentials (encrypted)
│   │   ├── config_editor.py          # Mapping file editor
│   │   ├── conversion.py             # Data conversion (HyLib → FOLIO)
│   │   ├── executions.py             # Migration task execution
│   │   ├── files.py                  # Source data file management
│   │   ├── folio_reference.py        # FOLIO reference data lookup
│   │   ├── health.py                 # Health check
│   │   ├── validation.py             # Post-migration validation
│   │   ├── deletion.py               # Record deletion from FOLIO
│   │   └── tasks.py                  # Task configuration
│   ├── services/                      # Business logic
│   │   ├── config_service.py         # migration_config.json generation
│   │   ├── conversion_service.py     # Data conversion orchestration
│   │   ├── deletion_service.py       # FOLIO record deletion
│   │   ├── execution_service.py      # folio_migration_tools runner
│   │   ├── folder_service.py         # Iteration folder management
│   │   ├── project_service.py        # Project directory setup
│   │   └── validation_service.py     # Record count & content validation
│   ├── db/                            # SQLAlchemy models + SQLite
│   ├── models/                        # Pydantic schemas
│   └── utils/
├── templates/                         # Jinja2 HTML templates
├── static/                            # CSS, JS assets
├── tools/                             # CLI migration utilities
│   ├── convert_hylib_feefines.py     # HyLib CSV → feefines.tsv
│   ├── convert_hylib_loans.py        # HyLib CSV → loans.tsv
│   ├── convert_hylib_requests.py     # HyLib CSV → requests.tsv
│   ├── extract_095_standard.py       # MARC 095 → holdings.tsv + items.tsv
│   ├── delete_holdings_by_instance.py # Delete Holdings/Items from FOLIO
│   └── folio_env.sh.example          # FOLIO env vars template
├── config/                            # Client mapping files (version controlled)
│   └── thu/mapping_files/            # THU locations, material types, etc.
├── deployment/                        # Nginx, systemd configs
└── docs/                              # Documentation
    ├── guides/                        # Step-by-step migration guides (zh-TW)
    ├── analysis/                      # Per-task technical analysis (API details)
    ├── issues/                        # folio_migration_tools known issues
    └── dev/                           # Development notes
```

## Reference Data (outside this repo)

Migration data and tools source code at `D:\FOLIO-FSE\`:
- `D:\FOLIO-FSE\clients\thu\` - THU migration data (downloaded from Linux)
- `D:\FOLIO-FSE\folio_migration_tools\` - folio_migration_tools source (v1.10.1)
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
- Page routes use `/clients/{client_code}/...` (return HTML)
- DB migrations handled via `_run_migrations()` in database.py (ALTER TABLE for SQLite)
- Credentials are encrypted at rest (Fernet encryption)
- Background tasks use FastAPI BackgroundTasks or threading
- FOLIO API client uses async httpx with token auth
- CLI tools in `tools/` have dual interface: `convert()` function (for service) + `main()` (for CLI)
- Service-API-Template pattern: `services/*.py` → `api/*.py` → `templates/*.html`

## folio_migration_tools Known Issues

- **HoldingsCsvTransformer**: Hardcoded `source_data/items/` path — must copy holdings.tsv there
- **RequestsMigrator**: `fulfilmentPreference` misspelled (missing 'l') — needs post-install patch
- **Re-transform**: Generates new UUIDs — must re-post after re-transform
- Details in `docs/issues/`
