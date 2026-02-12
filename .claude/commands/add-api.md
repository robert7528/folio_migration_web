Help me add a new API endpoint for: $ARGUMENTS

Follow the existing patterns in the project:
1. Create a new router file in `src/folio_migration_web/api/` if needed
2. Add Pydantic request/response models in `src/folio_migration_web/models/` if needed
3. Add service logic in `src/folio_migration_web/services/` if needed
4. Register the router in `src/folio_migration_web/main.py`
5. Use the `/api/clients/{client_code}/` prefix pattern

Reference existing routers for style and patterns.
