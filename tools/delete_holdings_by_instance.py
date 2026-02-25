#!/usr/bin/env python3
"""
Delete all Holdings (and their Items) under specified FOLIO Instances.

Use this to clean up Holdings that were NOT created by the migration tool
(e.g., manually created or from other sources), which the Web Portal's
batch deletion cannot handle.

Usage:
    export FOLIO_URL="https://okapi.example.com"
    export FOLIO_TENANT="your_tenant_id"
    export FOLIO_USER="admin_user"
    export FOLIO_PASSWORD="password"

    python delete_holdings_by_instance.py instance_ids.txt

    # Or pipe instance UUIDs directly:
    python delete_holdings_by_instance.py --uuids uuid1 uuid2 uuid3 ...

Input file format (one per line, either format accepted):
    ["00301888", "5228ced7-e3db-51e4-8eae-fee1664e5965"]
    5228ced7-e3db-51e4-8eae-fee1664e5965
"""

import argparse
import json
import os
import re
import sys
import time

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed. Run: pip install httpx")
    sys.exit(1)


class FolioClient:
    """Simple synchronous FOLIO API client for deletion operations."""

    def __init__(self, base_url, tenant_id, token):
        self.base_url = base_url.rstrip("/")
        self.tenant_id = tenant_id
        self.headers = {
            "x-okapi-tenant": tenant_id,
            "x-okapi-token": token,
            "Content-Type": "application/json",
        }
        self.client = httpx.Client(timeout=30.0, headers=self.headers)

    @classmethod
    def login(cls, base_url, tenant_id, username, password):
        """Authenticate and return a FolioClient."""
        base_url = base_url.rstrip("/")
        headers = {
            "x-okapi-tenant": tenant_id,
            "Content-Type": "application/json",
        }
        resp = httpx.post(
            f"{base_url}/authn/login",
            json={"username": username, "password": password},
            headers=headers,
            timeout=30.0,
        )
        if resp.status_code not in (200, 201):
            print(f"ERROR: Login failed: {resp.status_code} {resp.text}")
            sys.exit(1)

        token = resp.headers.get("x-okapi-token")
        if not token:
            body = resp.json()
            token = body.get("okapiToken") or body.get("accessToken")
        if not token:
            print("ERROR: No token received")
            sys.exit(1)

        print(f"Authenticated as {username}")
        return cls(base_url, tenant_id, token)

    def get_holdings_for_instance(self, instance_id):
        """Get all holdings under an instance."""
        resp = self.client.get(
            f"{self.base_url}/holdings-storage/holdings",
            params={"query": f'instanceId=="{instance_id}"', "limit": 1000},
        )
        if resp.status_code == 200:
            return resp.json().get("holdingsRecords", [])
        print(f"  WARNING: Failed to query holdings: {resp.status_code}")
        return []

    def get_items_for_holdings(self, holdings_id):
        """Get all items under a holdings record."""
        resp = self.client.get(
            f"{self.base_url}/item-storage/items",
            params={"query": f'holdingsRecordId=="{holdings_id}"', "limit": 1000},
        )
        if resp.status_code == 200:
            return resp.json().get("items", [])
        return []

    def delete_item(self, item_id):
        """Delete a single item."""
        resp = self.client.delete(f"{self.base_url}/item-storage/items/{item_id}")
        return resp.status_code

    def delete_holdings(self, holdings_id):
        """Delete a single holdings record."""
        resp = self.client.delete(
            f"{self.base_url}/holdings-storage/holdings/{holdings_id}"
        )
        return resp.status_code

    def close(self):
        self.client.close()


def parse_instance_ids(source):
    """Parse instance UUIDs from file or list.

    Accepts lines like:
        ["00301888", "5228ced7-e3db-51e4-8eae-fee1664e5965"]
        5228ced7-e3db-51e4-8eae-fee1664e5965
    """
    uuid_pattern = re.compile(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I
    )
    uuids = []

    for line in source:
        line = line.strip()
        if not line:
            continue
        # Try to parse as JSON array first
        if line.startswith("["):
            try:
                arr = json.loads(line)
                # Second element is the UUID
                if len(arr) >= 2 and uuid_pattern.match(str(arr[1])):
                    uuids.append(str(arr[1]))
                    continue
            except json.JSONDecodeError:
                pass
        # Otherwise extract UUID from line
        match = uuid_pattern.search(line)
        if match:
            uuids.append(match.group())

    return uuids


def main():
    parser = argparse.ArgumentParser(
        description="Delete all Holdings (and Items) under specified FOLIO Instances."
    )
    parser.add_argument(
        "input_file",
        nargs="?",
        help="File with instance IDs (one per line)",
    )
    parser.add_argument(
        "--uuids",
        nargs="+",
        help="Instance UUIDs directly on command line",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be deleted without actually deleting",
    )
    args = parser.parse_args()

    # Get instance UUIDs
    if args.uuids:
        instance_ids = args.uuids
    elif args.input_file:
        with open(args.input_file, encoding="utf-8") as f:
            instance_ids = parse_instance_ids(f)
    else:
        print("Reading from stdin (paste lines, then Ctrl+D)...")
        instance_ids = parse_instance_ids(sys.stdin)

    if not instance_ids:
        print("ERROR: No instance UUIDs found")
        sys.exit(1)

    print(f"Found {len(instance_ids)} instance UUIDs")

    # Get FOLIO connection from environment
    folio_url = os.environ.get("FOLIO_URL")
    tenant = os.environ.get("FOLIO_TENANT")
    token = os.environ.get("FOLIO_TOKEN")

    if not folio_url or not tenant:
        print("ERROR: Set environment variables: FOLIO_URL, FOLIO_TENANT")
        print("  Auth option 1: FOLIO_TOKEN=<token>")
        print("  Auth option 2: FOLIO_USER=<user> FOLIO_PASSWORD=<pass>")
        sys.exit(1)

    if token:
        # Use token directly
        print(f"Using token for {folio_url}")
        client = FolioClient(folio_url, tenant, token)
    else:
        # Login with username/password
        username = os.environ.get("FOLIO_USER")
        password = os.environ.get("FOLIO_PASSWORD")
        if not username or not password:
            print("ERROR: Set FOLIO_TOKEN or both FOLIO_USER and FOLIO_PASSWORD")
            sys.exit(1)
        client = FolioClient.login(folio_url, tenant, username, password)

    # Process each instance
    total_holdings = 0
    total_items = 0
    deleted_holdings = 0
    deleted_items = 0
    failed = []

    try:
        for i, instance_id in enumerate(instance_ids, 1):
            print(f"\n[{i}/{len(instance_ids)}] Instance: {instance_id}")

            holdings = client.get_holdings_for_instance(instance_id)
            if not holdings:
                print("  No holdings found")
                continue

            print(f"  Found {len(holdings)} holdings")

            for h in holdings:
                h_id = h["id"]
                h_location = h.get("permanentLocationId", "?")
                h_callnum = h.get("callNumber", "")
                total_holdings += 1

                # First delete items under this holdings
                items = client.get_items_for_holdings(h_id)
                if items:
                    print(f"  Holdings {h_id[:8]}... ({h_callnum}): {len(items)} items")
                    for item in items:
                        total_items += 1
                        if args.dry_run:
                            print(f"    [DRY RUN] Would delete item {item['id'][:8]}...")
                            deleted_items += 1
                        else:
                            status = client.delete_item(item["id"])
                            if status == 204:
                                deleted_items += 1
                            else:
                                print(f"    FAILED to delete item {item['id'][:8]}...: HTTP {status}")
                                failed.append(("item", item["id"], status))

                # Then delete holdings
                if args.dry_run:
                    print(f"  [DRY RUN] Would delete holdings {h_id[:8]}... ({h_callnum})")
                    deleted_holdings += 1
                else:
                    status = client.delete_holdings(h_id)
                    if status == 204:
                        deleted_holdings += 1
                        print(f"  Deleted holdings {h_id[:8]}... ({h_callnum})")
                    else:
                        print(f"  FAILED to delete holdings {h_id[:8]}...: HTTP {status}")
                        failed.append(("holdings", h_id, status))

            # Small delay to avoid overwhelming the API
            time.sleep(0.1)

    finally:
        client.close()

    # Summary
    prefix = "[DRY RUN] " if args.dry_run else ""
    print(f"\n{'='*50}")
    print(f"{prefix}Summary:")
    print(f"  Instances processed: {len(instance_ids)}")
    print(f"  Holdings {prefix}deleted: {deleted_holdings}/{total_holdings}")
    print(f"  Items {prefix}deleted: {deleted_items}/{total_items}")
    if failed:
        print(f"  Failed: {len(failed)}")
        for rtype, rid, status in failed[:10]:
            print(f"    {rtype} {rid}: HTTP {status}")


if __name__ == "__main__":
    main()
