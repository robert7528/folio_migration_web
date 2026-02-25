#!/bin/bash
#
# Source this script to set FOLIO environment variables for THU.
#
# Usage:
#   source tools/get_thu_env.sh
#   python tools/delete_holdings_by_instance.py /tmp/instance_ids.txt --dry-run
#
# Or with password on command line (non-interactive):
#   FOLIO_PASSWORD="xxx" source tools/get_thu_env.sh

export FOLIO_URL="https://okapi.example.com"
export FOLIO_TENANT="your_tenant_id"
FOLIO_USER="admin_user"

# Get password if not already set
if [ -z "$FOLIO_PASSWORD" ]; then
    read -s -p "FOLIO password for $FOLIO_USER: " FOLIO_PASSWORD
    echo
fi

# Get token
TOKEN=$(curl -s -X POST "${FOLIO_URL}/authn/login" \
    -H "Content-Type: application/json" \
    -H "x-okapi-tenant: ${FOLIO_TENANT}" \
    -d "{\"username\":\"${FOLIO_USER}\",\"password\":\"${FOLIO_PASSWORD}\"}" \
    -D - 2>/dev/null | grep -i "x-okapi-token" | tr -d '\r' | awk '{print $2}')

if [ -z "$TOKEN" ]; then
    # Try extracting from JSON body (newer FOLIO versions)
    TOKEN=$(curl -s -X POST "${FOLIO_URL}/authn/login" \
        -H "Content-Type: application/json" \
        -H "x-okapi-tenant: ${FOLIO_TENANT}" \
        -d "{\"username\":\"${FOLIO_USER}\",\"password\":\"${FOLIO_PASSWORD}\"}" \
        | python3 -c "import sys,json; print(json.load(sys.stdin).get('okapiToken',''))" 2>/dev/null)
fi

unset FOLIO_PASSWORD

if [ -n "$TOKEN" ]; then
    export FOLIO_TOKEN="$TOKEN"
    echo "✓ FOLIO_URL=$FOLIO_URL"
    echo "✓ FOLIO_TENANT=$FOLIO_TENANT"
    echo "✓ FOLIO_TOKEN=${TOKEN:0:20}..."
else
    echo "✗ Token 取得失敗，請確認密碼是否正確"
fi
