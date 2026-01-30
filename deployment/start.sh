#!/bin/bash
cd /folio/folio_migration_web
source .venv/bin/activate
exec uvicorn folio_migration_web.main:app --host 127.0.0.1 --port 8000 --workers 4 --log-level info
