# Feature Request: Add created/updated counts for Holdings/Items/Instances BatchPoster

## Summary

The `BatchPoster` task provides `created` and `updated` record counts for Users, but not for Holdings, Items, or Instances. This makes it difficult to determine whether records were newly created or updated during migration.

## Environment

- **folio_migration_tools version**: Latest
- **Python version**: 3.13
- **FOLIO release**: Sunflower

## Current Behavior

### Users BatchPoster (HTTP 200)

When posting Users, the log includes created/updated counts:

```
Posting successful! Total rows: 128 Total failed: 0 created: 0 updated: 128 in 1.5s Batch Size: 128 Request size: 50KB
```

The report also shows:
```
Measure | Count
--- | ---:
Users created | 0
Users updated | 128
```

### Holdings/Items/Instances BatchPoster (HTTP 201)

When posting Holdings, Items, or Instances, the log only shows totals:

```
Posting successful! Total rows: 65 Total failed: 0 in 1.7s Batch Size: 65 Request size: 26.84KB
```

The report shows:
```
Measure | Count
--- | ---:
Failed to post first time | 0
Records posted first time | 0
Records processed first time | 65
```

**Problem**: `Records posted first time | 0` is confusing when all 65 records succeeded. There's no way to know if records were created or updated.

## Root Cause Analysis

### Source Code Location

**File**: `src/folio_migration_tools/migration_tasks/batch_poster.py`

#### Users (HTTP 200 response) - Lines 720-756

```python
elif response.status_code == 200:
    json_report = json.loads(response.text)
    self.users_created += json_report.get("createdRecords", 0)
    self.users_updated += json_report.get("updatedRecords", 0)
    self.num_posted = self.users_updated + self.users_created
    # ...
    logging.info(
        "Posting successful! Total rows: %s Total failed: %s "
        "created: %s updated: %s in %ss Batch Size: %s Request size: %s "
        "Message from server: %s",
        num_records,
        self.num_failures,
        self.users_created,
        self.users_updated,
        # ...
    )
```

The `/user-import` API returns a JSON response containing `createdRecords` and `updatedRecords`.

#### Holdings/Items/Instances (HTTP 201 response) - Lines 707-719

```python
if response.status_code == 201:
    logging.info(
        "Posting successful! Total rows: %s Total failed: %s "
        "in %ss "
        "Batch Size: %s Request size: %s ",
        num_records,
        self.num_failures,
        response.elapsed.total_seconds(),
        len(batch),
        get_req_size(response),
    )
```

The batch synchronous APIs (e.g., `/holdings-storage/batch/synchronous`) return HTTP 201 with no response body containing created/updated counts.

## Expected Behavior

For all object types, the report should clearly indicate:
1. How many records were successfully processed
2. How many were newly created vs. updated (if determinable)
3. How many failed

## Suggested Solutions

### Option A: Pre-check existence before posting (Accurate but slow)

Before posting each batch, query FOLIO to check which record IDs already exist:

```python
def check_existing_ids(self, batch, query_endpoint):
    ids = [record.get("id") for record in batch]
    # Query FOLIO to find which IDs exist
    existing = set()
    for id in ids:
        response = self.folio_client.get(f"{query_endpoint}/{id}")
        if response.status_code == 200:
            existing.add(id)
    return existing
```

**Pros**: Accurate counts
**Cons**: Significantly increases API calls and execution time

### Option B: Track initial counts (Recommended)

Before and after posting, query the total count of records in FOLIO:

```python
# Before posting
initial_count = self.get_record_count(query_endpoint)

# After posting
final_count = self.get_record_count(query_endpoint)

# Calculate
newly_created = final_count - initial_count
updated = total_posted - newly_created - failed
```

**Pros**: Only 2 extra API calls per task
**Cons**: May be inaccurate if other processes modify records during migration

### Option C: Improve report clarity (Minimal change)

Change the report measure names to be clearer:

```
Current:
Records posted first time | 0        <- Confusing

Suggested:
Records successfully processed | 65  <- Clear
Records requiring retry | 0
Records failed | 0
```

### Option D: Request FOLIO API enhancement

Request that the batch synchronous APIs return created/updated counts similar to the user-import API:

```json
{
  "totalRecords": 65,
  "createdRecords": 65,
  "updatedRecords": 0,
  "failedRecords": 0
}
```

This would be the most comprehensive solution but requires changes to FOLIO core modules.

## Impact

- **Severity**: Low (cosmetic/informational)
- **Impact**: Migration operators cannot easily verify whether records were newly created or updated, which is useful for:
  - Validating migration expectations
  - Debugging duplicate record issues
  - Audit trail documentation

## Workaround

Currently, operators can manually query FOLIO before and after migration to determine created vs. updated counts:

```bash
# Before migration
curl -X GET "$OKAPI_URL/holdings-storage/holdings?limit=0" \
  -H "x-okapi-tenant: $TENANT" \
  -H "x-okapi-token: $TOKEN" | jq '.totalRecords'

# After migration
# Run the same query and compare counts
```

## Related Information

- The `Records posted first time` counter appears to track records that succeeded on the first POST attempt (vs. requiring a retry), not newly created records.
- This behavior is consistent across Holdings, Items, and Instances BatchPoster tasks.

---

**Reported by**: THU Migration Team
**Date**: 2026-02-10
