# MARC 095 欄位 Holdings/Items 轉檔流程指南

> 本文件說明當 MARC 書目檔內含 095 段別（嵌入式館藏/單冊資料）時，如何提取並轉檔匯入 FOLIO。

---

## 目錄

1. [適用情境](#適用情境)
2. [整體流程圖](#整體流程圖)
3. [095 欄位結構說明](#095-欄位結構說明)
4. [前置作業](#前置作業)
5. [Step 1: 準備 MARC 檔案](#step-1-準備-marc-檔案)
6. [Step 2: 建立 095 提取腳本](#step-2-建立-095-提取腳本)
7. [Step 3: 執行 095 提取](#step-3-執行-095-提取)
8. [Step 4: 準備 Mapping 檔案](#step-4-準備-mapping-檔案)
9. [Step 5: 準備 taskConfig](#step-5-準備-taskconfig)
10. [Step 6: 準備 Reference Data 對應檔](#step-6-準備-reference-data-對應檔)
11. [Step 7: 執行轉檔與匯入](#step-7-執行轉檔與匯入)
12. [檔案清單總覽](#檔案清單總覽)
13. [驗證與除錯](#驗證與除錯)
14. [附錄 A: 使用預設 Mapping 的簡化流程](#附錄-a使用預設-mapping-的簡化流程)
15. [附錄 B: THU 專案範例設定](#附錄-bthu-專案範例設定)

---

## 適用情境

本流程適用於以下情況：

- 來源系統只有一個 MARC 書目檔（ISO 2709 格式）
- 書目記錄中包含 095 欄位，內嵌館藏和單冊資訊
- 沒有獨立的 MFHD (MARC Holdings) 檔案
- 沒有獨立的 Items CSV/TSV 檔案

**典型的 095 欄位結構**：
```
095 $a 圖書館 $b 館藏位置 $c 條碼 $d 分類號 $e 著者號 $p 資料類型 $t 索書號類型 $y 年份 $z 完整索書號
```

---

## 整體流程圖

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MARC ISO 檔案 (含 095 段別)                               │
│                         bibs.mrc / bibs.iso                                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
        ┌───────────────────────────┴───────────────────────────┐
        │                                                       │
        ▼                                                       ▼
┌───────────────────────┐                         ┌───────────────────────┐
│  Step 1: 轉 Instances │                         │  Step 2: 提取 095     │
│  (BibsTransformer)    │                         │  (Python 腳本)        │
│                       │                         │                       │
│  輸入: bibs.mrc       │                         │  輸入: bibs.mrc       │
│  輸出: instances.json │                         │  輸出:                │
│                       │                         │    - holdings_095.tsv │
│  ※ tagsToDelete:095  │                         │    - items_095.tsv    │
└───────────────────────┘                         └───────────────────────┘
        │                                                       │
        ▼                                                       │
┌───────────────────────┐                                       │
│  Step 3: 匯入 FOLIO   │                                       │
│  (BatchPoster)        │                                       │
└───────────────────────┘                                       │
        │                                                       │
        │ ← ─ ─ ─ ─ ─ Instances 必須先存在 ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘
        ▼
┌───────────────────────┐
│  Step 4: 轉 Holdings  │
│  (HoldingsCsvTransformer)
│                       │
│  輸入: holdings_095.tsv
│  Mapping: holdings_mapping_095.json
│  輸出: holdings.json  │
└───────────────────────┘
        │
        ▼
┌───────────────────────┐
│  Step 5: 匯入 Holdings│
│  (BatchPoster)        │
└───────────────────────┘
        │
        ▼
┌───────────────────────┐
│  Step 6: 轉 Items     │
│  (ItemsTransformer)   │
│                       │
│  輸入: items_095.tsv  │
│  Mapping: item_mapping_095.json
│  輸出: items.json     │
└───────────────────────┘
        │
        ▼
┌───────────────────────┐
│  Step 7: 匯入 Items   │
│  (BatchPoster)        │
└───────────────────────┘
```

---

## 095 欄位結構說明

### 標準 095 子欄位定義

| 子欄位 | 內容 | 對應 FOLIO 欄位 | 說明 |
|:------:|------|-----------------|------|
| $a | 圖書館代碼 | - | 多館時使用 |
| $b | 館藏位置 | Holdings.permanentLocationId | 必要欄位 |
| $c | 條碼 | Item.barcode | 必要欄位 |
| $d | 分類號 | Holdings.callNumber (部分) | 組成索書號 |
| $e | 著者號 | Holdings.callNumber (部分) | 組成索書號 |
| $p | 資料類型 | Item.materialTypeId | 如 BOOK, DVD |
| $r | 價格 | - | 選用 |
| $s | 日期 | - | 選用 |
| $t | 索書號類型 | Holdings.callNumberTypeId | 如 DDC, LCC |
| $y | 年份 | Item.yearCaption | 出版年或複本年 |
| $z | 完整索書號 | Holdings.callNumber | 若有則直接使用 |

### 範例 MARC 記錄

```
001 00301888
245 10 $a 投資學 / $c 王大明著.
095    $b LB3F $c W228135 $d 332.6 $e L242 $p BOOK $t DDC $y 2000
095    $b LB4F $c W228136 $d 332.6 $e L242 $p BOOK $t DDC $y 2001
```

上述記錄會產生：
- 1 個 Instance
- 2 個 Holdings（不同位置）
- 2 個 Items（不同條碼）

---

## 前置作業

### 準備目錄結構

```bash
# 設定專案路徑變數
PROJECT=/folio/folio_migration_web/clients/[CLIENT_CODE]/iterations/[CLIENT_CODE]_migration

# 建立必要目錄
mkdir -p $PROJECT/source_data/instances
mkdir -p $PROJECT/source_data/holdings
mkdir -p $PROJECT/source_data/items
mkdir -p $PROJECT/mapping_files
mkdir -p $PROJECT/results
mkdir -p $PROJECT/logs
mkdir -p $PROJECT/scripts

# 確認目錄結構
tree $PROJECT
```

### 確認環境

```bash
# 進入專案目錄
cd $PROJECT

# 啟動虛擬環境
source .venv/bin/activate

# 確認 folio_migration_tools 已安裝
pip show folio_migration_tools

# 確認 pymarc 已安裝（用於 095 提取）
pip show pymarc || pip install pymarc
```

---

## Step 1: 準備 MARC 檔案

將 MARC ISO 檔案放到 `source_data/instances/` 目錄：

```bash
# 複製 MARC 檔案
cp /path/to/your/bibs.mrc $PROJECT/source_data/instances/

# 或使用符號連結（節省空間）
ln -s /path/to/your/bibs.mrc $PROJECT/source_data/instances/bibs.mrc

# 確認檔案
ls -la $PROJECT/source_data/instances/
```

---

## Step 2: 建立 095 提取腳本

建立 `$PROJECT/scripts/extract_095.py`：

```python
#!/usr/bin/env python3
"""
Extract 095 field from MARC records and generate Holdings/Items TSV files.

Usage:
    python extract_095.py input.mrc [holdings_output.tsv] [items_output.tsv]

Example:
    python extract_095.py source_data/instances/bibs.mrc
"""

import sys
import csv
from pathlib import Path

try:
    from pymarc import MARCReader
except ImportError:
    print("ERROR: pymarc not installed. Run: pip install pymarc")
    sys.exit(1)


def extract_095_data(marc_file):
    """Extract 095 field data from MARC file."""
    records_data = []
    record_count = 0
    records_with_095 = 0

    print(f"Reading MARC file: {marc_file}")

    with open(marc_file, 'rb') as f:
        reader = MARCReader(f)
        for record in reader:
            record_count += 1
            bib_id = record['001'].data if record['001'] else None
            if not bib_id:
                continue

            fields_095 = record.get_fields('095')
            if not fields_095:
                continue

            records_with_095 += 1

            for f095 in fields_095:
                data = {
                    'bib_id': bib_id.strip(),
                    'library': '',           # $a
                    'location': '',          # $b
                    'barcode': '',           # $c
                    'classification': '',    # $d
                    'cutter': '',            # $e
                    'material_type': '',     # $p
                    'price': '',             # $r
                    'date': '',              # $s
                    'call_number_type': '',  # $t
                    'year': '',              # $y
                    'full_call_number': '',  # $z
                }

                for subfield in f095:
                    code, value = subfield[0], subfield[1].strip()
                    if code == 'a':
                        data['library'] = value
                    elif code == 'b':
                        data['location'] = value
                    elif code == 'c':
                        data['barcode'] = value
                    elif code == 'd':
                        data['classification'] = value
                    elif code == 'e':
                        data['cutter'] = value
                    elif code == 'p':
                        data['material_type'] = value
                    elif code == 'r':
                        data['price'] = value
                    elif code == 's':
                        data['date'] = value
                    elif code == 't':
                        data['call_number_type'] = value
                    elif code == 'y':
                        data['year'] = value
                    elif code == 'z':
                        data['full_call_number'] = value

                # Build call number if not provided in $z
                if not data['full_call_number'] and data['classification']:
                    parts = [data['classification']]
                    if data['cutter']:
                        parts.append(data['cutter'])
                    if data['year']:
                        parts.append(data['year'])
                    data['full_call_number'] = ' '.join(parts)

                records_data.append(data)

    print(f"Total MARC records: {record_count}")
    print(f"Records with 095: {records_with_095}")
    print(f"Total 095 fields (items): {len(records_data)}")

    return records_data


def write_holdings_tsv(records_data, output_file):
    """Write holdings TSV file with deduplication."""
    fieldnames = ['bib_id', 'location', 'call_number', 'call_number_type']

    # Ensure output directory exists
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter='\t')
        writer.writeheader()

        # Deduplicate by bib_id + location + call_number
        seen = set()
        for data in records_data:
            key = (data['bib_id'], data['location'], data['full_call_number'])
            if key not in seen:
                seen.add(key)
                writer.writerow({
                    'bib_id': data['bib_id'],
                    'location': data['location'],
                    'call_number': data['full_call_number'],
                    'call_number_type': data['call_number_type'],
                })

    print(f"Holdings: {len(seen)} unique records -> {output_file}")
    return len(seen)


def write_items_tsv(records_data, output_file):
    """Write items TSV file."""
    fieldnames = ['bib_id', 'barcode', 'location', 'material_type', 'call_number', 'year']

    # Ensure output directory exists
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter='\t')
        writer.writeheader()

        for data in records_data:
            writer.writerow({
                'bib_id': data['bib_id'],
                'barcode': data['barcode'],
                'location': data['location'],
                'material_type': data['material_type'],
                'call_number': data['full_call_number'],
                'year': data['year'],
            })

    print(f"Items: {len(records_data)} records -> {output_file}")
    return len(records_data)


def show_sample(records_data, count=3):
    """Show sample records for verification."""
    print(f"\n{'='*60}")
    print(f"Sample data (first {count} records)")
    print('='*60)

    for i, data in enumerate(records_data[:count]):
        print(f"\nRecord {i+1}:")
        print(f"  BIB ID: {data['bib_id']}")
        print(f"  Location: {data['location']}")
        print(f"  Barcode: {data['barcode']}")
        print(f"  Call Number: {data['full_call_number']}")
        print(f"  Call Number Type: {data['call_number_type']}")
        print(f"  Material Type: {data['material_type']}")
        print(f"  Year: {data['year']}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_095.py input.mrc [holdings_output.tsv] [items_output.tsv]")
        print("\nExample:")
        print("  python extract_095.py source_data/instances/bibs.mrc")
        sys.exit(1)

    marc_file = sys.argv[1]

    # Determine output paths
    if len(sys.argv) >= 3:
        holdings_output = sys.argv[2]
    else:
        base_dir = Path(marc_file).parent.parent  # Go up from instances/
        holdings_output = base_dir / 'holdings' / 'holdings_from_095.tsv'

    if len(sys.argv) >= 4:
        items_output = sys.argv[3]
    else:
        base_dir = Path(marc_file).parent.parent
        items_output = base_dir / 'items' / 'items_from_095.tsv'

    # Extract data
    records_data = extract_095_data(marc_file)

    if not records_data:
        print("\nNo 095 fields found in the MARC file.")
        sys.exit(0)

    # Show sample
    show_sample(records_data)

    # Write output files
    print(f"\n{'='*60}")
    print("Writing output files")
    print('='*60)

    write_holdings_tsv(records_data, holdings_output)
    write_items_tsv(records_data, items_output)

    print("\nDone!")


if __name__ == '__main__':
    main()
```

### 設定腳本權限

```bash
chmod +x $PROJECT/scripts/extract_095.py
```

---

## Step 3: 執行 095 提取

```bash
cd $PROJECT
source .venv/bin/activate

# 執行提取腳本
python scripts/extract_095.py source_data/instances/bibs.mrc

# 預期輸出：
# Reading MARC file: source_data/instances/bibs.mrc
# Total MARC records: 1000
# Records with 095: 950
# Total 095 fields (items): 1200
# ...
# Holdings: 980 unique records -> source_data/holdings/holdings_from_095.tsv
# Items: 1200 records -> source_data/items/items_from_095.tsv
```

### 確認輸出檔案

```bash
# 檢視 Holdings TSV
echo "=== Holdings TSV ==="
head -5 source_data/holdings/holdings_from_095.tsv
wc -l source_data/holdings/holdings_from_095.tsv

# 檢視 Items TSV
echo "=== Items TSV ==="
head -5 source_data/items/items_from_095.tsv
wc -l source_data/items/items_from_095.tsv
```

---

## Step 4: 準備 Mapping 檔案

### holdings_mapping_095.json

建立 `$PROJECT/mapping_files/holdings_mapping_095.json`：

```json
{
  "data": [
    {
      "folio_field": "instanceId",
      "legacy_field": "bib_id",
      "value": "",
      "description": "Link to Instance via MARC 001 field"
    },
    {
      "folio_field": "legacyIdentifier",
      "legacy_field": "bib_id",
      "value": "",
      "description": "Legacy identifier for tracking"
    },
    {
      "folio_field": "formerIds[0]",
      "legacy_field": "bib_id",
      "value": "",
      "description": "Preserve bib_id as former ID"
    },
    {
      "folio_field": "permanentLocationId",
      "legacy_field": "location",
      "value": "",
      "description": "From 095$b - mapped via locations.tsv"
    },
    {
      "folio_field": "callNumber",
      "legacy_field": "call_number",
      "value": "",
      "description": "From 095$z or assembled from $d$e$y"
    },
    {
      "folio_field": "callNumberTypeId",
      "legacy_field": "call_number_type",
      "value": "",
      "description": "From 095$t - mapped via call_number_type_mapping.tsv"
    }
  ]
}
```

### item_mapping_095.json

建立 `$PROJECT/mapping_files/item_mapping_095.json`：

```json
{
  "data": [
    {
      "folio_field": "barcode",
      "legacy_field": "barcode",
      "value": "",
      "description": "From 095$c"
    },
    {
      "folio_field": "holdingsRecordId",
      "legacy_field": "bib_id",
      "value": "",
      "description": "Link to Holdings via holdingsMergeCriteria"
    },
    {
      "folio_field": "legacyIdentifier",
      "legacy_field": "barcode",
      "fallback_legacy_field": "bib_id",
      "value": "",
      "description": "Use barcode as primary identifier"
    },
    {
      "folio_field": "formerIds[0]",
      "legacy_field": "barcode",
      "value": "",
      "description": "Preserve barcode as former ID"
    },
    {
      "folio_field": "formerIds[1]",
      "legacy_field": "bib_id",
      "value": "",
      "description": "Preserve bib_id as second former ID"
    },
    {
      "folio_field": "materialTypeId",
      "legacy_field": "material_type",
      "value": "",
      "description": "From 095$p - mapped via material_types.tsv"
    },
    {
      "folio_field": "permanentLoanTypeId",
      "legacy_field": "loan_type",
      "value": "",
      "description": "Mapped via loan_types.tsv"
    },
    {
      "folio_field": "permanentLocationId",
      "legacy_field": "location",
      "value": "",
      "description": "From 095$b - mapped via locations.tsv"
    },
    {
      "folio_field": "itemLevelCallNumber",
      "legacy_field": "call_number",
      "value": "",
      "description": "Item-level call number"
    },
    {
      "folio_field": "yearCaption[0]",
      "legacy_field": "year",
      "value": "",
      "description": "From 095$y"
    },
    {
      "folio_field": "status.name",
      "legacy_field": "Not mapped",
      "value": "Available",
      "description": "Default item status"
    }
  ]
}
```

---

## Step 5: 準備 taskConfig

建立 `$PROJECT/mapping_files/taskConfig_095.json`：

```json
{
  "libraryInformation": {
    "tenantId": "YOUR_TENANT_ID",
    "okapiUrl": "https://YOUR_FOLIO_URL",
    "okapiUsername": "YOUR_USERNAME",
    "libraryName": "YOUR_LIBRARY_NAME",
    "logLevelDebug": false,
    "folioRelease": "sunflower",
    "multiFieldDelimiter": "<^>",
    "addTimeStampToFileNames": false,
    "failedPercentageThreshold": 25,
    "iterationIdentifier": "YOUR_ITERATION_ID"
  },
  "migrationTasks": [
    {
      "name": "bibs",
      "migrationTaskType": "BibsTransformer",
      "ilsFlavour": "tag001",
      "hridHandling": "default",
      "addAdministrativeNotesWithLegacyIds": true,
      "tagsToDelete": ["095", "949", "999"],
      "files": [
        {
          "file_name": "bibs.mrc",
          "suppressed": false
        }
      ]
    },
    {
      "name": "bibs_poster",
      "migrationTaskType": "BatchPoster",
      "objectType": "Instances",
      "batchSize": 250,
      "files": [
        {
          "file_name": "folio_instances_bibs.json"
        }
      ]
    },
    {
      "name": "bibs_srs_poster",
      "migrationTaskType": "BatchPoster",
      "objectType": "SRS",
      "batchSize": 250,
      "files": [
        {
          "file_name": "folio_srs_instances_bibs.json"
        }
      ]
    },
    {
      "name": "holdings_from_095",
      "migrationTaskType": "HoldingsCsvTransformer",
      "holdingsMapFileName": "holdings_mapping_095.json",
      "locationMapFileName": "locations.tsv",
      "callNumberTypeMapFileName": "call_number_type_mapping.tsv",
      "defaultCallNumberTypeName": "Dewey Decimal classification",
      "fallbackHoldingsTypeId": "03c9c400-b9e3-4a07-ac0e-05ab470233ed",
      "hridHandling": "default",
      "holdingsMergeCriteria": [
        "instanceId",
        "permanentLocationId",
        "callNumber"
      ],
      "files": [
        {
          "file_name": "holdings_from_095.tsv",
          "suppressed": false
        }
      ]
    },
    {
      "name": "holdings_poster",
      "migrationTaskType": "BatchPoster",
      "objectType": "Holdings",
      "batchSize": 500,
      "files": [
        {
          "file_name": "folio_holdings_holdings_from_095.json"
        }
      ]
    },
    {
      "name": "items_from_095",
      "migrationTaskType": "ItemsTransformer",
      "itemsMappingFileName": "item_mapping_095.json",
      "locationMapFileName": "locations.tsv",
      "materialTypesMapFileName": "material_types.tsv",
      "loanTypesMapFileName": "loan_types.tsv",
      "itemStatusesMapFileName": "item_statuses.tsv",
      "callNumberTypeMapFileName": "call_number_type_mapping.tsv",
      "defaultCallNumberTypeName": "Dewey Decimal classification",
      "defaultLoanTypeName": "Can circulate",
      "hridHandling": "default",
      "files": [
        {
          "file_name": "items_from_095.tsv"
        }
      ]
    },
    {
      "name": "items_poster",
      "migrationTaskType": "BatchPoster",
      "objectType": "Items",
      "batchSize": 500,
      "files": [
        {
          "file_name": "folio_items_items_from_095.json"
        }
      ]
    }
  ]
}
```

### taskConfig 關鍵參數說明

| 參數 | 說明 |
|------|------|
| `tagsToDelete: ["095"]` | 轉 Instance 時刪除 095 欄位（避免重複資料） |
| `holdingsMergeCriteria` | Holdings 合併條件：相同 Instance + Location + CallNumber = 同一 Holdings |
| `defaultCallNumberTypeName` | 預設索書號類型（當 095$t 無值時使用） |
| `defaultLoanTypeName` | 預設借閱類型（Items 必填欄位） |
| `fallbackHoldingsTypeId` | 預設 Holdings Type UUID |

---

## Step 6: 準備 Reference Data 對應檔

### locations.tsv

建立 `$PROJECT/mapping_files/locations.tsv`：

```tsv
folio_code	LOCATION
LB3F	LB3F
LB4F	LB4F
LB45	LB45
LBA	LBA
LBBS	LBBS
MAIN	MAIN
REF	REF
Migration	*
```

> **說明**：
> - 第一欄 `folio_code` 是 FOLIO 位置代碼（程式會比對 FOLIO 中 location 的 `code` 屬性）
> - 第二欄 `LOCATION` 是來源資料中的位置欄位值
> - `*` 放在第二欄作為通配符，未對應的值會使用該行的 `folio_code` 作為預設
> - **注意**：欄位名稱必須是 `folio_code`（不是 `folio_name` 或 `legacy_code`），否則工具會報錯

### material_types.tsv

建立 `$PROJECT/mapping_files/material_types.tsv`：

```tsv
folio_name	MATERIAL_TYPE
book	BOOK
dvd	DVD
sound recording	CD
video recording	VHS
serial	SERIAL
map	MAP
unspecified	*
```

### loan_types.tsv

建立 `$PROJECT/mapping_files/loan_types.tsv`：

```tsv
folio_name	LOAN_TYPE
Can circulate	CIR
Can circulate	CIRC
Cannot circulate	NOCIR
Cannot circulate	REF
Course reserves	RESERVE
Can circulate	*
```

### call_number_type_mapping.tsv

建立 `$PROJECT/mapping_files/call_number_type_mapping.tsv`：

```tsv
folio_name	CALL_NUMBER_TYPE
Dewey Decimal classification	DDC
Dewey Decimal classification	DEWEY
Library of Congress classification	LCC
Library of Congress classification	LC
National Library of Medicine classification	NLM
Superintendent of Documents classification	SUDOC
Other scheme	LOCAL
Dewey Decimal classification	*
```

### item_statuses.tsv

建立 `$PROJECT/mapping_files/item_statuses.tsv`：

```tsv
legacy_code	folio_name
AVAILABLE	Available
CHECKEDOUT	Checked out
MISSING	Missing
LOST	Declared lost
DAMAGED	Restricted
```

> **注意**：item_statuses.tsv 不允許 `*` 通配符。未匹配的狀態會自動使用 `Available` 作為預設值。

---

## Step 7: 執行轉檔與匯入

### 完整執行腳本

建立 `$PROJECT/scripts/run_095_migration.sh`：

```bash
#!/bin/bash
#
# 095 Holdings/Items Migration Script
#

set -e  # Exit on error

# Configuration
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TASK_CONFIG="mapping_files/taskConfig_095.json"

cd "$PROJECT_DIR"
source .venv/bin/activate

echo "=========================================="
echo "Starting 095 Migration"
echo "Project: $PROJECT_DIR"
echo "=========================================="

# Step 1: Transform Bibs
echo ""
echo ">>> Step 1: Transforming Bibs..."
python -m folio_migration_tools.migration_tasks.migration_task_base \
  --base_folder . \
  --task_config "$TASK_CONFIG" \
  --task_name bibs

# Step 2: Post Instances
echo ""
echo ">>> Step 2: Posting Instances to FOLIO..."
python -m folio_migration_tools.migration_tasks.migration_task_base \
  --base_folder . \
  --task_config "$TASK_CONFIG" \
  --task_name bibs_poster

# Step 3: Post SRS (Source Records)
echo ""
echo ">>> Step 3: Posting SRS records..."
python -m folio_migration_tools.migration_tasks.migration_task_base \
  --base_folder . \
  --task_config "$TASK_CONFIG" \
  --task_name bibs_srs_poster

# Step 4: Extract 095 (if not already done)
HOLDINGS_TSV="source_data/holdings/holdings_from_095.tsv"
if [ ! -f "$HOLDINGS_TSV" ]; then
  echo ""
  echo ">>> Step 4: Extracting 095 fields..."
  python scripts/extract_095.py source_data/instances/bibs.mrc
else
  echo ""
  echo ">>> Step 4: 095 files already exist, skipping extraction"
fi

# Step 5: Transform Holdings
echo ""
echo ">>> Step 5: Transforming Holdings..."
python -m folio_migration_tools.migration_tasks.migration_task_base \
  --base_folder . \
  --task_config "$TASK_CONFIG" \
  --task_name holdings_from_095

# Step 6: Post Holdings
echo ""
echo ">>> Step 6: Posting Holdings to FOLIO..."
python -m folio_migration_tools.migration_tasks.migration_task_base \
  --base_folder . \
  --task_config "$TASK_CONFIG" \
  --task_name holdings_poster

# Step 7: Transform Items
echo ""
echo ">>> Step 7: Transforming Items..."
python -m folio_migration_tools.migration_tasks.migration_task_base \
  --base_folder . \
  --task_config "$TASK_CONFIG" \
  --task_name items_from_095

# Step 8: Post Items
echo ""
echo ">>> Step 8: Posting Items to FOLIO..."
python -m folio_migration_tools.migration_tasks.migration_task_base \
  --base_folder . \
  --task_config "$TASK_CONFIG" \
  --task_name items_poster

echo ""
echo "=========================================="
echo "Migration Complete!"
echo "=========================================="
echo ""
echo "Check logs for details:"
echo "  ls -la logs/"
echo ""
echo "Verify in FOLIO:"
echo "  - Instances count"
echo "  - Holdings count"
echo "  - Items count"
```

### 設定腳本權限並執行

```bash
chmod +x $PROJECT/scripts/run_095_migration.sh

# 執行完整流程
./scripts/run_095_migration.sh
```

### 或逐步執行

```bash
cd $PROJECT
source .venv/bin/activate

# ========== 1. 轉檔 Bibs ==========
echo ">>> Transforming Bibs..."
python -m folio_migration_tools.migration_tasks.migration_task_base \
  --base_folder . \
  --task_config mapping_files/taskConfig_095.json \
  --task_name bibs

# ========== 2. 匯入 Instances ==========
echo ">>> Posting Instances..."
python -m folio_migration_tools.migration_tasks.migration_task_base \
  --base_folder . \
  --task_config mapping_files/taskConfig_095.json \
  --task_name bibs_poster

# ========== 3. 匯入 SRS ==========
echo ">>> Posting SRS..."
python -m folio_migration_tools.migration_tasks.migration_task_base \
  --base_folder . \
  --task_config mapping_files/taskConfig_095.json \
  --task_name bibs_srs_poster

# ========== 4. 提取 095 ==========
echo ">>> Extracting 095 fields..."
python scripts/extract_095.py source_data/instances/bibs.mrc

# ========== 5. 轉檔 Holdings ==========
echo ">>> Transforming Holdings..."
python -m folio_migration_tools.migration_tasks.migration_task_base \
  --base_folder . \
  --task_config mapping_files/taskConfig_095.json \
  --task_name holdings_from_095

# ========== 6. 匯入 Holdings ==========
echo ">>> Posting Holdings..."
python -m folio_migration_tools.migration_tasks.migration_task_base \
  --base_folder . \
  --task_config mapping_files/taskConfig_095.json \
  --task_name holdings_poster

# ========== 7. 轉檔 Items ==========
echo ">>> Transforming Items..."
python -m folio_migration_tools.migration_tasks.migration_task_base \
  --base_folder . \
  --task_config mapping_files/taskConfig_095.json \
  --task_name items_from_095

# ========== 8. 匯入 Items ==========
echo ">>> Posting Items..."
python -m folio_migration_tools.migration_tasks.migration_task_base \
  --base_folder . \
  --task_config mapping_files/taskConfig_095.json \
  --task_name items_poster
```

---

## 檔案清單總覽

```
$PROJECT/
├── .env                                  # FOLIO 帳密
├── .venv/                                # Python 虛擬環境
├── mapping_files/
│   ├── taskConfig_095.json               # 主任務設定檔
│   ├── holdings_mapping_095.json         # Holdings 欄位對應
│   ├── item_mapping_095.json             # Items 欄位對應
│   ├── locations.tsv                     # 位置對應
│   ├── material_types.tsv                # 資料類型對應
│   ├── loan_types.tsv                    # 借閱類型對應
│   ├── call_number_type_mapping.tsv      # 索書號類型對應
│   └── item_statuses.tsv                 # 館藏狀態對應
├── scripts/
│   ├── extract_095.py                    # 095 提取腳本
│   └── run_095_migration.sh              # 完整執行腳本
├── source_data/
│   ├── instances/
│   │   └── bibs.mrc                      # 原始 MARC 檔案
│   ├── holdings/
│   │   └── holdings_from_095.tsv         # 提取的 Holdings TSV
│   └── items/
│       └── items_from_095.tsv            # 提取的 Items TSV
├── results/
│   ├── folio_instances_bibs.json         # 轉檔後的 Instances
│   ├── folio_srs_instances_bibs.json     # 轉檔後的 SRS
│   ├── folio_holdings_holdings_from_095.json  # 轉檔後的 Holdings
│   └── folio_items_items_from_095.json   # 轉檔後的 Items
└── logs/
    ├── bibs_*.log
    ├── bibs_poster_*.log
    ├── holdings_from_095_*.log
    ├── holdings_poster_*.log
    ├── items_from_095_*.log
    └── items_poster_*.log
```

---

## 驗證與除錯

### 檢查 Log 檔案

```bash
# 查看最新的 log
ls -lt logs/ | head -10

# 檢視特定任務的 log
tail -100 logs/holdings_from_095_*.log
tail -100 logs/items_from_095_*.log

# 搜尋錯誤
grep -i error logs/*.log
grep -i failed logs/*.log
```

### 驗證 FOLIO 資料

```bash
# 設定變數（或從 .env 載入）
# export FOLIO_URL="https://okapi.example.com"
# export FOLIO_TENANT="your_tenant_id"
# export FOLIO_USER="admin_user"
# export FOLIO_PASSWORD="..."

# 取得 FOLIO token
export FOLIO_TOKEN=$(curl -s -X POST "${FOLIO_URL}/authn/login" \
  -H "Content-Type: application/json" \
  -H "x-okapi-tenant: ${FOLIO_TENANT}" \
  -d "{\"username\":\"${FOLIO_USER}\",\"password\":\"${FOLIO_PASSWORD}\"}" \
  -D - 2>/dev/null | grep -i "x-okapi-token" | tr -d '\r' | awk '{print $2}')

# 查詢 Instances 數量
curl -s -X GET "$FOLIO_URL/instance-storage/instances?limit=0" \
  -H "X-Okapi-Tenant: $FOLIO_TENANT" \
  -H "X-Okapi-Token: $FOLIO_TOKEN" | jq '.totalRecords'

# 查詢 Holdings 數量
curl -s -X GET "$FOLIO_URL/holdings-storage/holdings?limit=0" \
  -H "X-Okapi-Tenant: $FOLIO_TENANT" \
  -H "X-Okapi-Token: $FOLIO_TOKEN" | jq '.totalRecords'

# 查詢 Items 數量
curl -s -X GET "$FOLIO_URL/item-storage/items?limit=0" \
  -H "X-Okapi-Tenant: $FOLIO_TENANT" \
  -H "X-Okapi-Token: $FOLIO_TOKEN" | jq '.totalRecords'

# 查詢特定 Instance 的 Holdings
curl -s -X GET "$FOLIO_URL/holdings-storage/holdings?query=instanceId==$INSTANCE_UUID" \
  -H "X-Okapi-Tenant: $FOLIO_TENANT" \
  -H "X-Okapi-Token: $FOLIO_TOKEN" | jq '.holdingsRecords'

# 查詢特定 Holdings 的 Items
curl -s -X GET "$FOLIO_URL/item-storage/items?query=holdingsRecordId==$HOLDINGS_UUID" \
  -H "X-Okapi-Tenant: $FOLIO_TENANT" \
  -H "X-Okapi-Token: $FOLIO_TOKEN" | jq '.items'
```

### 常見問題

| 問題 | 可能原因 | 解決方案 |
|------|----------|----------|
| Holdings 找不到 Instance | bib_id 不存在或格式不符 | 檢查 001 欄位值，確認 Instances 已先匯入 |
| Items 找不到 Holdings | holdingsMergeCriteria 不匹配 | 確認 bib_id + location + call_number 組合正確 |
| Location 對應失敗 | locations.tsv 缺少該代碼 | 新增對應或使用 `*` 預設值 |
| Material Type 錯誤 | material_types.tsv 缺少對應 | 新增對應，確認 FOLIO 中存在該類型 |
| 條碼重複 | 來源資料有重複條碼 | 清理來源資料或修改提取邏輯 |

---

## 附錄 A：使用預設 Mapping 的簡化流程

如果希望使用預設的 `holdingsrecord_mapping.json` 和 `item_mapping.json`，可以使用 **標準版提取腳本**，它會輸出符合預設 mapping 欄位名稱的 TSV。

### 標準版提取腳本 (extract_095_standard.py)

腳本位置：`tools/extract_095_standard.py`

#### 與原版的差異

| 項目 | extract_095.py (原版) | extract_095_standard.py (標準版) |
|------|----------------------|--------------------------------|
| Holdings 欄位 | bib_id, location, call_number, call_number_type | HOLDINGS_ID, BIB_ID, LOCATION, CALL_NUMBER, NOTE |
| Items 欄位 | bib_id, barcode, location, material_type, call_number, year | ITEM_ID, BIB_ID, HOLDINGS_ID, BARCODE, LOCATION, MATERIAL_TYPE, LOAN_TYPE, CALL_NUMBER, COPY_NUMBER, YEAR, STATUS, NOTE |
| 輸出檔名 | holdings_from_095.tsv, items_from_095.tsv | holdings.tsv, items.tsv |
| 需要的 Mapping | 095 專用 mapping | **預設** mapping |
| 產生 HOLDINGS_ID | ❌ | ✅ (用於 Item 連結) |
| 產生 ITEM_ID | ❌ | ✅ |

#### 標準版腳本完整程式碼

> **注意**：以下為精簡版，完整最新版本請參考 `tools/extract_095_standard.py`。

```python
#!/usr/bin/env python3
"""
Extract 095 field from MARC records and generate Holdings/Items TSV files.

This version outputs column names that match the default folio_migration_web
mapping templates (holdingsrecord_mapping.json, item_mapping.json).

Usage:
    python extract_095_standard.py input.mrc [holdings_output.tsv] [items_output.tsv]

Output:
    - holdings.tsv (columns: HOLDINGS_ID, BIB_ID, LOCATION, CALL_NUMBER, CALL_NUMBER_TYPE, NOTE)
    - items.tsv (columns: ITEM_ID, BIB_ID, HOLDINGS_ID, BARCODE, LOCATION, ...)
"""

import sys
import csv
import re
from pathlib import Path

try:
    from pymarc import MARCReader
except ImportError:
    print("ERROR: pymarc not installed. Run: pip install pymarc")
    sys.exit(1)


def normalize_whitespace(text):
    """Normalize whitespace: collapse multiple spaces to single space and strip."""
    if not text:
        return ''
    return re.sub(r'\s+', ' ', text).strip()


def extract_095_data(marc_file):
    """Extract 095 field data from MARC file."""
    records_data = []
    record_count = 0
    records_with_095 = 0
    item_counter = 0

    with open(marc_file, 'rb') as f:
        reader = MARCReader(f)
        for record in reader:
            record_count += 1
            bib_id = record['001'].data.strip() if record['001'] else None
            if not bib_id:
                continue

            fields_095 = record.get_fields('095')
            if not fields_095:
                continue

            records_with_095 += 1

            for f095 in fields_095:
                item_counter += 1
                data = {
                    'bib_id': bib_id,
                    'library': '',           # $a
                    'location': '',          # $b
                    'barcode': '',           # $c
                    'classification': '',    # $d
                    'cutter': '',            # $e
                    'material_type': '',     # $p
                    'price': '',             # $r
                    'date': '',              # $s
                    'call_number_type': '',  # $t
                    'year': '',              # $y
                    'full_call_number': '',  # $z
                    'item_id': f"ITEM-{item_counter:08d}",
                }

                for subfield in f095:
                    code, value = subfield[0], normalize_whitespace(subfield[1])
                    if code == 'a':   data['library'] = value
                    elif code == 'b': data['location'] = value
                    elif code == 'c': data['barcode'] = value
                    elif code == 'd': data['classification'] = value
                    elif code == 'e': data['cutter'] = value
                    elif code == 'p': data['material_type'] = value
                    elif code == 'r': data['price'] = value
                    elif code == 's': data['date'] = value
                    elif code == 't': data['call_number_type'] = value
                    elif code == 'y': data['year'] = value
                    elif code == 'z': data['full_call_number'] = value

                # Build call number from $d + $e + $y (preferred)
                # Always prefer $d/$e over $z because some systems' $z may include
                # material type prefix (e.g. "BOOK 332.6 L242 2000")
                if data['classification']:
                    parts = [data['classification']]
                    if data['cutter']:
                        parts.append(data['cutter'])
                    if data['year']:
                        parts.append(data['year'])
                    data['full_call_number'] = ' '.join(parts)
                elif data['full_call_number'] and data['material_type']:
                    # Fallback: use $z but strip material type prefix if present
                    prefix = data['material_type'] + ' '
                    if data['full_call_number'].startswith(prefix):
                        data['full_call_number'] = data['full_call_number'][len(prefix):]

                # Use barcode as item_id if available
                if data['barcode']:
                    data['item_id'] = data['barcode']

                records_data.append(data)

    return records_data


def generate_holdings_id(bib_id, location, material_type, call_number):
    """Generate a unique holdings ID based on bib_id + location + material_type + call_number."""
    combined = f"{bib_id}-{location}-{material_type}_{call_number}"
    return combined.replace(' ', '_').replace('/', '-')


def write_holdings_tsv(records_data, output_file):
    """Write holdings TSV file with standard column names."""
    fieldnames = ['HOLDINGS_ID', 'BIB_ID', 'LOCATION', 'CALL_NUMBER', 'CALL_NUMBER_TYPE', 'NOTE']

    Path(output_file).parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter='\t')
        writer.writeheader()

        seen = {}
        for data in records_data:
            key = (data['bib_id'], data['location'], data['material_type'], data['full_call_number'])
            if key not in seen:
                holdings_id = generate_holdings_id(
                    data['bib_id'], data['location'],
                    data['material_type'], data['full_call_number']
                )
                seen[key] = holdings_id
                writer.writerow({
                    'HOLDINGS_ID': holdings_id,
                    'BIB_ID': data['bib_id'],
                    'LOCATION': data['location'],
                    'CALL_NUMBER': data['full_call_number'],
                    'CALL_NUMBER_TYPE': data['call_number_type'],
                    'NOTE': '',
                })

    return seen


def write_items_tsv(records_data, holdings_map, output_file):
    """Write items TSV file with standard column names."""
    fieldnames = [
        'ITEM_ID', 'BIB_ID', 'HOLDINGS_ID', 'BARCODE', 'LOCATION',
        'MATERIAL_TYPE', 'LOAN_TYPE', 'CALL_NUMBER', 'COPY_NUMBER',
        'YEAR', 'STATUS', 'NOTE'
    ]

    Path(output_file).parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter='\t')
        writer.writeheader()

        for data in records_data:
            key = (data['bib_id'], data['location'], data['material_type'], data['full_call_number'])
            holdings_id = holdings_map.get(key, '')

            writer.writerow({
                'ITEM_ID': data['item_id'],
                'BIB_ID': data['bib_id'],
                'HOLDINGS_ID': holdings_id,
                'BARCODE': data['barcode'],
                'LOCATION': data['location'],
                'MATERIAL_TYPE': data['material_type'],
                'LOAN_TYPE': '',
                'CALL_NUMBER': data['full_call_number'],
                'COPY_NUMBER': '',
                'YEAR': data['year'],
                'STATUS': 'Available',
                'NOTE': '',
            })
```

#### 使用標準版的簡化流程

```bash
cd $PROJECT
source .venv/bin/activate

# 1. 提取 095 (使用標準版腳本)
python scripts/extract_095_standard.py source_data/instances/bibs.mrc

# 輸出：
#   source_data/holdings/holdings.tsv
#   source_data/items/items.tsv

# 2. 使用預設 taskConfig 轉檔 Holdings
python -m folio_migration_tools.migration_tasks.migration_task_base \
  --base_folder . \
  --task_config mapping_files/migration_config.json \
  --task_name transform_holdings_csv

# 3. 匯入 Holdings
python -m folio_migration_tools.migration_tasks.migration_task_base \
  --base_folder . \
  --task_config mapping_files/migration_config.json \
  --task_name post_holdings_csv

# 4. 轉檔 Items
python -m folio_migration_tools.migration_tasks.migration_task_base \
  --base_folder . \
  --task_config mapping_files/migration_config.json \
  --task_name transform_items

# 5. 匯入 Items
python -m folio_migration_tools.migration_tasks.migration_task_base \
  --base_folder . \
  --task_config mapping_files/migration_config.json \
  --task_name post_items
```

#### 輸出範例

**holdings.tsv**:
```tsv
HOLDINGS_ID	BIB_ID	LOCATION	CALL_NUMBER	CALL_NUMBER_TYPE	NOTE
00301888-LB3F-BOOK_332.6_L242_2000	00301888	LB3F	332.6 L242 2000	DDC
00301889-LB4F-BOOK_658.4_S123_2001	00301889	LB4F	658.4 S123 2001	DDC
```

> **注意**：HOLDINGS_ID 格式為 `{bib_id}-{location}-{material_type}_{call_number}`，包含 material_type 以區分同一書目+位置+索書號但不同資料類型的館藏。

**items.tsv**:
```tsv
ITEM_ID	BIB_ID	HOLDINGS_ID	BARCODE	LOCATION	MATERIAL_TYPE	LOAN_TYPE	CALL_NUMBER	COPY_NUMBER	YEAR	STATUS	NOTE
W228135	00301888	00301888-LB3F-BOOK_332.6_L242_2000	W228135	LB3F	BOOK		332.6 L242 2000		2000	Available
W228136	00301889	00301889-LB4F-BOOK_658.4_S123_2001	W228136	LB4F	BOOK		658.4 S123 2001		2001	Available
```

#### 優點

1. **不需要額外的 mapping 檔案** - 使用預設的 `holdingsrecord_mapping.json` 和 `item_mapping.json`
2. **不需要額外的 taskConfig** - 使用預設的 `migration_config.json`
3. **Holdings 和 Items 自動連結** - 腳本會產生 `HOLDINGS_ID` 並在 Items 中引用
4. **統一管理** - 所有客戶專案使用相同的流程

---

## 附錄 B：THU 專案範例設定

以下是 THU 專案的實際設定值：

### taskConfig_095.json (THU)

```json
{
  "libraryInformation": {
    "tenantId": "your_tenant_id",
    "okapiUrl": "https://okapi.example.com",
    "okapiUsername": "EBSCOAdmin",
    "libraryName": "thu",
    "logLevelDebug": false,
    "folioRelease": "sunflower",
    "multiFieldDelimiter": "<^>",
    "addTimeStampToFileNames": false,
    "iterationIdentifier": "thu_migration"
  }
}
```

### locations.tsv (THU)

```tsv
folio_code	LOCATION
LB3F	LB3F
LB4F	LB4F
LB45	LB45
LBA	LBA
LBBS	LBBS
LBCA	LBCA
LBCD	LBCD
LBCH	LBCH
LM45	LM45
LM46	LM46
Migration	*
```

> **重要**：locations.tsv 的欄位標題必須是 `folio_code`（第一欄）和來源資料欄位名如 `LOCATION`（第二欄）。通配符 `*` 放在第二欄（來源值），對應的 `folio_code` 放在第一欄。

### material_types.tsv (THU)

```tsv
folio_name	MATERIAL_TYPE
book	BOOK
dvd	DVD
sound recording	CD
unspecified	*
```

---

*文件更新日期: 2026-02-23*
