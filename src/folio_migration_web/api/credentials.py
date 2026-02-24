"""FOLIO credentials management API."""

import json
import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db.database import get_db
from ..db.models import Client as ClientModel
from ..models.client import ClientCredentials, ConnectionTestResult
from ..utils.encryption import get_credential_manager
from ..services.config_service import get_config_service

router = APIRouter(prefix="/api/clients/{client_code}/credentials", tags=["credentials"])
settings = get_settings()


@router.get("")
async def get_credentials_status(
    client_code: str,
    db: Session = Depends(get_db),
):
    """Check if credentials are set for a client."""
    client = db.query(ClientModel).filter(ClientModel.client_code == client_code).first()
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_code}' not found")

    # Decrypt username to show on the form (password is never returned)
    username = None
    if client.credentials_set and client.encrypted_username:
        try:
            manager = get_credential_manager()
            username = manager.decrypt(client.encrypted_username)
        except Exception:
            pass

    return {
        "client_code": client_code,
        "credentials_set": client.credentials_set,
        "has_username": bool(client.encrypted_username),
        "has_password": bool(client.encrypted_password),
        "username": username,  # Return decrypted username
    }


@router.post("")
async def set_credentials(
    client_code: str,
    credentials: ClientCredentials,
    db: Session = Depends(get_db),
):
    """Set FOLIO credentials for a client."""
    client = db.query(ClientModel).filter(ClientModel.client_code == client_code).first()
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_code}' not found")

    manager = get_credential_manager()

    # Always update username
    client.encrypted_username = manager.encrypt(credentials.username)

    # Only update password if provided
    if credentials.password:
        client.encrypted_password = manager.encrypt(credentials.password)
        password_to_save = credentials.password
    elif client.encrypted_password:
        # Keep existing password
        password_to_save = manager.decrypt(client.encrypted_password)
    else:
        raise HTTPException(status_code=400, detail="Password is required")

    client.credentials_set = True
    db.commit()

    # Also update .env file
    _update_env_file(client_code, credentials.username, password_to_save)

    # Update library_config.json with username
    _update_library_config_username(client_code, credentials.username)

    # Fetch reference data from FOLIO and update mapping files
    reference_data_updated = False
    try:
        config_service = get_config_service(settings.get_client_dir(client_code))
        reference_data = await config_service.fetch_folio_reference_data(
            client.folio_url,
            client.tenant_id,
            credentials.username,
            password_to_save,
        )
        if reference_data.get("holdings_note_type_id") or reference_data.get("item_note_type_id"):
            config_service.update_mapping_with_reference_data(reference_data)
            reference_data_updated = True
    except Exception:
        pass  # Silently fail - mapping files can be updated manually

    return {
        "status": "success",
        "message": "Credentials saved successfully",
        "reference_data_updated": reference_data_updated,
    }


@router.delete("")
async def clear_credentials(
    client_code: str,
    db: Session = Depends(get_db),
):
    """Clear FOLIO credentials for a client."""
    client = db.query(ClientModel).filter(ClientModel.client_code == client_code).first()
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_code}' not found")

    client.encrypted_username = None
    client.encrypted_password = None
    client.credentials_set = False

    db.commit()

    # Also clear .env file
    _update_env_file(client_code, "", "")

    return {
        "status": "success",
        "message": "Credentials cleared",
    }


@router.post("/test", response_model=ConnectionTestResult)
async def test_connection(
    client_code: str,
    credentials: ClientCredentials | None = None,
    db: Session = Depends(get_db),
):
    """
    Test FOLIO connection.

    If credentials are provided, uses those. Otherwise uses stored credentials.
    """
    client = db.query(ClientModel).filter(ClientModel.client_code == client_code).first()
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_code}' not found")

    # Get credentials
    if credentials:
        username = credentials.username
        password = credentials.password
    elif client.credentials_set:
        manager = get_credential_manager()
        username = manager.decrypt(client.encrypted_username)
        password = manager.decrypt(client.encrypted_password)
    else:
        raise HTTPException(
            status_code=400,
            detail="No credentials provided and none stored",
        )

    # Test connection to FOLIO
    try:
        result = await _test_folio_connection(
            client.folio_url,
            client.tenant_id,
            username,
            password,
        )
        return result
    except Exception as e:
        return ConnectionTestResult(
            success=False,
            message=f"Connection failed: {str(e)}",
        )


async def _test_folio_connection(
    folio_url: str,
    tenant_id: str,
    username: str,
    password: str,
) -> ConnectionTestResult:
    """Test connection to FOLIO by attempting to authenticate."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Try to authenticate
        auth_url = f"{folio_url}/authn/login"
        headers = {
            "Content-Type": "application/json",
            "x-okapi-tenant": tenant_id,
        }
        payload = {
            "username": username,
            "password": password,
        }

        try:
            response = await client.post(auth_url, json=payload, headers=headers)

            # FOLIO returns 201 (older) or 200 (newer) on successful auth
            # Check for token in header or body
            token = response.headers.get("x-okapi-token")

            # For newer FOLIO versions, token might be in response body
            if not token and response.status_code == 200:
                try:
                    body = response.json()
                    token = body.get("okapiToken") or body.get("accessToken")
                except Exception:
                    pass

            if response.status_code in (200, 201) and token:
                # Authentication successful
                # Try to get FOLIO version
                folio_version = None
                try:
                    version_headers = {
                        "x-okapi-tenant": tenant_id,
                        "x-okapi-token": token,
                    }
                    version_response = await client.get(
                        f"{folio_url}/_/version",
                        headers=version_headers,
                    )
                    if version_response.status_code == 200:
                        folio_version = version_response.text.strip()
                except Exception:
                    pass

                return ConnectionTestResult(
                    success=True,
                    message="Connection successful",
                    folio_version=folio_version,
                )
            elif response.status_code == 422:
                return ConnectionTestResult(
                    success=False,
                    message="Invalid username or password",
                )
            elif response.status_code == 400:
                return ConnectionTestResult(
                    success=False,
                    message="Invalid tenant ID or request format",
                )
            elif response.status_code in (200, 201):
                # Status OK but no token found
                return ConnectionTestResult(
                    success=False,
                    message="Authentication response missing token. Check credentials.",
                )
            else:
                return ConnectionTestResult(
                    success=False,
                    message=f"Authentication failed with status {response.status_code}",
                )

        except httpx.ConnectError:
            return ConnectionTestResult(
                success=False,
                message=f"Could not connect to {folio_url}",
            )
        except httpx.TimeoutException:
            return ConnectionTestResult(
                success=False,
                message="Connection timed out",
            )


@router.post("/refresh-reference-data")
async def refresh_reference_data(
    client_code: str,
    db: Session = Depends(get_db),
):
    """
    Fetch reference data from FOLIO and update mapping files.

    This includes holdings note type ID, item note type ID, etc.
    Requires credentials to be set.
    """
    client = db.query(ClientModel).filter(ClientModel.client_code == client_code).first()
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_code}' not found")

    if not client.credentials_set:
        raise HTTPException(status_code=400, detail="Credentials not set")

    manager = get_credential_manager()
    username = manager.decrypt(client.encrypted_username)
    password = manager.decrypt(client.encrypted_password)

    try:
        config_service = get_config_service(settings.get_client_dir(client_code))
        reference_data = await config_service.fetch_folio_reference_data(
            client.folio_url,
            client.tenant_id,
            username,
            password,
        )

        if not reference_data.get("holdings_note_type_id") and not reference_data.get("item_note_type_id"):
            return {
                "status": "warning",
                "message": "Could not fetch reference data from FOLIO",
                "reference_data": reference_data,
            }

        config_service.update_mapping_with_reference_data(reference_data)

        return {
            "status": "success",
            "message": "Reference data updated successfully",
            "reference_data": reference_data,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch reference data: {str(e)}")


# ============================================================
# SMTP Configuration
# ============================================================

smtp_router = APIRouter(prefix="/api/clients/{client_code}/smtp", tags=["smtp"])


async def _get_folio_token(client: ClientModel) -> tuple[str, str]:
    """Authenticate and get FOLIO token. Returns (token, error_message)."""
    if not client.credentials_set:
        raise HTTPException(status_code=400, detail="FOLIO credentials not set")

    manager = get_credential_manager()
    username = manager.decrypt(client.encrypted_username)
    password = manager.decrypt(client.encrypted_password)

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        auth_url = f"{client.folio_url}/authn/login"
        headers = {
            "Content-Type": "application/json",
            "x-okapi-tenant": client.tenant_id,
        }
        response = await http_client.post(
            auth_url, json={"username": username, "password": password}, headers=headers
        )
        if response.status_code not in (200, 201):
            raise HTTPException(status_code=502, detail="FOLIO authentication failed")

        token = response.headers.get("x-okapi-token")
        if not token:
            body = response.json()
            token = body.get("okapiToken") or body.get("accessToken")
        if not token:
            raise HTTPException(status_code=502, detail="Failed to obtain FOLIO token")

        return token


@smtp_router.get("")
async def get_smtp_status(
    client_code: str,
    db: Session = Depends(get_db),
):
    """Get SMTP configuration status from FOLIO."""
    client = db.query(ClientModel).filter(ClientModel.client_code == client_code).first()
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_code}' not found")

    token = await _get_folio_token(client)

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        headers = {
            "x-okapi-tenant": client.tenant_id,
            "x-okapi-token": token,
        }
        response = await http_client.get(
            f"{client.folio_url}/smtp-configuration", headers=headers
        )
        if response.status_code != 200:
            raise HTTPException(status_code=502, detail="Failed to query SMTP configuration")

        data = response.json()
        configs = data.get("smtpConfigurations", [])

        if not configs:
            return {"configured": False, "enabled": False, "host": None, "id": None}

        smtp = configs[0]
        host = smtp.get("host", "")
        is_enabled = "disabled" not in host.lower()

        return {
            "configured": True,
            "enabled": is_enabled,
            "host": host,
            "id": smtp.get("id"),
            "has_backup": bool(client.smtp_original_host),
        }


@smtp_router.post("/disable")
async def disable_smtp(
    client_code: str,
    db: Session = Depends(get_db),
):
    """Disable SMTP by setting host to 'disabled'. Backs up original host."""
    client = db.query(ClientModel).filter(ClientModel.client_code == client_code).first()
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_code}' not found")

    token = await _get_folio_token(client)

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        headers = {
            "x-okapi-tenant": client.tenant_id,
            "x-okapi-token": token,
            "Content-Type": "application/json",
        }

        # Get current SMTP config
        response = await http_client.get(
            f"{client.folio_url}/smtp-configuration", headers=headers
        )
        if response.status_code != 200:
            raise HTTPException(status_code=502, detail="Failed to query SMTP configuration")

        data = response.json()
        configs = data.get("smtpConfigurations", [])
        if not configs:
            raise HTTPException(status_code=404, detail="No SMTP configuration found in FOLIO")

        smtp = configs[0]
        smtp_id = smtp["id"]
        current_host = smtp.get("host", "")

        if "disabled" in current_host.lower():
            return {"status": "already_disabled", "message": "SMTP is already disabled"}

        # Backup original host
        client.smtp_original_host = current_host
        db.commit()

        # Update SMTP host to "disabled"
        smtp["host"] = "disabled"
        # Remove metadata (FOLIO doesn't accept it in PUT)
        smtp.pop("metadata", None)

        put_response = await http_client.put(
            f"{client.folio_url}/smtp-configuration/{smtp_id}",
            headers=headers,
            json=smtp,
        )
        if put_response.status_code not in (200, 204):
            raise HTTPException(
                status_code=502,
                detail=f"Failed to update SMTP: HTTP {put_response.status_code}"
            )

        return {
            "status": "success",
            "message": f"SMTP disabled. Original host '{current_host}' backed up.",
        }


@smtp_router.post("/enable")
async def enable_smtp(
    client_code: str,
    db: Session = Depends(get_db),
):
    """Restore SMTP by setting host back to the backed-up value."""
    client = db.query(ClientModel).filter(ClientModel.client_code == client_code).first()
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_code}' not found")

    if not client.smtp_original_host:
        raise HTTPException(
            status_code=400,
            detail="No backup host found. SMTP may not have been disabled via this portal."
        )

    token = await _get_folio_token(client)

    async with httpx.AsyncClient(timeout=30.0) as http_client:
        headers = {
            "x-okapi-tenant": client.tenant_id,
            "x-okapi-token": token,
            "Content-Type": "application/json",
        }

        # Get current SMTP config
        response = await http_client.get(
            f"{client.folio_url}/smtp-configuration", headers=headers
        )
        if response.status_code != 200:
            raise HTTPException(status_code=502, detail="Failed to query SMTP configuration")

        data = response.json()
        configs = data.get("smtpConfigurations", [])
        if not configs:
            raise HTTPException(status_code=404, detail="No SMTP configuration found in FOLIO")

        smtp = configs[0]
        smtp_id = smtp["id"]

        # Restore original host
        smtp["host"] = client.smtp_original_host
        smtp.pop("metadata", None)

        put_response = await http_client.put(
            f"{client.folio_url}/smtp-configuration/{smtp_id}",
            headers=headers,
            json=smtp,
        )
        if put_response.status_code not in (200, 204):
            raise HTTPException(
                status_code=502,
                detail=f"Failed to restore SMTP: HTTP {put_response.status_code}"
            )

        restored_host = client.smtp_original_host
        client.smtp_original_host = None
        db.commit()

        return {
            "status": "success",
            "message": f"SMTP restored to '{restored_host}'.",
        }


def _update_env_file(client_code: str, username: str, password: str):
    """Update the .env file with credentials."""
    client_path = settings.get_client_dir(client_code)
    env_path = client_path / ".env"

    if env_path.exists():
        content = env_path.read_text(encoding="utf-8")
        lines = content.split("\n")
        new_lines = []

        username_set = False
        password_set = False

        for line in lines:
            if line.startswith("USERNAME="):
                new_lines.append(f"USERNAME={username}")
                username_set = True
            elif line.startswith("PASSWORD="):
                new_lines.append(f"PASSWORD={password}")
                password_set = True
            else:
                new_lines.append(line)

        if not username_set:
            new_lines.append(f"USERNAME={username}")
        if not password_set:
            new_lines.append(f"PASSWORD={password}")

        env_path.write_text("\n".join(new_lines), encoding="utf-8")


def _update_library_config_username(client_code: str, username: str):
    """Update the library_config.json with the username."""
    client_path = settings.get_client_dir(client_code)
    config_path = client_path / "mapping_files" / "library_config.json"

    if not config_path.exists():
        return

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if "libraryInformation" in config:
            config["libraryInformation"]["okapiUsername"] = username
            config_path.write_text(
                json.dumps(config, indent=4, ensure_ascii=False),
                encoding="utf-8"
            )

            # Also update migration_config.json if it exists
            migration_config_path = client_path / "mapping_files" / "migration_config.json"
            if migration_config_path.exists():
                migration_config = json.loads(migration_config_path.read_text(encoding="utf-8"))
                if "libraryInformation" in migration_config:
                    migration_config["libraryInformation"]["okapiUsername"] = username
                    migration_config_path.write_text(
                        json.dumps(migration_config, indent=4, ensure_ascii=False),
                        encoding="utf-8"
                    )
    except Exception:
        pass  # Silently fail - config will work without username in some cases
