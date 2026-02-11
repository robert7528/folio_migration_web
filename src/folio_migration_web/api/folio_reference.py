"""FOLIO reference data lookup API."""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db.database import get_db
from ..db.models import Client as ClientModel
from ..services.validation_service import FolioApiClient
from ..utils.encryption import decrypt_value

router = APIRouter(
    prefix="/api/clients/{client_code}/folio/reference-data",
    tags=["folio-reference"],
)

# Supported reference data types and their FOLIO API endpoints
REFERENCE_TYPES = {
    "holdings-types": {
        "endpoint": "/holdings-types",
        "records_key": "holdingsTypes",
        "label": "Holdings Types",
    },
    "service-points": {
        "endpoint": "/service-points",
        "records_key": "servicepoints",
        "label": "Service Points",
    },
    "item-note-types": {
        "endpoint": "/item-note-types",
        "records_key": "itemNoteTypes",
        "label": "Item Note Types",
    },
    "address-types": {
        "endpoint": "/addresstypes",
        "records_key": "addressTypes",
        "label": "Address Types",
    },
    "note-types": {
        "endpoint": "/note-types",
        "records_key": "noteTypes",
        "label": "Note Types",
    },
    "material-types": {
        "endpoint": "/material-types",
        "records_key": "mtypes",
        "label": "Material Types",
    },
    "loan-types": {
        "endpoint": "/loan-types",
        "records_key": "loantypes",
        "label": "Loan Types",
    },
    "locations": {
        "endpoint": "/locations",
        "records_key": "locations",
        "label": "Locations",
    },
    "call-number-types": {
        "endpoint": "/call-number-types",
        "records_key": "callNumberTypes",
        "label": "Call Number Types",
    },
    "patron-groups": {
        "endpoint": "/groups",
        "records_key": "usergroups",
        "label": "Patron Groups",
    },
    "statistical-codes": {
        "endpoint": "/statistical-codes",
        "records_key": "statisticalCodes",
        "label": "Statistical Codes",
    },
}


class ReferenceDataItem(BaseModel):
    """A single reference data item."""
    id: str
    name: str
    source: str = ""
    code: str = ""


class ReferenceDataResponse(BaseModel):
    """Response for reference data lookup."""
    type: str
    label: str
    values: List[ReferenceDataItem]
    total: int


@router.get("/types")
async def list_reference_types():
    """List all available reference data types."""
    return {
        "types": [
            {"key": key, "label": info["label"]}
            for key, info in REFERENCE_TYPES.items()
        ]
    }


@router.get("/{ref_type}")
async def get_reference_data(
    client_code: str,
    ref_type: str,
    db: Session = Depends(get_db),
) -> ReferenceDataResponse:
    """Get reference data from FOLIO by type."""
    if ref_type not in REFERENCE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported reference type: {ref_type}. "
                   f"Available types: {', '.join(REFERENCE_TYPES.keys())}",
        )

    # Get client and credentials
    client = db.query(ClientModel).filter(
        ClientModel.client_code == client_code
    ).first()
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_code}' not found")

    if not client.credentials_set:
        raise HTTPException(status_code=400, detail="FOLIO credentials not configured")

    try:
        username = decrypt_value(client.encrypted_username)
        password = decrypt_value(client.encrypted_password)

        folio_client = await FolioApiClient.create(
            client.folio_url, client.tenant_id, username, password,
        )

        # Query FOLIO for reference data
        ref_config = REFERENCE_TYPES[ref_type]
        import httpx
        async with httpx.AsyncClient(timeout=30.0) as http_client:
            url = f"{folio_client.folio_url}{ref_config['endpoint']}?limit=1000"
            response = await http_client.get(url, headers=folio_client.headers)

            if response.status_code != 200:
                raise Exception(f"FOLIO API error: {response.status_code}")

            data = response.json()

        records = data.get(ref_config["records_key"], [])

        # Normalize to common format
        values = []
        for record in records:
            values.append(ReferenceDataItem(
                id=record.get("id", ""),
                name=record.get("name", record.get("desc", "")),
                source=record.get("source", ""),
                code=record.get("code", ""),
            ))

        # Sort by name
        values.sort(key=lambda v: v.name.lower())

        return ReferenceDataResponse(
            type=ref_type,
            label=ref_config["label"],
            values=values,
            total=len(values),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch reference data: {str(e)}",
        )
