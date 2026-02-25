# folio_migration_tools Issue Report: HoldingsCsvTransformer File Path

## Summary

`HoldingsCsvTransformer` looks for source data files in `source_data/items/` directory instead of the expected `source_data/holdings/` directory.

## Environment

- **folio_migration_tools version**: (check with `pip show folio-migration-tools`)
- **Python version**: 3.13
- **FOLIO release**: Sunflower
- **OS**: Rocky Linux 9

## Issue Description

When running the `HoldingsCsvTransformer` task, the tool searches for the `holdings.tsv` file in `source_data/items/` directory instead of `source_data/holdings/`.

### Expected Behavior

Based on the log output and the directory structure convention:
- `BibsTransformer` → `source_data/instances/`
- `HoldingsCsvTransformer` → `source_data/holdings/` (expected)
- `ItemsTransformer` → `source_data/items/`

The `HoldingsCsvTransformer` should look for files in `source_data/holdings/`.

### Actual Behavior

The `HoldingsCsvTransformer` looks for files in `source_data/items/`:

```
Files to process:
    /folio/folio_migration_web/clients/thu/iterations/thu_migration/source_data/items/holdings.tsv
```

## Steps to Reproduce

1. Create a migration project with standard directory structure:
   ```
   iterations/
   └── thu_migration/
       └── source_data/
           ├── holdings/
           │   └── holdings.tsv    ← File placed here
           └── items/
               └── items.tsv
   ```

2. Configure `transform_holdings_csv` task in `migration_config.json`:
   ```json
   {
       "name": "transform_holdings_csv",
       "migrationTaskType": "HoldingsCsvTransformer",
       "holdingsMapFileName": "holdingsrecord_mapping.json",
       "locationMapFileName": "locations.tsv",
       "callNumberTypeMapFileName": "call_number_type_mapping.tsv",
       "defaultCallNumberTypeName": "Library of Congress classification",
       "fallbackHoldingsTypeId": "03c9c400-b9e3-4a07-ac0e-05ab470233ed",
       "hridHandling": "default",
       "files": [
           {
               "file_name": "holdings.tsv"
           }
       ],
       "updateHridSettings": false
   }
   ```

3. Run the task.

4. Observe the error:
   ```
   CRITICAL    Critical Process issue. Check configuration, mapping files and reference data
   None of the files listed in task configuration found in
   /folio/folio_migration_web/clients/thu/iterations/thu_migration/source_data/items.
   Listed files: holdings.tsv
   ```

## Log Output

### Initial Log (showing expected path)
```
Source records files folder is /folio/.../source_data/holdings
```

### Error Log (showing actual search path)
```
CRITICAL    Critical Process issue. Check configuration, mapping files and reference data
None of the files listed in task configuration found in
/folio/folio_migration_web/clients/thu/iterations/thu_migration/source_data/items.
Listed files: holdings.tsv
```

### After Workaround (file copied to items/)
```
Files to process:
    /folio/.../source_data/items/holdings.tsv
Source data file contains 73 rows
processed 73 records in 1 files
All done!
```

## Workaround

Copy `holdings.tsv` to the `source_data/items/` directory:

```bash
cp source_data/holdings/holdings.tsv source_data/items/
```

## Root Cause Analysis

### Source Code Location

**File**: `src/folio_migration_tools/migration_tasks/holdings_csv_transformer.py`

The path `"items"` is **hardcoded** in two locations:

#### Location 1: Line 213-215 (in `__init__`)
```python
self.check_source_files(
    self.folder_structure.data_folder / "items", self.task_configuration.files
)
```

#### Location 2: Line 395 (in `process_single_file`)
```python
full_path = self.folder_structure.data_folder / "items" / file_def.file_name
```

### Why `legacy_records_folder` Should Be Used

The `FolderStructure` class (`folder_structure.py`, lines 70-76) already correctly calculates the source folder based on object type:

```python
def setup_migration_file_structure(self, source_file_type: str = ""):
    ...
    object_type_string = str(self.object_type.name).lower()  # = "holdings"
    if source_file_type:
        self.legacy_records_folder = self.data_folder / source_file_type
    elif self.object_type == FOLIONamespaces.other:
        self.legacy_records_folder = self.data_folder
    else:
        self.legacy_records_folder = self.data_folder / object_type_string
```

Since `HoldingsCsvTransformer.get_object_type()` returns `FOLIONamespaces.holdings`, the `legacy_records_folder` is correctly set to `source_data/holdings`.

### Comparison with Other Transformers

| Transformer | Code | Path Used |
|-------------|------|-----------|
| BibsTransformer | `self.folder_structure.legacy_records_folder` | ✅ Correct (`source_data/instances`) |
| ItemsTransformer | `self.folder_structure.legacy_records_folder` | ✅ Correct (`source_data/items`) |
| **HoldingsCsvTransformer** | `self.folder_structure.data_folder / "items"` | ❌ Hardcoded wrong path |

### Log vs Implementation Inconsistency

The log message at `folder_structure.py:59`:
```python
logging.info("Source records files folder is %s", self.legacy_records_folder)
```

This outputs the **correct** path (`source_data/holdings`), but `HoldingsCsvTransformer` ignores `legacy_records_folder` and uses the hardcoded `"items"` path instead.

## Suggested Fix

Replace the hardcoded `"items"` path with `legacy_records_folder` in both locations:

### Fix for Line 213-215:
```python
# Before (incorrect):
self.check_source_files(
    self.folder_structure.data_folder / "items", self.task_configuration.files
)

# After (correct):
self.check_source_files(
    self.folder_structure.legacy_records_folder, self.task_configuration.files
)
```

### Fix for Line 395:
```python
# Before (incorrect):
full_path = self.folder_structure.data_folder / "items" / file_def.file_name

# After (correct):
full_path = self.folder_structure.legacy_records_folder / file_def.file_name
```

This aligns `HoldingsCsvTransformer` with the pattern used by `BibsTransformer` and `ItemsTransformer`.

## Impact

- **Severity**: Medium
- **Impact**: Users must manually copy holdings files to the items directory, which is counter-intuitive and may cause confusion with actual item files.

## Related Information

- Task type: `HoldingsCsvTransformer`
- The `HoldingsMarcTransformer` may have the same issue (not verified)
- The `ItemsTransformer` correctly uses `source_data/items/`

## Additional Notes

The initial log message shows the correct path:
```
Source records files folder is /folio/.../source_data/holdings
```

But the actual file search occurs in a different directory, suggesting the log message and the actual implementation may be inconsistent.

---

**Reported by**: THU Migration Team
**Date**: 2026-02-09
