"""FOLIO credentials management API."""

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db.database import get_db
from ..db.models import Client as ClientModel
from ..models.client import ClientCredentials, ConnectionTestResult
from ..utils.encryption import get_credential_manager

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

    return {
        "client_code": client_code,
        "credentials_set": client.credentials_set,
        "has_username": bool(client.encrypted_username),
        "has_password": bool(client.encrypted_password),
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

    # Encrypt credentials
    manager = get_credential_manager()
    client.encrypted_username = manager.encrypt(credentials.username)
    client.encrypted_password = manager.encrypt(credentials.password)
    client.credentials_set = True

    db.commit()

    # Also update .env file
    _update_env_file(client_code, credentials.username, credentials.password)

    return {
        "status": "success",
        "message": "Credentials saved successfully",
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

            if response.status_code == 201:
                # Authentication successful
                # Try to get FOLIO version
                folio_version = None
                try:
                    token = response.headers.get("x-okapi-token")
                    if token:
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
