# FOLIO Migration Web Portal

Web application for managing FOLIO library migration projects.

## Features

- Create and manage client migration projects
- Configure FOLIO credentials with encrypted storage
- Upload source data files (MARC, CSV, JSON)
- Edit migration configuration and mapping files (JSON, TSV)
- FOLIO reference data UUID lookup (locations, material types, loan types, etc.)
- Execute migration tasks via folio_migration_tools
- Validate migration results (record-level comparison & count check)
- Delete migrated records from FOLIO (instances, holdings, items, users)
- Test FOLIO API connections

## Requirements

- Python 3.10+
- uv (recommended) or pip

## Quick Start

```bash
# Clone repository
cd /path/to/folio_migration_web

# Create virtual environment
uv venv .venv --python 3.13
source .venv/bin/activate  # Linux/macOS
# or: .venv\Scripts\activate  # Windows

# Install dependencies
uv pip install -e .

# Copy and configure environment
cp .env.example .env
nano .env

# Run development server
uvicorn folio_migration_web.main:app --reload
```

## Deployment

See `deployment/` directory for:
- `nginx.conf` - Nginx configuration
- `folio-migration-web.service` - systemd service file

## API Documentation

After starting the server, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Project Structure

```
folio_migration_web/
├── src/folio_migration_web/
│   ├── main.py           # FastAPI application
│   ├── config.py         # Configuration
│   ├── api/              # API routes
│   ├── models/           # Pydantic models
│   ├── services/         # Business logic
│   ├── db/               # Database layer
│   └── utils/            # Utilities
├── static/               # CSS, JavaScript
├── templates/            # HTML templates
├── deployment/           # Deployment configs
├── docs/                 # Migration documentation
├── tools/                # Migration utility scripts
│   ├── extract_095_standard.py      # Extract Holdings/Items from MARC 095
│   ├── delete_holdings_by_instance.py  # Delete Holdings/Items from FOLIO
│   ├── folio_task_analyzer.py       # Analyze migration task configs
│   └── get_thu_env.sh               # THU FOLIO environment setup
└── config/               # Client mapping files (version controlled)
    └── thu/mapping_files/  # THU locations, material types, etc.
```

## License

MIT
