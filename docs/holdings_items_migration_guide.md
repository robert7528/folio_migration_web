# FOLIO Holdings 和 Items 轉檔匯入完整指南

> 本文件說明如何使用 folio_migration_tools 進行 Holdings 和 Items 的轉檔與匯入作業。

---

## 目錄

1. [整體架構概覽](#一整體架構概覽)
2. [Holdings 轉檔方式](#二holdings-轉檔方式)
3. [Holdings Mapping 欄位對應](#三holdings-mapping-欄位對應)
4. [Items 轉檔](#四items-轉檔)
5. [Items Mapping 欄位對應](#五items-mapping-欄位對應)
6. [必要的 Reference Data 對應檔案](#六必要的-reference-data-對應檔案)
7. [執行順序](#七執行順序)
8. [THU 095 轉檔的具體設定](#八thu-095-轉檔的具體設定)
9. [常見問題與解決](#九常見問題與解決)

---

## 一、整體架構概覽

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Migration Flow                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  [Bibs/Instances 轉檔匯入] ─────────────────────────────────────────────┐   │
│         ↓                                                               │   │
│  ┌──────────────────────────────────────────────────────────────────────┤   │
│  │                                                                      │   │
│  │  Holdings 來源 (二選一或並用)                                         │   │
│  │  ├── MARC (MFHD) ──→ HoldingsMarcTransformer                        │   │
│  │  └── TSV/CSV     ──→ HoldingsCsvTransformer                         │   │
│  │         ↓                                                            │   │
│  │  [Holdings BatchPoster] ─→ FOLIO                                     │   │
│  │                                                                      │   │
│  └──────────────────────────────────────────────────────────────────────┤   │
│         ↓                                                               │   │
│  ┌──────────────────────────────────────────────────────────────────────┤   │
│  │  Items 來源                                                          │   │
│  │  └── TSV/CSV     ──→ ItemsTransformer                               │   │
│  │         ↓                                                            │   │
│  │  [Items BatchPoster] ─→ FOLIO                                        │   │
│  └───────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 資料關聯圖

```
Instance (書目)
    │
    ├── Holdings (館藏) ──────────────────┐
    │       │                             │
    │       ├── Item (單冊) 1             │
    │       ├── Item (單冊) 2             │  同一個 Holdings 可有多個 Items
    │       └── Item (單冊) 3             │
    │                                     │
    ├── Holdings (另一館藏位置) ───────────┘
    │       │
    │       └── Item (單冊)
    │
    └── (一個 Instance 可有多個 Holdings)
```

---

## 二、Holdings 轉檔方式

### 方式 A：HoldingsMarcTransformer (從 MARC MFHD)

**適用情境**：來源系統有獨立的 MFHD (MARC Holdings) 檔案

**TaskConfig 設定**：

```json
{
  "name": "transform_mfhd",
  "legacyIdMarcPath": "001",
  "migrationTaskType": "HoldingsMarcTransformer",
  "locationMapFileName": "locations.tsv",
  "defaultCallNumberTypeName": "Library of Congress classification",
  "fallbackHoldingsTypeId": "03c9c400-b9e3-4a07-ac0e-05ab470233ed",
  "hridHandling": "preserve001",
  "createSourceRecords": true,
  "files": [
    {
      "file_name": "holding.mrc",
      "discovery_suppressed": false
    }
  ],
  "boundwithRelationshipFilePath": "voyager_bound_with_export.tsv",
  "holdingsTypeUuidForBoundwiths": "072cf64f-1fbe-4bb4-bdee-2d72453aefad"
}
```

**關鍵參數說明**：

| 參數 | 說明 |
|------|------|
| `legacyIdMarcPath` | MARC 中的 Legacy ID 欄位路徑（通常是 001） |
| `createSourceRecords` | 是否建立 SRS 記錄（保留原始 MARC） |
| `boundwithRelationshipFilePath` | Bound-with 關係檔案（一個 Holdings 對應多個 Bibs） |
| `holdingsTypeUuidForBoundwiths` | Bound-with 的 Holdings Type UUID |
| `fallbackHoldingsTypeId` | 預設的 Holdings Type UUID |
| `hridHandling` | HRID 處理方式：`preserve001` 保留原值，`default` 由系統產生 |

---

### 方式 B：HoldingsCsvTransformer (從 TSV/CSV)

**適用情境**：Holdings 資料來自 TSV/CSV 或從 MARC 095 等嵌入欄位提取

**TaskConfig 設定**：

```json
{
  "name": "transform_csv_holdings",
  "migrationTaskType": "HoldingsCsvTransformer",
  "holdingsMapFileName": "holdingsrecord_mapping.json",
  "locationMapFileName": "locations.tsv",
  "defaultCallNumberTypeName": "Library of Congress classification",
  "callNumberTypeMapFileName": "call_number_type_mapping.tsv",
  "holdingsTypeUuidForBoundwiths": "072cf64f-1fbe-4bb4-bdee-2d72453aefad",
  "previouslyGeneratedHoldingsFiles": [
    "folio_holdings_transform_mfhd.json"
  ],
  "holdingsMergeCriteria": [
    "instanceId",
    "permanentLocationId",
    "callNumber"
  ],
  "fallbackHoldingsTypeId": "03c9c400-b9e3-4a07-ac0e-05ab470233ed",
  "hridHandling": "default",
  "files": [
    {
      "file_name": "csv_items.tsv"
    }
  ]
}
```

**關鍵參數說明**：

| 參數 | 說明 |
|------|------|
| `holdingsMapFileName` | Holdings 欄位對應檔 (JSON) |
| `previouslyGeneratedHoldingsFiles` | 已轉檔的 Holdings JSON（用於合併避免重複） |
| `holdingsMergeCriteria` | Holdings 合併條件（相同條件 = 同一個 Holdings） |
| `fallbackHoldingsTypeId` | 預設 Holdings Type UUID |
| `callNumberTypeMapFileName` | 索書號類型對應檔 |

### holdingsMergeCriteria 說明

當多筆資料符合相同的合併條件時，會被視為同一個 Holdings：

```
條件組合: instanceId + permanentLocationId + callNumber

範例:
  Record 1: bib_id=001, location=LB3F, callNumber=PQ6353.M35
  Record 2: bib_id=001, location=LB3F, callNumber=PQ6353.M35
  → 合併為同一個 Holdings

  Record 3: bib_id=001, location=LB4F, callNumber=PQ6353.M35
  → 不同 location，建立新的 Holdings
```

---

## 三、Holdings Mapping 欄位對應

### 完整欄位對應表

| FOLIO 欄位 | 說明 | 必填 | 範例 legacy_field |
|------------|------|:----:|------------------|
| `instanceId` | 連結到 Instance | **是** | `fake_instance_id`, `bib_id`, `RECORD #(BIBLIO)` |
| `permanentLocationId` | 永久位置 | **是** | `PERM_LOCATION`, `location`, `LOCATION` |
| `legacyIdentifier` | Legacy ID（用於追蹤） | 否 | `Z30_REC_KEY`, `bib_id` |
| `callNumber` | 索書號 | 否 | `CALL #(BIBLIO)`, `call_number` |
| `callNumberPrefix` | 索書號前綴 | 否 | |
| `callNumberSuffix` | 索書號後綴 | 否 | |
| `callNumberTypeId` | 索書號類型 | 否 | 透過 mapping TSV 對應 |
| `copyNumber` | 複本號 | 否 | |
| `formerIds[0]` | 舊系統 ID | 否 | `Z30_REC_KEY`, `bib_id` |
| `holdingsTypeId` | Holdings 類型 | 否 | 使用 fallbackHoldingsTypeId |
| `notes[0].note` | 備註內容 | 否 | `holdings_note`, `VOLUME` |
| `notes[0].holdingsNoteTypeId` | 備註類型 UUID | 否 | 直接填入 UUID |
| `notes[0].staffOnly` | 僅員工可見 | 否 | `true` / `false` |
| `holdingsStatements[0].statement` | 館藏聲明 | 否 | `holdings_stmt` |
| `temporaryLocationId` | 臨時位置 | 否 | |
| `discoverySuppress` | 是否隱藏 | 否 | `true` / `false` |

### 範例 Holdings Mapping (095 提取用)

```json
{
  "data": [
    {
      "folio_field": "instanceId",
      "legacy_field": "bib_id",
      "value": "",
      "description": "連結到 Instance (透過 001 欄位)"
    },
    {
      "folio_field": "legacyIdentifier",
      "legacy_field": "bib_id",
      "fallback_legacy_field": "",
      "value": "",
      "description": "Legacy ID for tracking"
    },
    {
      "folio_field": "formerIds[0]",
      "legacy_field": "bib_id",
      "value": "",
      "description": "Former ID"
    },
    {
      "folio_field": "permanentLocationId",
      "legacy_field": "location",
      "value": "",
      "description": "從 095$b 取得"
    },
    {
      "folio_field": "callNumber",
      "legacy_field": "call_number",
      "value": "",
      "description": "從 095$z 或組合 $d$e$y"
    },
    {
      "folio_field": "callNumberTypeId",
      "legacy_field": "call_number_type",
      "value": "",
      "description": "從 095$t 取得 (DDC, LCC 等)"
    }
  ]
}
```

### 範例 Holdings Mapping (csv_items.tsv 用)

```json
{
  "data": [
    {
      "folio_field": "legacyIdentifier",
      "legacy_field": "Z30_REC_KEY",
      "value": ""
    },
    {
      "folio_field": "formerIds[0]",
      "legacy_field": "Z30_REC_KEY",
      "value": ""
    },
    {
      "folio_field": "instanceId",
      "legacy_field": "fake_instance_id",
      "value": ""
    },
    {
      "folio_field": "permanentLocationId",
      "legacy_field": "PERM_LOCATION",
      "value": ""
    },
    {
      "folio_field": "holdingsStatements[0].statement",
      "legacy_field": "holdings_stmt",
      "value": ""
    },
    {
      "folio_field": "notes[0].holdingsNoteTypeId",
      "legacy_field": "holdings_note",
      "value": "f453de0f-8b54-4e99-9180-52932529e3a6"
    },
    {
      "folio_field": "notes[0].note",
      "legacy_field": "holdings_note",
      "value": ""
    },
    {
      "folio_field": "notes[0].staffOnly",
      "legacy_field": "holdings_note",
      "value": true
    }
  ]
}
```

---

## 四、Items 轉檔

### TaskConfig 設定

```json
{
  "name": "transform_csv_items",
  "migrationTaskType": "ItemsTransformer",
  "locationMapFileName": "locations.tsv",
  "itemsMappingFileName": "item_mapping_for_csv_items.json",
  "defaultCallNumberTypeName": "Library of Congress classification",
  "callNumberTypeMapFileName": "call_number_type_mapping.tsv",
  "materialTypesMapFileName": "material_types_csv.tsv",
  "loanTypesMapFileName": "loan_types_csv.tsv",
  "itemStatusesMapFileName": "item_statuses.tsv",
  "statisticalCodesMapFileName": "statcodes.tsv",
  "fallbackHoldingsTypeId": "03c9c400-b9e3-4a07-ac0e-05ab470233ed",
  "hridHandling": "default",
  "files": [
    {
      "file_name": "csv_items.tsv"
    }
  ],
  "boundwithRelationshipFilePath": "voyager_bound_with_export.tsv"
}
```

### 關鍵參數說明

| 參數 | 說明 | 必填 |
|------|------|:----:|
| `itemsMappingFileName` | Item 欄位對應檔 (JSON) | 是 |
| `materialTypesMapFileName` | 資料類型對應 (legacy → FOLIO) | 是 |
| `loanTypesMapFileName` | 借閱類型對應 | 是 |
| `itemStatusesMapFileName` | 館藏狀態對應 | 否 |
| `locationMapFileName` | 位置對應（Item 層級位置用） | 否 |
| `statisticalCodesMapFileName` | 統計代碼對應 | 否 |
| `callNumberTypeMapFileName` | 索書號類型對應 | 否 |
| `boundwithRelationshipFilePath` | Bound-with 關係檔 | 否 |
| `defaultLoanTypeName` | 預設借閱類型名稱 | 否 |

---

## 五、Items Mapping 欄位對應

### 完整欄位對應表

| FOLIO 欄位 | 說明 | 必填 | 範例 legacy_field |
|------------|------|:----:|------------------|
| `holdingsRecordId` | 連結到 Holdings | **是** | `fake_instance_id`, `MFHD_ID`, `bib_id` |
| `barcode` | 條碼 | 否 | `Z30_BARCODE`, `ITEM_BARCODE`, `barcode` |
| `legacyIdentifier` | Legacy ID | 否 | `Z30_REC_KEY`, `ITEM_ID` |
| `materialTypeId` | 資料類型 | **是** | `Z30_MATERIAL`, `material_type` |
| `permanentLoanTypeId` | 借閱類型 | **是** | `Z30_MATERIAL`, `I TYPE` |
| `status.name` | 館藏狀態 | 否 | 預設 `Available` |
| `copyNumber` | 複本號 | 否 | `Z30_COPY_ID`, `COPY_NUMBER` |
| `enumeration` | 編號 | 否 | `Z30_ENUMERATION_A`, `ITEM_ENUM` |
| `chronology` | 年代 | 否 | `Z30_CHRONOLOGICAL_I`, `CHRON` |
| `yearCaption[0]` | 年份標題 | 否 | `year`, `YEAR` |
| `volume` | 卷號 | 否 | `VOLUME` |
| `itemLevelCallNumber` | Item 層級索書號 | 否 | `Z30_CALL_NO_2`, `call_number` |
| `permanentLocationId` | Item 永久位置 | 否 | 通常繼承自 Holdings |
| `temporaryLocationId` | Item 臨時位置 | 否 | |
| `notes[0].note` | 備註 | 否 | `Z30_NOTE_OPAC`, `FREETEXT` |
| `notes[0].itemNoteTypeId` | 備註類型 UUID | 否 | 直接填入 UUID |
| `notes[0].staffOnly` | 僅員工可見 | 否 | `true` / `false` |
| `formerIds[0]` | 舊系統 ID | 否 | `ITEM_ID` |
| `hrid` | HRID | 否 | 可用 `Z30_REC_KEY` |
| `accessionNumber` | 登錄號 | 否 | |
| `numberOfPieces` | 件數 | 否 | `PIECES` |
| `descriptionOfPieces` | 件數描述 | 否 | `PIECES` |

### Item 與 Holdings 的連結機制

```
┌─────────────────────────────────────────────────────────────────┐
│ Item.holdingsRecordId                                           │
│         │                                                       │
│         ▼                                                       │
│ 尋找對應的 Holdings:                                             │
│                                                                 │
│ 方式 1: 直接對應 (MFHD_ID)                                       │
│   Item.holdingsRecordId = "46361520"                            │
│   Holdings.legacyIdentifier = "46361520"                        │
│   → 直接匹配                                                    │
│                                                                 │
│ 方式 2: 透過 holdingsMergeCriteria                               │
│   Item: bib_id=001, location=LB3F, call_number=PQ6353           │
│   Holdings: instanceId=001, permanentLocationId=LB3F,           │
│             callNumber=PQ6353                                   │
│   → 條件匹配，自動連結                                           │
└─────────────────────────────────────────────────────────────────┘
```

### 範例 Item Mapping (095 提取用)

```json
{
  "data": [
    {
      "folio_field": "barcode",
      "legacy_field": "barcode",
      "value": "",
      "description": "從 095$c 取得"
    },
    {
      "folio_field": "holdingsRecordId",
      "legacy_field": "bib_id",
      "value": "",
      "description": "透過 bib_id + location + call_number 連結"
    },
    {
      "folio_field": "legacyIdentifier",
      "legacy_field": "barcode",
      "fallback_legacy_field": "bib_id",
      "value": ""
    },
    {
      "folio_field": "materialTypeId",
      "legacy_field": "material_type",
      "value": "",
      "description": "從 095$p 取得"
    },
    {
      "folio_field": "permanentLoanTypeId",
      "legacy_field": "loan_type",
      "value": "",
      "description": "透過 loan_types.tsv 映射"
    },
    {
      "folio_field": "permanentLocationId",
      "legacy_field": "location",
      "value": "",
      "description": "從 095$b 取得"
    },
    {
      "folio_field": "itemLevelCallNumber",
      "legacy_field": "call_number",
      "value": ""
    },
    {
      "folio_field": "yearCaption[0]",
      "legacy_field": "year",
      "value": "",
      "description": "從 095$y 取得"
    },
    {
      "folio_field": "status.name",
      "legacy_field": "Not mapped",
      "value": "Available",
      "description": "預設狀態"
    }
  ]
}
```

### 範例 Item Mapping (MFHD attached items)

```json
{
  "data": [
    {
      "folio_field": "barcode",
      "legacy_field": "ITEM_BARCODE",
      "value": ""
    },
    {
      "folio_field": "legacyIdentifier",
      "legacy_field": "ITEM_ID",
      "value": ""
    },
    {
      "folio_field": "holdingsRecordId",
      "legacy_field": "MFHD_ID",
      "value": ""
    },
    {
      "folio_field": "materialTypeId",
      "legacy_field": "ITEM_TYPE_ID",
      "value": ""
    },
    {
      "folio_field": "permanentLoanTypeId",
      "legacy_field": "ITEM_TYPE_ID",
      "value": ""
    },
    {
      "folio_field": "copyNumber",
      "legacy_field": "COPY_NUMBER",
      "value": ""
    },
    {
      "folio_field": "enumeration",
      "legacy_field": "ITEM_ENUM",
      "value": ""
    },
    {
      "folio_field": "chronology",
      "legacy_field": "CHRON",
      "value": ""
    },
    {
      "folio_field": "yearCaption[0]",
      "legacy_field": "YEAR",
      "value": ""
    },
    {
      "folio_field": "notes[0].itemNoteTypeId",
      "legacy_field": "FREETEXT",
      "value": "5a15e0f8-2802-4cbf-a4de-8f0dedd3ed3a"
    },
    {
      "folio_field": "notes[0].note",
      "legacy_field": "FREETEXT",
      "value": ""
    },
    {
      "folio_field": "notes[0].staffOnly",
      "legacy_field": "FREETEXT",
      "value": false
    }
  ]
}
```

---

## 六、必要的 Reference Data 對應檔案

### 1. locations.tsv

位置代碼對應，將來源系統的位置代碼轉換為 FOLIO 位置代碼。

```tsv
folio_code	LOCATION
LB3F	LB3F
LB4F	LB4F
ACDPM	ACDPM
MAIN	MAIN
REN	REN
jnlDesk	jnlDesk
maps	maps
Migration	*
```

> **注意**:
> - 第一欄 `folio_code` 必須是 FOLIO location 的 `code` 值（程式比對 FOLIO 中 location 的 `code` 屬性）
> - 第二欄是來源資料的欄位名稱（如 `LOCATION`），值為來源資料中的位置代碼
> - 通配符 `*` 放在第二欄（來源值），表示未匹配的值使用第一欄的 `folio_code` 作為預設
> - **欄位名稱必須是 `folio_code`**（不是 `folio_name` 或 `legacy_code`），否則工具會報 CRITICAL 錯誤

### 2. material_types.tsv

資料類型對應。

```tsv
folio_name	MATERIAL_TYPE
BOOK	BOOK
DVD	DVD
CD	CD
book	a
sound recording	c
MIGRATION	*
```

### 3. loan_types.tsv

借閱類型對應。

```tsv
folio_name	LOAN_TYPE
一般圖書(可外借)	CIR
不可外借	NOCIR
Can circulate	0
Reading room	199
Can circulate	42
Can circulate	33
不可外借	*
```

### 4. call_number_type_mapping.tsv

索書號類型對應。

```tsv
folio_name	CALL_NUMBER_TYPE
Dewey Decimal classification	DDC
Library of Congress classification	LCC
Library of Congress classification	0
Dewey Decimal classification	*
```

### 5. item_statuses.tsv

館藏狀態對應。

```tsv
legacy_code	folio_name
available	Available
checked_out	Checked out
lost	Aged to lost
-	Available
o	Available
*	Available
```

### 6. statcodes.tsv (選用)

統計代碼對應。

```tsv
legacy_code	folio_code
STAT1	stat-code-1
STAT2	stat-code-2
*	default-stat
```

---

## 七、執行順序

### 完整流程圖

```
┌─────────────────────────────────────────────────────────────────┐
│ Step 1: Bibs/Instances                                          │
├─────────────────────────────────────────────────────────────────┤
│  transform_bibs → post_bibs → post_srs_bibs                     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 2: Holdings                                                │
├─────────────────────────────────────────────────────────────────┤
│  方式 A: transform_mfhd → post_holdingsrecords_from_mfhd        │
│          → post_srs_mfhds                                       │
│                                                                 │
│  方式 B: transform_csv_holdings → post_csv_holdings             │
│                                                                 │
│  (可同時使用兩種方式，注意使用 previouslyGeneratedHoldingsFiles)  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 3: Items                                                   │
├─────────────────────────────────────────────────────────────────┤
│  transform_csv_items                                            │
│  transform_mfhd_items                                           │
│  transform_bw_items                                             │
│          ↓                                                      │
│  post_items (可合併多個來源的 Items)                              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Step 4: Extradata (Bound-with 關係等)                           │
├─────────────────────────────────────────────────────────────────┤
│  post_extradata                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 標準執行指令

```bash
# 設定基本變數
BASE_FOLDER="/path/to/iteration"
TASK_CONFIG="mapping_files/taskConfig.json"

# 啟動虛擬環境
source .venv/bin/activate

# 1. 轉檔 Bibs (Instances)
python -m folio_migration_tools.migration_tasks.migration_task_base \
  --base_folder $BASE_FOLDER \
  --task_config $TASK_CONFIG \
  --task_name transform_bibs

python -m folio_migration_tools.migration_tasks.migration_task_base \
  --base_folder $BASE_FOLDER \
  --task_config $TASK_CONFIG \
  --task_name post_bibs

# 2. 轉檔 Holdings (MFHD 方式)
python -m folio_migration_tools.migration_tasks.migration_task_base \
  --base_folder $BASE_FOLDER \
  --task_config $TASK_CONFIG \
  --task_name transform_mfhd

python -m folio_migration_tools.migration_tasks.migration_task_base \
  --base_folder $BASE_FOLDER \
  --task_config $TASK_CONFIG \
  --task_name post_holdingsrecords_from_mfhd

# 3. 轉檔 Holdings (CSV 方式)
python -m folio_migration_tools.migration_tasks.migration_task_base \
  --base_folder $BASE_FOLDER \
  --task_config $TASK_CONFIG \
  --task_name transform_csv_holdings

python -m folio_migration_tools.migration_tasks.migration_task_base \
  --base_folder $BASE_FOLDER \
  --task_config $TASK_CONFIG \
  --task_name post_csv_holdings

# 4. 轉檔 Items
python -m folio_migration_tools.migration_tasks.migration_task_base \
  --base_folder $BASE_FOLDER \
  --task_config $TASK_CONFIG \
  --task_name transform_csv_items

python -m folio_migration_tools.migration_tasks.migration_task_base \
  --base_folder $BASE_FOLDER \
  --task_config $TASK_CONFIG \
  --task_name transform_mfhd_items

# 5. 匯入 Items
python -m folio_migration_tools.migration_tasks.migration_task_base \
  --base_folder $BASE_FOLDER \
  --task_config $TASK_CONFIG \
  --task_name post_items

# 6. 匯入 Extradata
python -m folio_migration_tools.migration_tasks.migration_task_base \
  --base_folder $BASE_FOLDER \
  --task_config $TASK_CONFIG \
  --task_name post_extradata
```

---

## 八、THU 095 轉檔的具體設定

### 資料來源結構 (從 MARC 095 欄位提取)

**095 子欄位對應**:

| 子欄位 | 內容 | 對應欄位 |
|--------|------|----------|
| $a | 圖書館代碼 | library |
| $b | 館藏位置 | location |
| $c | 條碼 | barcode |
| $d | 分類號 | classification |
| $e | 著者號 | cutter |
| $p | 資料類型 | material_type |
| $t | 索書號類型 | call_number_type |
| $y | 年份 | year |
| $z | 完整索書號 | full_call_number |

### 提取後的 TSV 結構

**Holdings TSV** (`holdings.tsv`，使用標準版腳本 extract_095_standard.py):

```tsv
HOLDINGS_ID	BIB_ID	LOCATION	CALL_NUMBER	CALL_NUMBER_TYPE	NOTE
00301888-LB3F-BOOK_332.6_L242_2000	00301888	LB3F	332.6 L242 2000	DDC
00301889-LB4F-BOOK_658.4_S123_2001	00301889	LB4F	658.4 S123 2001	DDC
```

> **注意**：
> - HOLDINGS_ID 格式為 `{bib_id}-{location}-{material_type}_{call_number}`
> - Call number 不包含 material type 前綴（腳本會自動從 $z 中去除）

**Items TSV** (`items.tsv`，使用標準版腳本 extract_095_standard.py):

```tsv
ITEM_ID	BIB_ID	HOLDINGS_ID	BARCODE	LOCATION	MATERIAL_TYPE	LOAN_TYPE	CALL_NUMBER	COPY_NUMBER	YEAR	STATUS	NOTE
W228135	00301888	00301888-LB3F-BOOK_332.6_L242_2000	W228135	LB3F	BOOK		332.6 L242 2000		2000	Available
W228136	00301889	00301889-LB4F-BOOK_658.4_S123_2001	W228136	LB4F	BOOK		658.4 S123 2001		2001	Available
```

### TaskConfig 設定 (`taskConfig_095.json`)

```json
{
  "libraryInformation": {
    "tenantId": "fs00001280",
    "okapiUrl": "https://api-thu.folio.ebsco.com",
    "okapiUsername": "EBSCOAdmin",
    "libraryName": "thu",
    "logLevelDebug": false,
    "folioRelease": "sunflower",
    "multiFieldDelimiter": "<^>",
    "addTimeStampToFileNames": false,
    "failedPercentageThreshold": 25,
    "iterationIdentifier": "current"
  },
  "migrationTasks": [
    {
      "name": "holdings_from_095",
      "holdingsMapFileName": "holdings_mapping_095.json",
      "callNumberTypeMapFileName": "call_number_type_mapping.tsv",
      "migrationTaskType": "HoldingsCsvTransformer",
      "fallbackHoldingsTypeId": "22b583e7-0998-4373-9c0b-053a0cb17f2c",
      "locationMapFileName": "locations.tsv",
      "defaultCallNumberTypeName": "Dewey Decimal classification",
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
      "name": "holdings_095_poster",
      "migrationTaskType": "BatchPoster",
      "objectType": "Holdings",
      "batchSize": 1000,
      "files": [
        {
          "fileName": "folio_holdings_holdings_from_095.json"
        }
      ]
    },
    {
      "name": "items_from_095",
      "migrationTaskType": "ItemsTransformer",
      "hridHandling": "default",
      "defaultCallNumberTypeName": "Dewey Decimal classification",
      "defaultLoanTypeName": "一般圖書(可外借)",
      "itemsMappingFileName": "item_mapping_095.json",
      "locationMapFileName": "locations.tsv",
      "tempLocationMapFileName": "locations.tsv",
      "materialTypesMapFileName": "material_types.tsv",
      "loanTypesMapFileName": "loan_types.tsv",
      "callNumberTypeMapFileName": "call_number_type_mapping.tsv",
      "itemStatusesMapFileName": "item_statuses.tsv",
      "files": [
        {
          "file_name": "items_from_095.tsv"
        }
      ]
    },
    {
      "name": "items_095_poster",
      "migrationTaskType": "BatchPoster",
      "objectType": "Items",
      "batchSize": 1000,
      "files": [
        {
          "file_name": "folio_items_items_from_095.json"
        }
      ]
    }
  ]
}
```

### 完整執行步驟

```bash
# 在 Linux 主機上執行
cd /folio/folio_migration_web/clients/thu/iterations/thu_migration

# 啟動虛擬環境
source .venv/bin/activate

# 1. 確認 Instances 已匯入完成
# (應該在之前的步驟已完成)

# 2. 轉檔 Holdings (from 095)
python -m folio_migration_tools.migration_tasks.migration_task_base \
  --base_folder . \
  --task_config mapping_files/taskConfig_095.json \
  --task_name holdings_from_095

# 檢查轉檔結果
ls -la results/folio_holdings_holdings_from_095.json

# 3. 匯入 Holdings 到 FOLIO
python -m folio_migration_tools.migration_tasks.migration_task_base \
  --base_folder . \
  --task_config mapping_files/taskConfig_095.json \
  --task_name holdings_095_poster

# 4. 轉檔 Items (from 095)
python -m folio_migration_tools.migration_tasks.migration_task_base \
  --base_folder . \
  --task_config mapping_files/taskConfig_095.json \
  --task_name items_from_095

# 檢查轉檔結果
ls -la results/folio_items_items_from_095.json

# 5. 匯入 Items 到 FOLIO
python -m folio_migration_tools.migration_tasks.migration_task_base \
  --base_folder . \
  --task_config mapping_files/taskConfig_095.json \
  --task_name items_095_poster

# 6. 檢查 logs
tail -100 logs/holdings_from_095_*.log
tail -100 logs/items_from_095_*.log
```

---

## 九、常見問題與解決

### 問題排查表

| 問題 | 可能原因 | 解決方案 |
|------|----------|----------|
| Holdings 找不到 Instance | instanceId 對應的 bib_id 在 FOLIO 中不存在 | 1. 確認 Bibs 已先匯入<br>2. 檢查 001 欄位值是否正確<br>3. 查看 Instance 的 hrid 或 identifiers |
| Items 找不到 Holdings | holdingsRecordId 無法對應到任何 Holdings | 1. 檢查 holdingsMergeCriteria 設定<br>2. 確認 Holdings 已先建立<br>3. 檢查 bib_id + location + callNumber 是否匹配 |
| Location 對應失敗 | locations.tsv 缺少該位置代碼 | 1. 新增 location code 到 locations.tsv<br>2. 使用 `*` 設定預設值 |
| Material Type 錯誤 | material_types.tsv 缺少對應 | 1. 新增 material type 對應<br>2. 確認 FOLIO 中已建立該 Material Type |
| Loan Type 錯誤 | loan_types.tsv 缺少對應 | 1. 新增 loan type 對應<br>2. 使用 defaultLoanTypeName 設定預設值 |
| 重複的 Holdings | 相同 Instance+Location+CallNumber | 使用 holdingsMergeCriteria 自動合併 |
| Barcode 重複 | 多筆 Item 使用相同條碼 | 1. 清理來源資料<br>2. 使用 legacyIdentifier 作為唯一識別 |
| 轉檔成功但匯入失敗 | FOLIO API 驗證錯誤 | 1. 檢查 logs 中的錯誤訊息<br>2. 確認所有 reference data 已存在於 FOLIO |

### 常見錯誤訊息

#### 1. "Instance not found"

```
ERROR: Could not find instance for legacy id: 00301888
```

**解決**: 確認該 bib_id 對應的 Instance 已匯入 FOLIO。

```bash
# 在 FOLIO 中查詢
curl -X GET "https://api-xxx.folio.ebsco.com/instance-storage/instances?query=hrid==00301888" \
  -H "X-Okapi-Tenant: xxx" \
  -H "X-Okapi-Token: xxx"
```

#### 2. "Location not found"

```
ERROR: Could not map location: LB45
```

**解決**: 在 locations.tsv 中新增對應：

```tsv
LB45	LB45
```

或確認 FOLIO 中已建立該 Location。

#### 3. "Holdings record not found for item"

```
ERROR: Could not find holdings record for item with legacy id: W228135
```

**解決**:
1. 確認 Holdings 已先匯入
2. 檢查 holdingsMergeCriteria 是否正確
3. 確認 Item 的 bib_id + location + call_number 與 Holdings 匹配

### Log 檔案位置

```
logs/
├── holdings_from_095_20260205_*.log      # Holdings 轉檔 log
├── holdings_095_poster_20260205_*.log    # Holdings 匯入 log
├── items_from_095_20260205_*.log         # Items 轉檔 log
└── items_095_poster_20260205_*.log       # Items 匯入 log
```

### 驗證指令

```bash
# 驗證 Holdings 數量
curl -X GET "https://api-xxx.folio.ebsco.com/holdings-storage/holdings?limit=0" \
  -H "X-Okapi-Tenant: xxx" \
  -H "X-Okapi-Token: xxx" | jq '.totalRecords'

# 驗證 Items 數量
curl -X GET "https://api-xxx.folio.ebsco.com/item-storage/items?limit=0" \
  -H "X-Okapi-Tenant: xxx" \
  -H "X-Okapi-Token: xxx" | jq '.totalRecords'

# 查詢特定 Instance 的 Holdings
curl -X GET "https://api-xxx.folio.ebsco.com/holdings-storage/holdings?query=instanceId==<uuid>" \
  -H "X-Okapi-Tenant: xxx" \
  -H "X-Okapi-Token: xxx"

# 查詢特定 Holdings 的 Items
curl -X GET "https://api-xxx.folio.ebsco.com/item-storage/items?query=holdingsRecordId==<uuid>" \
  -H "X-Okapi-Tenant: xxx" \
  -H "X-Okapi-Token: xxx"
```

---

## 附錄：檔案結構參考

```
iteration_folder/
├── mapping_files/
│   ├── taskConfig.json                    # 主要任務設定
│   ├── taskConfig_095.json                # 095 專用任務設定
│   ├── holdings_mapping.json              # Holdings 欄位對應
│   ├── holdings_mapping_095.json          # 095 Holdings 欄位對應
│   ├── item_mapping.json                  # Item 欄位對應
│   ├── item_mapping_095.json              # 095 Item 欄位對應
│   ├── locations.tsv                      # 位置對應
│   ├── material_types.tsv                 # 資料類型對應
│   ├── loan_types.tsv                     # 借閱類型對應
│   ├── call_number_type_mapping.tsv       # 索書號類型對應
│   └── item_statuses.tsv                  # 館藏狀態對應
├── source_data/
│   ├── instances/
│   │   └── bibs.mrc                       # 書目 MARC 檔
│   ├── holdings/
│   │   ├── holding.mrc                    # Holdings MARC 檔 (MFHD)
│   │   └── holdings_from_095.tsv          # 從 095 提取的 Holdings
│   └── items/
│       ├── items.tsv                      # Items TSV
│       └── items_from_095.tsv             # 從 095 提取的 Items
├── results/
│   ├── folio_instances_*.json             # 轉檔後的 Instances
│   ├── folio_holdings_*.json              # 轉檔後的 Holdings
│   └── folio_items_*.json                 # 轉檔後的 Items
└── logs/
    └── *.log                              # 執行 logs
```

---

*文件更新日期: 2026-02-23*
