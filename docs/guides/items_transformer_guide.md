# ItemsTransformer 任務完整操作流程指南

## 概述

ItemsTransformer 是 FOLIO Migration Tools 中用於將 TSV/CSV 表格資料轉換為 FOLIO Item 記錄的任務。適用於：

- 從 MARC 095 欄位提取的單冊資料（THU 模式）
- 從原系統 CSV/TSV 匯出的單冊（Item）資料
- 任何以表格形式存在的單冊資料

### 前置條件

ItemsTransformer 依賴已存在的 Instance 和 Holdings 記錄：

```
1. BibsTransformer (transform_bibs)           → 產出 instances_id_map.json
2. BatchPoster (post_instances)               → 將 Instances 匯入 FOLIO
3. HoldingsCsvTransformer (holdings_from_095)  → 產出 holdings_id_map.json
4. BatchPoster (post_holdings)                → 將 Holdings 匯入 FOLIO
5. ItemsTransformer (transform_items)          → 使用 holdings_id_map.json  ← 本文件
6. BatchPoster (post_items)                   → 將 Items 匯入 FOLIO
```

> **重要**：Items 透過 `holdings_id_map.json` 連結到 Holdings。若 Holdings 尚未轉檔或未匯入 FOLIO，ItemsTransformer 將無法正確建立 Item 與 Holdings 的關聯。

---

## 1. 任務執行命令

### 基本命令格式

```bash
# 密碼透過環境變數傳遞，避免在 ps 輸出中暴露
export FOLIO_MIGRATION_TOOLS_FOLIO_PASSWORD="your_password"
export FOLIO_MIGRATION_TOOLS_OKAPI_PASSWORD="your_password"

python -m folio_migration_tools <config_path> <task_name> --base_folder_path <path>
```

### 實際範例

```bash
export FOLIO_MIGRATION_TOOLS_FOLIO_PASSWORD="your_password"
export FOLIO_MIGRATION_TOOLS_OKAPI_PASSWORD="your_password"

python -m folio_migration_tools \
    /path/to/client/mapping_files/migration_config.json \
    transform_items \
    --base_folder_path /path/to/client
```

> **注意**：需要同時設定 `FOLIO_MIGRATION_TOOLS_FOLIO_PASSWORD` 和 `FOLIO_MIGRATION_TOOLS_OKAPI_PASSWORD` 兩個環境變數，以避免工具在執行時出現互動式密碼提示。

### Web Portal 執行方式

Web Portal 使用每個客戶專案自己的 Python 虛擬環境：

```python
# Windows
project_python = client_path / ".venv" / "Scripts" / "python.exe"

# Linux/macOS
project_python = client_path / ".venv" / "bin" / "python"

cmd = [
    str(project_python), "-m", "folio_migration_tools",
    str(config_path),
    task_name,
    "--base_folder_path", base_folder,
]

# 密碼透過環境變數傳遞（見 execution_service.py）
process = subprocess.Popen(
    cmd,
    env={
        **os.environ,
        "FOLIO_MIGRATION_TOOLS_FOLIO_PASSWORD": folio_password,
        "FOLIO_MIGRATION_TOOLS_OKAPI_PASSWORD": folio_password,
    },
)
```

透過 Web Portal 介面執行：

1. 進入客戶專案詳情頁
2. 點擊「Execute Tasks」按鈕
3. 選擇要執行的任務（如 `transform_items`）
4. 選擇 Iteration
5. 確認使用儲存的 Credentials
6. 點擊「Start Execution」

---

## 2. TaskConfig 設定

### migration_config.json 中的任務定義

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
    "failedPercentageThreshold": 25,
    "iterationIdentifier": "current"
  },
  "migrationTasks": [
    {
      "name": "transform_items",
      "migrationTaskType": "ItemsTransformer",
      "itemsMappingFileName": "item_mapping.json",
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
      ],
      "updateHridSettings": false
    }
  ]
}
```

### libraryInformation 欄位說明

| 欄位 | 說明 |
|------|------|
| `tenantId` | FOLIO 租戶 ID |
| `okapiUrl` | Okapi API 網址 |
| `okapiUsername` | Okapi 登入使用者名稱 |
| `libraryName` | 圖書館名稱標識 |
| `folioRelease` | FOLIO 版本（如 `sunflower`） |
| `multiFieldDelimiter` | 多值欄位分隔符號（預設 `<^>`） |
| `failedPercentageThreshold` | 失敗比例門檻（超過即中止，預設 25%） |
| `iterationIdentifier` | 迭代識別碼（如 `current`、`thu_migration`） |

---

## 3. 完整參數表

以下參數基於 `items_transformer.py` 的 `TaskConfiguration` 類別：

| 參數 | 類型 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| `name` | string | 是 | - | 任務名稱，用於執行和識別 |
| `migrationTaskType` | string | 是 | - | 必須為 `"ItemsTransformer"` |
| `files` | FileDefinition[] | 是 | - | 來源 TSV/CSV 檔案列表 |
| `itemsMappingFileName` | string | 是 | - | Item 欄位對應 JSON 檔名 |
| `locationMapFileName` | string | 是 | - | 位置對應 TSV 檔名 |
| `materialTypesMapFileName` | string | 是 | - | 資料類型對應 TSV 檔名 |
| `loanTypesMapFileName` | string | 是 | - | 借閱類型對應 TSV 檔名 |
| `itemStatusesMapFileName` | string | 是 | - | 狀態對應 TSV 檔名 |
| `callNumberTypeMapFileName` | string | 是 | - | 索書號類型對應 TSV 檔名 |
| `defaultCallNumberTypeName` | string | 是 | - | 預設索書號類型名稱（須與 FOLIO 中的名稱完全一致） |
| `defaultLoanTypeName` | string | 否* | - | 預設借閱類型名稱 |
| `hridHandling` | enum | 是 | - | HRID 處理方式：`"default"` 或 `"preserve001"` |
| `tempLocationMapFileName` | string | 否 | `""` | 暫時位置對應 TSV 檔名 |
| `tempLoanTypesMapFileName` | string | 否 | `""` | 暫時借閱類型對應 TSV 檔名 |
| `statisticalCodesMapFileName` | string | 否 | `""` | 統計代碼對應 TSV 檔名 |
| `updateHridSettings` | boolean | 否 | `true` | 是否更新 FOLIO HRID 計數器 |
| `resetHridSettings` | boolean | 否 | `false` | 是否重置 HRID 計數器至起始值 |
| `boundwithRelationshipFilePath` | string | 否 | `""` | Boundwith 關聯檔案路徑（Voyager 風格的 TSV，含 MFHD_ID 和 BIB_ID） |
| `preventPermanentLocationMapDefault` | boolean | 否 | `false` | 阻止位置預設映射（設為 `true` 時，未匹配的位置不會 fallback） |

> *`defaultLoanTypeName` 未在 TaskConfiguration 中定義為獨立欄位，但建議在配置中設定，搭配 `loan_types.tsv` 的 `*` fallback 使用。

### files 欄位格式

```json
"files": [
  {
    "file_name": "items_from_095.tsv"
  }
]
```

| 屬性 | 說明 |
|------|------|
| `file_name` | 來源資料檔名 |
| `suppressed` | 是否將產出的 Items 標記為 suppressed（不在 OPAC 顯示） |

---

## 4. Mapping 檔案說明

### 4.1 item_mapping.json

Item Mapping 檔案定義來源 TSV 欄位與 FOLIO Item 欄位之間的對應關係。

#### 格式結構

```json
{
  "data": [
    {
      "folio_field": "FOLIO 欄位名稱",
      "legacy_field": "來源 TSV 欄位名稱",
      "value": "",
      "description": "說明"
    }
  ]
}
```

#### 欄位對應說明

| folio_field | 說明 | 必填 | 備註 |
|-------------|------|------|------|
| `barcode` | 條碼 | 否 | 重複條碼會自動加上 UUID 後綴 |
| `legacyIdentifier` | 原系統識別碼 | 是 | 用於產生 Item UUID |
| `formerIds[0]` | 歷史識別碼 | 否 | 保留原系統 ID |
| `holdingsRecordId` | Holdings UUID | 是 | 透過 `holdings_id_map.json` 解析（見[第 5 節](#5-holdings-連結機制)） |
| `materialTypeId` | 資料類型 | 是 | 透過 `material_types.tsv` 對應 |
| `permanentLoanTypeId` | 借閱類型 | 是 | **必須映射到來源欄位**，透過 `loan_types.tsv` 對應 |
| `permanentLocationId` | 永久位置 | 是 | 透過 `locations.tsv` 對應 |
| `itemLevelCallNumber` | Item 層級索書號 | 否 | |
| `itemLevelCallNumberTypeId` | 索書號類型 | 否 | 透過 `call_number_type_mapping.tsv` 對應 |
| `status.name` | 狀態 | 否 | 透過 `item_statuses.tsv` 對應，或設 `value` 為固定值 |
| `copyNumber` | 複本號 | 否 | |
| `volume` | 卷次 | 否 | |
| `enumeration` | 列舉 | 否 | |
| `chronology` | 年代 | 否 | |
| `yearCaption[0]` | 年份標題 | 否 | |
| `notes[0].note` | 備註 | 否 | |
| `notes[0].itemNoteTypeId` | 備註類型 UUID | 否 | 需提供 FOLIO Item Note Type UUID |
| `notes[0].staffOnly` | 僅員工可見 | 否 | `true` 或 `false` |

> **重要**：`permanentLoanTypeId` 必須映射到來源資料的欄位（如 `loan_type`、`LOAN_TYPE`、`ITEM_TYPE_ID` 等），不可設為 `"Not mapped"`。若來源資料沒有借閱類型欄位，應在 `loan_types.tsv` 中使用 `*` 通配符作為 fallback。

#### `legacyIdentifier` 與 `fallback_legacy_field`

`legacyIdentifier` 是產生 Item UUID 的依據。若主要識別碼可能為空，可使用 `fallback_legacy_field` 指定備用欄位：

```json
{
  "folio_field": "legacyIdentifier",
  "legacy_field": "barcode",
  "fallback_legacy_field": "bib_id",
  "value": ""
}
```

當 `barcode` 為空時，會改用 `bib_id` 的值。

#### THU 095 範例（`item_mapping_095.json`）

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
      "folio_field": "legacyIdentifier",
      "legacy_field": "barcode",
      "fallback_legacy_field": "bib_id",
      "value": ""
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
      "folio_field": "holdingsRecordId",
      "legacy_field": "holdings_id",
      "value": "",
      "description": "透過 bib_id + location + call_number 連結"
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
      "description": "透過 loan_types.tsv 映射"
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

### 4.2 material_types.tsv

資料類型對應檔案，將來源資料的資料類型代碼對應到 FOLIO 的 Material Type 名稱。

#### 格式

```
folio_name	MATERIAL_TYPE
```

- **`folio_name`**（必須使用此名稱）：FOLIO 中的 Material Type 名稱，必須完全一致
- **第二欄名稱必須與來源 TSV 的欄位名完全一致**（如 `MATERIAL_TYPE`、`material_type`）
- 支援通配符 `*` 作為 fallback（建議提供）

> **重要**：`folio_name` 是 folio_migration_tools 的 `RefDataMapping` 保留欄位名，不可更改。第二欄名稱會被用來查找來源資料中的對應值。

#### THU 範例

```tsv
folio_name	MATERIAL_TYPE
A	A
BOOK	BOOK
CD	CD
DVD	DVD
EB	EB
MIGRATION	*
```

> `*` fallback：當來源資料的 `MATERIAL_TYPE` 值不在對應表中時，會使用 `MIGRATION` 作為預設。

### 4.3 loan_types.tsv

借閱類型對應檔案，將來源資料的借閱類型代碼對應到 FOLIO 的 Loan Type 名稱。

#### 格式

```
folio_name	LOAN_TYPE
```

- **`folio_name`**（必須使用此名稱）：FOLIO 中的 Loan Type 名稱
- **第二欄名稱必須與來源 TSV 的欄位名完全一致**（如 `LOAN_TYPE`、`loan_type`）
- **強烈建議**提供 `*` fallback，處理來源資料中空值或未預期的值

#### THU 範例

```tsv
folio_name	LOAN_TYPE
Reading room	33
Can circulate	42
Can circulate	*
```

> **搭配 `defaultLoanTypeName`**：`loan_types.tsv` 的 `*` fallback 處理來源資料中的未知值；`defaultLoanTypeName` 是 taskConfig 層級的額外安全網。建議兩者都設定。

### 4.4 item_statuses.tsv

館藏狀態對應檔案。**此檔案有特殊規則**，與其他 mapping 檔案不同：

#### 格式

```
legacy_code	folio_name
```

- **必須使用固定欄位名** `legacy_code` 和 `folio_name`（程式碼中有硬編碼檢查）
- **不允許 `*` 通配符**（程式碼會檢查並中止執行）
- 未匹配的狀態會自動使用 `Available` 作為預設值
- `folio_name` 的值必須是 FOLIO 支援的 Item Status 名稱

#### THU 範例

```tsv
legacy_code	folio_name
available	Available
checked_out	Checked out
lost	Aged to lost
```

#### FOLIO 支援的 Item Status 清單

| Status | 說明 |
|--------|------|
| `Available` | 可借閱 |
| `Checked out` | 已借出 |
| `In transit` | 運送中 |
| `Awaiting pickup` | 待取件 |
| `Awaiting delivery` | 待配送 |
| `Missing` | 遺失 |
| `Paged` | 已調閱 |
| `On order` | 訂購中 |
| `In process` | 處理中 |
| `Declared lost` | 讀者報遺失 |
| `Claimed returned` | 聲稱已歸還 |
| `Aged to lost` | 超期轉遺失 |
| `Withdrawn` | 已註銷 |
| `Lost and paid` | 遺失已賠償 |
| `Restricted` | 限制使用 |
| `Intellectual item` | 虛擬項目 |
| `In process (non-requestable)` | 處理中（不可請求） |
| `Long missing` | 長期遺失 |
| `Unavailable` | 不可用 |
| `Unknown` | 未知 |
| `Order closed` | 訂單已關閉 |

### 4.5 locations.tsv

位置對應檔案，與 Holdings 共用。將來源系統的位置代碼對應到 FOLIO 的 location code。

#### 格式

```
legacy_code	folio_code
```

- 使用 Tab 分隔
- 支援通配符 `*` 作為 fallback
- 與 HoldingsCsvTransformer 共用同一個檔案

#### THU 範例（前幾行）

```tsv
legacy_code	folio_code
LB3F	LB3F
LB4F	LB4F
LBA	LBA
LBBS	LBBS
*	Migration
```

### 4.6 call_number_type_mapping.tsv

索書號類型對應檔案，與 Holdings 共用。

#### 格式

```
folio_name	CALL_NUMBER_TYPE
```

- **`folio_name`**（必須使用此名稱）：FOLIO 中的索書號類型名稱
- **第二欄名稱必須與來源 TSV 的欄位名完全一致**
- 支援通配符 `*` 作為 fallback（建議提供）

#### THU 範例

```tsv
folio_name	CALL_NUMBER_TYPE
Dewey Decimal classification	DDC
Library of Congress classification	LCC
CCL	CCL
CFC	CFC
MCD	MCD
TTC	TTC
CCL	*
```

---

## 5. Holdings 連結機制

### holdingsRecordId 解析流程

ItemsTransformer 透過 `holdings_id_map.json` 將來源資料中的 Holdings 識別碼轉換為 FOLIO Holdings UUID：

```
來源 TSV (items_from_095.tsv)
  └─ holdingsRecordId 對應的 legacy_field 值（如 "001_LB_312.4 7821"）
      └─ 在 holdings_id_map.json 中查找
          └─ 找到對應的 FOLIO Holdings UUID
              └─ 寫入 Item 記錄的 holdingsRecordId
```

### holdings_id_map.json 結構

`holdings_id_map.json` 是 HoldingsCsvTransformer 的輸出檔案，位於 `iterations/{iter}/results/` 目錄：

```json
{
  "001_LB_312.4 7821": ["legacy_id", "550e8400-e29b-41d4-a716-446655440000"],
  "001_LB3F_005.133": ["legacy_id", "6312d172-f0cf-40f6-b27d-9fa8feaf332f"]
}
```

- Key：Holdings 的 Legacy ID（由 Holdings Mapping 的 `legacyIdentifier` 產生）
- Value[1]：FOLIO Holdings UUID

### item_mapping.json 中的設定

```json
{
  "folio_field": "holdingsRecordId",
  "legacy_field": "holdings_id",
  "value": ""
}
```

`legacy_field` 指定的來源 TSV 欄位值必須能在 `holdings_id_map.json` 中找到對應的 Key。

### 必要的執行順序

```
1. HoldingsCsvTransformer → 產出 holdings_id_map.json
2. BatchPoster (Holdings)  → 將 Holdings 匯入 FOLIO
3. ItemsTransformer        → 讀取 holdings_id_map.json 進行連結
4. BatchPoster (Items)     → 將 Items 匯入 FOLIO
```

> **注意**：Holdings 必須先匯入 FOLIO（步驟 2），因為 ItemsTransformer 初始化時需要從 FOLIO API 取得 Reference Data（Material Types、Loan Types 等）。

---

## 6. 輸出檔案

### 結果檔案位置

```
{client_path}/iterations/{iteration}/
├── results/
│   └── folio_items_{task_name}.json     # 轉檔後的 FOLIO Item 記錄
│
└── reports/
    ├── report_transform_items.md        # 轉檔統計報告（Markdown）
    └── data_issues_log_transform_items.tsv  # 資料問題記錄
```

### Items JSON 格式

輸出的 `folio_items_{task_name}.json` 為 JSON Lines 格式（每行一筆記錄）：

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "holdingsRecordId": "6312d172-f0cf-40f6-b27d-9fa8feaf332f",
  "barcode": "T001234",
  "materialTypeId": "1a54b431-2e4f-452d-9cae-9cee66c9a892",
  "permanentLoanTypeId": "2b94c631-fca9-4892-a730-03ee529ffe27",
  "permanentLocationId": "a1234567-89ab-cdef-0123-456789abcdef",
  "status": {
    "name": "Available",
    "date": "2026-02-13T00:00:00.000000+00:00"
  },
  "formerIds": ["T001234", "001"],
  "_version": 1
}
```

### 報告檔案內容

報告檔案 (`report_transform_items.md`) 包含：

| 統計指標 | 說明 |
|---------|------|
| Number of files processed | 處理的來源檔案數 |
| Number of Legacy items in total | 來源資料總筆數 |
| Number of records written to disk | 成功產出的 Item 筆數 |
| Duplicate barcodes | 重複條碼數量 |
| Records failed because of failed holdings | 因 Holdings 查找失敗的筆數 |
| FAILED Records failed due to an error | 其他失敗筆數 |

### 下一步：匯入 FOLIO

ItemsTransformer 完成後，需使用 BatchPoster 將產出的 Item 記錄匯入 FOLIO。請參閱 [batch_poster_guide.md](batch_poster_guide.md)。

BatchPoster 任務配置範例：

```json
{
  "name": "post_items",
  "migrationTaskType": "BatchPoster",
  "objectType": "Items",
  "batchSize": 250,
  "files": [
    {
      "file_name": "folio_items_transform_items.json"
    }
  ]
}
```

---

## 7. HRID 處理

### 可用選項

| 模式 | 說明 |
|------|------|
| `default` | FOLIO 自動產生 HRID（推薦） |
| `preserve001` | 保留來源值作為 HRID |

### updateHridSettings 與 resetHridSettings

| 參數 | 預設值 | 說明 |
|------|--------|------|
| `updateHridSettings` | `true` | 執行後自動更新 FOLIO HRID 計數器 |
| `resetHridSettings` | `false` | 執行前先重置 HRID 計數器至起始值 |

### 測試 vs 正式遷移建議

| 階段 | updateHridSettings | resetHridSettings | 說明 |
|------|-------------------|-------------------|------|
| 測試階段 | `false` | `false` | 避免影響 FOLIO 計數器，方便反覆測試 |
| 正式遷移 | `true`（預設） | 視需求 | 確保計數器正確遞增 |

> **注意**：`resetHridSettings: true` 僅在 `updateHridSettings: true` 時生效。重置會在執行**開始前**將 Item HRID 計數器歸零，僅建議在首次正式遷移時使用。

---

## 8. 常見問題排解

### 8.1 permanentLoanTypeId missing

```
TransformationProcessError: permanentLoanTypeId is not mapped
```

**原因**：`item_mapping.json` 中 `permanentLoanTypeId` 的 `legacy_field` 設為 `"Not mapped"`。

**解決**：將 `legacy_field` 改為來源資料中的借閱類型欄位名（如 `loan_type`、`LOAN_TYPE`），並確保 `loan_types.tsv` 中有對應的映射。

### 8.2 callNumberTypeMapFileName missing

```
File not found: .../mapping_files/call_number_type_mapping.tsv
```

**原因**：taskConfig 中未設定 `callNumberTypeMapFileName`，或檔案不存在。

**解決**：在 taskConfig 中加入 `"callNumberTypeMapFileName": "call_number_type_mapping.tsv"`，並建立對應檔案。

### 8.3 `*` in status mapping not allowed

```
CRITICAL    * in status mapping not allowed. Available will be the default mapping.
Please remove the row with the *
```

**原因**：`item_statuses.tsv` 中使用了 `*` 通配符。

**解決**：移除 `item_statuses.tsv` 中包含 `*` 的行。未匹配的狀態會自動使用 `Available`。

### 8.4 legacy_code is not a column

```
CRITICAL    legacy_code is not a column in the status mapping file
```

**原因**：`item_statuses.tsv` 的欄位名稱不是 `legacy_code` 和 `folio_name`。

**解決**：確保 `item_statuses.tsv` 的標題列使用固定名稱 `legacy_code` 和 `folio_name`。

### 8.5 folio_name is not a column

```
CRITICAL    folio_name is not a column in the status mapping file
```

**原因**：同 8.4，欄位名稱錯誤。

**解決**：確保使用 `legacy_code	folio_name`（Tab 分隔）作為標題列。

### 8.6 id already exists in FOLIO

```
422: id value already exists in table item
```

**原因**：前次測試遺留的 Items 未刪除，再次匯入產生 UUID 衝突。

**解決**：在 FOLIO 中刪除前次測試的 Items，或使用 Web Portal 的 Deletion 功能。執行順序：先刪 Items → 再刪 Holdings → 最後刪 Instances（反向順序）。

### 8.7 Column folio_name missing

```
KeyError: 'folio_name'
```

**原因**：TSV 檔案使用空格而非 Tab 作為分隔符。

**解決**：使用 `hexdump` 確認 TSV 檔案使用 Tab（`\t`，hex `09`）分隔：

```bash
hexdump -C material_types.tsv | head -5
```

### 8.8 Holdings id not found

```
TransformationRecordFailedError: Holdings id referenced in legacy item
was not found amongst transformed Holdings records
```

**原因**：Item 的 `holdingsRecordId` 對應值在 `holdings_id_map.json` 中找不到。

**解決**：
1. 確認 HoldingsCsvTransformer 已執行並產出 `holdings_id_map.json`
2. 確認 Item TSV 中 `holdingsRecordId` 對應欄位的值與 Holdings 的 `legacyIdentifier` 一致
3. 檢查是否有大小寫或空白差異

### 8.9 認證失敗 (401 Unauthorized)

**原因**：FOLIO 帳密錯誤或環境變數未設定。

**解決**：
1. 確認 `FOLIO_MIGRATION_TOOLS_FOLIO_PASSWORD` 和 `FOLIO_MIGRATION_TOOLS_OKAPI_PASSWORD` 環境變數已設定
2. 確認 `okapiUsername` 在 `libraryInformation` 中已填寫
3. 若使用 Web Portal，確認 Credentials 頁面中的帳號密碼正確

---

## 9. 已知問題與限制

### 9.1 item_statuses.tsv 特殊規則

- **不允許 `*` 通配符**：與 `material_types.tsv`、`loan_types.tsv` 等其他 mapping 檔案不同
- **必須使用固定欄位名** `legacy_code` 和 `folio_name`：程式碼中有硬編碼檢查（`item_mapper.py` L137-141）
- 未匹配的狀態自動使用 `Available` 作為預設值

### 9.2 Holdings 必須先存在

- ItemsTransformer 依賴 `holdings_id_map.json`（HoldingsCsvTransformer 的輸出）
- 如果 Holdings 尚未轉檔，所有 Item 都會因找不到 Holdings UUID 而失敗
- Holdings 也必須已匯入 FOLIO（BatchPoster），否則後續匯入 Items 時會因外鍵約束失敗

### 9.3 來源資料 LOAN_TYPE 為空的處理

當來源資料中借閱類型欄位為空時，必須在 `loan_types.tsv` 中設定 `*` fallback：

```tsv
folio_name	LOAN_TYPE
Can circulate	REGULAR
Can circulate	*
```

`*` 會匹配所有空值和未對應的值，將其映射到 `Can circulate`。

### 9.4 重複條碼處理

ItemsTransformer 會自動處理重複條碼：當偵測到條碼已存在時，會在條碼後附加 UUID（如 `T001234-550e8400...`），並在報告中記錄為 "Duplicate barcodes"。

### 9.5 Boundwith 支援

若有合訂本（Boundwith）情況，需透過 `boundwithRelationshipFilePath` 指定一個 TSV 檔案（含 `MFHD_ID` 和 `BIB_ID` 欄位），工具會自動建立跨 Instance 的 Holdings 關聯。

---

## 10. Web Portal 執行流程

### 完整流程

1. **確認前置步驟完成**：
   - Instances 已轉檔並匯入 FOLIO
   - Holdings 已轉檔並匯入 FOLIO
   - `holdings_id_map.json` 存在於 `iterations/{iter}/results/` 目錄

2. **啟用 Items Task**：
   - 在 Web Portal 的客戶設定頁面
   - 確認 Items task 已啟用（`enabled: true`）
   - 確認所有 mapping 檔案已就位

3. **執行 transform_items**：
   - 點擊 Execute Tasks
   - 選擇 `transform_items`
   - 確認 Credentials
   - 點擊 Start Execution
   - 等待執行完成，檢查日誌

4. **檢查結果**：
   - 查看執行日誌確認無嚴重錯誤
   - 檢查 `report_transform_items.md` 統計
   - 確認 `folio_items_transform_items.json` 已產出

5. **執行 post_items**：
   - 選擇 `post_items`
   - 確認匯入成功

---

## 11. 最佳實踐

### 測試建議

1. **設定 `updateHridSettings: false`**：測試階段避免推高 FOLIO 的 HRID 計數器
2. **先小批量測試**：在 `files` 中先用小檔案（如前 100 筆），確認無誤再全量
3. **每次測試前清理**：刪除前次測試的 Items（及可能的 Holdings），避免 UUID 衝突

### Mapping 檔案驗證

1. **確認 Tab 分隔**：使用 `hexdump -C file.tsv | head` 確認使用 Tab（`09`），非空格（`20`）
2. **確認 UTF-8 編碼**：`file -i file.tsv` 確認編碼
3. **確認無 BOM**：若有 BOM（`EF BB BF`），可用 `sed -i '1s/^\xEF\xBB\xBF//' file.tsv` 移除
4. **確認行尾字元**：Linux 應使用 LF（`0a`），非 CRLF（`0d 0a`）

### 欄位名稱一致性

確認以下對應關係一致：

| 檔案 | 欄位名稱來源 |
|------|-------------|
| `item_mapping.json` 的 `legacy_field` | 來源 TSV 的欄位名（標題列） |
| `material_types.tsv` 第二欄名 | 來源 TSV 中 `materialTypeId` 對應的欄位名 |
| `loan_types.tsv` 第二欄名 | 來源 TSV 中 `permanentLoanTypeId` 對應的欄位名 |
| `call_number_type_mapping.tsv` 第二欄名 | 來源 TSV 中 `itemLevelCallNumberTypeId` 對應的欄位名 |

---

## 12. 相關文件

| 文件 | 說明 |
|------|------|
| [holdings_csv_transformer_guide.md](holdings_csv_transformer_guide.md) | Holdings 轉檔指南（前置步驟） |
| [batch_poster_guide.md](batch_poster_guide.md) | Items 匯入 FOLIO 的操作指南 |
| [bibs_transformer_guide.md](bibs_transformer_guide.md) | Instance 轉檔（最前置步驟） |
| [095_holdings_items_migration_workflow.md](095_holdings_items_migration_workflow.md) | 095 欄位提取完整流程 |
| [holdings_items_migration_guide.md](holdings_items_migration_guide.md) | 完整 Holdings/Items 遷移概覽 |
| [task-config-parameters.md](../analysis/task-config-parameters.md) | 所有任務類型的參數參考 |

---

## 附錄：檔案位置總覽

| 檔案 | 位置 | 說明 |
|------|------|------|
| 任務配置 | `mapping_files/migration_config.json` | 任務定義與參數 |
| 圖書館配置 | `mapping_files/library_config.json` | FOLIO 連線資訊 |
| Item Mapping | `mapping_files/item_mapping.json` | 欄位對應 JSON |
| 位置對應 | `mapping_files/locations.tsv` | 位置代碼對應（與 Holdings 共用） |
| 資料類型對應 | `mapping_files/material_types.tsv` | Material Type 對應 |
| 借閱類型對應 | `mapping_files/loan_types.tsv` | Loan Type 對應 |
| 狀態對應 | `mapping_files/item_statuses.tsv` | Item Status 對應 |
| 索書號類型對應 | `mapping_files/call_number_type_mapping.tsv` | Call Number Type 對應（與 Holdings 共用） |
| 來源資料 | `iterations/{iter}/source_data/items/` | Items TSV 輸入 |
| 結果檔案 | `iterations/{iter}/results/` | 轉檔後的 JSON |
| Holdings ID Map | `iterations/{iter}/results/holdings_id_map.json` | Holdings Legacy ID ↔ UUID 對應 |
| 報告檔案 | `iterations/{iter}/reports/` | 執行報告 |
