# HoldingsCsvTransformer 任務完整操作流程指南

## 概述

HoldingsCsvTransformer 是 FOLIO Migration Tools 中用於將 TSV/CSV 表格資料轉換為 FOLIO Holdings 記錄的任務。適用於來源系統沒有獨立 MFHD（MARC Holdings）檔案的情況，例如：

- 從 MARC 095 欄位提取的館藏資料（THU 模式）
- 從原系統 CSV/TSV 匯出的館藏資料
- 任何以表格形式存在的館藏資料

> **與 HoldingsMarcTransformer 的差異**：HoldingsMarcTransformer 處理 MARC Holdings (MFHD) 格式的記錄，適用於有獨立 MFHD 檔案的情況。詳見 [holdings_items_migration_guide.md](holdings_items_migration_guide.md)。

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
    holdings_from_095 \
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
3. 選擇要執行的任務（如 `holdings_from_095`）
4. 選擇 Iteration
5. 確認使用儲存的 Credentials
6. 點擊「Start Execution」

---

## 2. TaskConfig 設定

### migration_config.json 中的任務定義

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
      "migrationTaskType": "HoldingsCsvTransformer",
      "holdingsMapFileName": "holdings_mapping_095.json",
      "locationMapFileName": "locations.tsv",
      "callNumberTypeMapFileName": "call_number_type_mapping.tsv",
      "defaultCallNumberTypeName": "Dewey Decimal classification",
      "fallbackHoldingsTypeId": "22b583e7-0998-4373-9c0b-053a0cb17f2c",
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

以下參數基於 `holdings_csv_transformer.py` 的 `TaskConfiguration` 類別：

| 參數 | 類型 | 必填 | 預設值 | 說明 |
|------|------|------|--------|------|
| `name` | string | 是 | - | 任務名稱，用於執行和識別 |
| `migrationTaskType` | string | 是 | - | 必須為 `"HoldingsCsvTransformer"` |
| `files` | FileDefinition[] | 是 | - | 來源 CSV/TSV 檔案列表 |
| `holdingsMapFileName` | string | 是 | - | Holdings 欄位對應 JSON 檔名 |
| `locationMapFileName` | string | 是 | - | 位置對應 TSV 檔名 |
| `defaultCallNumberTypeName` | string | 是 | - | 預設索書號類型名稱（須與 FOLIO 中的名稱完全一致） |
| `fallbackHoldingsTypeId` | string (UUID) | 是 | - | 預設 Holdings Type UUID（查詢：`/holdings-types`） |
| `callNumberTypeMapFileName` | string | 是* | - | 索書號類型對應 TSV 檔名 |
| `hridHandling` | enum | 是 | - | HRID 處理方式：`"default"` 或 `"preserve001"` |
| `holdingsMergeCriteria` | string[] | 否 | `["instanceId", "permanentLocationId", "callNumber"]` | Holdings 合併條件 |
| `previouslyGeneratedHoldingsFiles` | string[] | 否 | `[]` | 之前已產生的 Holdings 檔案列表，用於避免重複 |
| `holdingsTypeUuidForBoundwiths` | string (UUID) | 否 | `""` | 合訂本（Bound-with）Holdings Type UUID |
| `updateHridSettings` | boolean | 否 | `true` | 是否更新 FOLIO HRID 計數器 |
| `resetHridSettings` | boolean | 否 | `false` | 是否重置 HRID 計數器至起始值 |
| `statisticalCodesMapFileName` | string | 否 | `""` | 統計代碼對應 TSV 檔名 |

> *`callNumberTypeMapFileName` 在 source code 中為 `Optional[str]`，但實際執行時會載入此檔案，建議一律提供。

### files 欄位格式

```json
"files": [
  {
    "file_name": "holdings_from_095.tsv",
    "suppressed": false
  }
]
```

| 屬性 | 說明 |
|------|------|
| `file_name` | 來源資料檔名 |
| `suppressed` | 是否將產出的 Holdings 標記為 suppressed（不在 OPAC 顯示） |

---

## 4. Mapping 檔案說明

### 4.1 Holdings Mapping JSON

Holdings Mapping 檔案定義來源 TSV 欄位與 FOLIO Holdings 欄位之間的對應關係。

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

#### THU 範例（`holdings_mapping_095.json`）

```json
{
  "data": [
    {
      "folio_field": "instanceId",
      "legacy_field": "bib_id",
      "value": "",
      "description": "Link to instance via 001 field"
    },
    {
      "folio_field": "legacyIdentifier",
      "legacy_field": "bib_id",
      "value": "",
      "description": "Legacy identifier for matching"
    },
    {
      "folio_field": "formerIds[0]",
      "legacy_field": "bib_id",
      "value": "",
      "description": "Former ID from bib_id"
    },
    {
      "folio_field": "permanentLocationId",
      "legacy_field": "location",
      "value": "",
      "description": "Permanent location from 095$b"
    },
    {
      "folio_field": "callNumber",
      "legacy_field": "call_number",
      "value": "",
      "description": "Call number from 095$z or assembled from $d$e$y"
    },
    {
      "folio_field": "callNumberTypeId",
      "legacy_field": "call_number_type",
      "value": "",
      "description": "Call number type from 095$t (DDC, LCC, etc.)"
    }
  ]
}
```

#### 欄位對應說明

| folio_field | 說明 | 必填 | 備註 |
|-------------|------|------|------|
| `instanceId` | 關聯的 Instance UUID | 是 | 透過 `instances_id_map.json` 將 legacy_field 值查找對應的 Instance UUID |
| `legacyIdentifier` | 原系統識別碼 | 是 | 用於產生 Holdings UUID 及建立 ID map |
| `formerIds[0]` | 歷史識別碼 | 否 | 保留原系統 ID，方便日後追溯 |
| `permanentLocationId` | 永久館藏位置 | 是 | 透過 `locations.tsv` 對應為 FOLIO location code |
| `callNumber` | 索書號 | 否 | Holdings 記錄的索書號欄位 |
| `callNumberTypeId` | 索書號類型 | 否 | 透過 `call_number_type_mapping.tsv` 對應 |
| `holdingsNoteTypeId` | 備註類型 | 否 | 需提供 FOLIO Holdings Note Type UUID |

> **重要**：`instanceId` 的 `legacy_field` 值必須與 BibsTransformer 產出的 `instances_id_map.json` 中的 Legacy ID 一致，否則 Holdings 無法正確關聯到 Instance。

### 4.2 locations.tsv

位置對應檔案，將來源系統的位置代碼對應到 FOLIO 的 location code。

#### 格式

```
legacy_code	folio_code
```

- 第一列為標題列（欄位名稱可自訂，但必須是兩欄 TSV）
- 使用 Tab 分隔
- 支援通配符 `*` 作為 fallback（未匹配的位置會使用此對應）

#### THU 範例（73 個位置，前幾行）

```tsv
館藏室location	folio_code
00AT	00AT
00AV	00AV
00CA	00CA
LB	LB
LB00	LB00
LB3F	LB3F
LBA	LBA
LBBS	LBBS
*	Migration
```

> **通配符 `*`**：所有未在對應表中列出的位置代碼都會被對應到 `Migration` 這個 FOLIO location。建議在正式遷移前將所有位置都明確列出，僅在測試階段使用 `*`。

### 4.3 call_number_type_mapping.tsv

索書號類型對應檔案，將來源系統的索書號類型代碼對應到 FOLIO 的索書號類型名稱。

#### 格式

```
folio_name	legacy_code
```

- 第一欄為 FOLIO 中的索書號類型名稱（必須完全一致）
- 第二欄為來源資料中的類型代碼
- 支援通配符 `*` 作為 fallback

#### THU 範例

```tsv
folio_name	call_number_type
Dewey Decimal classification	DDC
Library of Congress classification	LCC
Dewey Decimal classification	*
```

> 此範例中，來源資料的 `DDC` 對應到 FOLIO 的「Dewey Decimal classification」，`LCC` 對應到「Library of Congress classification」，其餘未匹配的類型預設使用 DDC。

---

## 5. UUID 查詢

### 5.1 需要 UUID 的參數

| 參數 | UUID 來源 | FOLIO API 端點 |
|------|-----------|----------------|
| `fallbackHoldingsTypeId` | Holdings Types | `/holdings-types` |
| Mapping 中的 `holdingsNoteTypeId` | Holdings Note Types | `/holdings-note-types` |
| `holdingsTypeUuidForBoundwiths` | Holdings Types | `/holdings-types` |

### 5.2 Web Portal UUID 查詢功能

Web Portal 提供內建的 FOLIO Reference Data 查詢功能，無需手動呼叫 API。

**操作路徑**：設定 → FOLIO Reference Data → 選擇 Reference Type

**API 端點**：`GET /api/clients/{client_code}/folio/reference-data/{ref_type}`

**可用的 Reference Types**：

| ref_type key | 說明 | FOLIO API |
|-------------|------|-----------|
| `holdings-types` | Holdings Types | `/holdings-types` |
| `holdings-note-types` | Holdings Note Types | `/holdings-note-types` |
| `locations` | Locations | `/locations` |
| `call-number-types` | Call Number Types | `/call-number-types` |
| `material-types` | Material Types | `/material-types` |
| `loan-types` | Loan Types | `/loan-types` |
| `service-points` | Service Points | `/service-points` |
| `item-note-types` | Item Note Types | `/item-note-types` |
| `address-types` | Address Types | `/addresstypes` |
| `note-types` | Note Types | `/note-types` |
| `patron-groups` | Patron Groups | `/groups` |
| `statistical-codes` | Statistical Codes | `/statistical-codes` |

**查詢步驟**：

1. 進入客戶專案的設定頁面
2. 選擇「FOLIO Reference Data」
3. 從下拉選單選擇資料類型（如 `Holdings Types`）
4. 系統會列出所有可用的項目，包含 `id`（UUID）和 `name`
5. 複製需要的 UUID 填入 TaskConfig

### 5.3 直接 API 查詢

若需直接查詢 FOLIO API：

```bash
# 先取得 Token
TOKEN=$(curl -s -X POST "${OKAPI_URL}/authn/login" \
  -H "Content-Type: application/json" \
  -H "x-okapi-tenant: ${TENANT_ID}" \
  -d '{"username":"'${USERNAME}'","password":"'${PASSWORD}'"}' \
  | jq -r '.okapiToken')

# 查詢 Holdings Types
curl -s "${OKAPI_URL}/holdings-types?limit=100" \
  -H "x-okapi-tenant: ${TENANT_ID}" \
  -H "x-okapi-token: ${TOKEN}" \
  | jq '.holdingsTypes[] | {id, name}'

# 查詢 Locations
curl -s "${OKAPI_URL}/locations?limit=1000" \
  -H "x-okapi-tenant: ${TENANT_ID}" \
  -H "x-okapi-token: ${TOKEN}" \
  | jq '.locations[] | {id, name, code}'

# 查詢 Call Number Types
curl -s "${OKAPI_URL}/call-number-types?limit=100" \
  -H "x-okapi-tenant: ${TENANT_ID}" \
  -H "x-okapi-token: ${TOKEN}" \
  | jq '.callNumberTypes[] | {id, name}'
```

---

## 6. Holdings 合併機制 (holdingsMergeCriteria)

### 原理說明

HoldingsCsvTransformer 會根據 `holdingsMergeCriteria` 指定的欄位組合，判斷多筆來源記錄是否應合併為同一筆 Holdings。預設條件為 `["instanceId", "permanentLocationId", "callNumber"]`，意即：當兩筆記錄屬於同一個 Instance、相同位置、相同索書號時，它們會被合併為一筆 Holdings。

### 合併範例

```
來源 TSV 記錄：

bib_id    location    call_number
001       LB          312.4 7821
001       LB          312.4 7821    ← 相同 Instance + Location + CallNumber → 合併
001       LB3F        312.4 7821    ← 不同 Location → 產生新的 Holdings
002       LB          312.4 7821    ← 不同 Instance → 產生新的 Holdings

結果：
  Holdings 1: Instance=001, Location=LB,   CallNumber=312.4 7821  (合併了 2 筆)
  Holdings 2: Instance=001, Location=LB3F, CallNumber=312.4 7821
  Holdings 3: Instance=002, Location=LB,   CallNumber=312.4 7821
```

### 可用的合併條件

合併條件必須是 FOLIO Holdings Schema 中的有效屬性名稱。常用的包括：

| 條件 | 說明 |
|------|------|
| `instanceId` | Instance UUID（幾乎必須包含） |
| `permanentLocationId` | 永久館藏位置 |
| `callNumber` | 索書號 |
| `callNumberTypeId` | 索書號類型 |
| `holdingsTypeId` | Holdings 類型 |

### previouslyGeneratedHoldingsFiles 的搭配用法

當分多次執行轉檔（例如先轉 MFHD Holdings，再轉 095 Holdings）時，可透過 `previouslyGeneratedHoldingsFiles` 指定先前產出的 Holdings 檔案，避免產生重複的 Holdings：

```json
{
  "previouslyGeneratedHoldingsFiles": [
    "folio_holdings_transform_mfhd.json"
  ]
}
```

工具會載入這些檔案中的 Holdings，並在合併判斷時一併考慮。

---

## 7. 輸出檔案

### 結果檔案位置

```
{client_path}/iterations/{iteration}/
├── results/
│   ├── folio_holdings_{task_name}.json    # 轉檔後的 FOLIO Holdings 記錄
│   └── holdings_id_map.json              # Legacy ID ↔ FOLIO UUID 對應表
│
└── reports/
    ├── report_{task_name}.md             # 轉檔統計報告（Markdown）
    └── report_{task_name}_raw.json       # 原始統計資料（JSON）
```

### Holdings JSON 格式

輸出的 `folio_holdings_{task_name}.json` 為 JSON Lines 格式（每行一筆記錄）：

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "instanceId": "6312d172-f0cf-40f6-b27d-9fa8feaf332f",
  "permanentLocationId": "a1234567-89ab-cdef-0123-456789abcdef",
  "callNumber": "312.4 7821",
  "callNumberTypeId": "03dd64d0-5626-4ecd-8ece-4531e0f7e5b9",
  "holdingsTypeId": "22b583e7-0998-4373-9c0b-053a0cb17f2c",
  "formerIds": ["001"],
  "_version": 1
}
```

### 報告檔案內容

報告檔案 (`report_{task_name}.md`) 包含：

| 統計指標 | 說明 |
|---------|------|
| Number of Legacy items in file | 來源資料總筆數 |
| Holdings Records Written to disk | 產出的 Holdings 筆數 |
| Unique Holdings created from Items | 新建的 Holdings 筆數 |
| Holdings already created from Item | 被合併的筆數 |
| FAILED Records failed due to an error | 失敗筆數 |

### 下一步：匯入 FOLIO

HoldingsCsvTransformer 完成後，需使用 BatchPoster 將產出的 Holdings 記錄匯入 FOLIO。請參閱 [batch_poster_guide.md](batch_poster_guide.md)。

BatchPoster 任務配置範例：

```json
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
}
```

---

## 8. 來源資料準備：095 欄位提取

### 095 欄位結構

MARC 095 欄位是某些圖書館系統用於內嵌館藏/單冊資訊的自訂欄位：

```
095 $a 圖書館 $b 館藏位置 $c 條碼 $d 分類號 $e 著者號 $p 資料類型 $t 索書號類型 $y 年份 $z 完整索書號
```

### 提取流程概述

使用 Python 腳本從 MARC 檔案中提取 095 欄位，產生 Holdings TSV 和 Items TSV 兩個檔案。提取後的 Holdings TSV 包含以下欄位：

```tsv
bib_id	location	call_number	call_number_type
001234	LB	312.4 7821	DDC
001234	LB3F	005.133 P999	DDC
005678	AA	QA76.73	LCC
```

> 完整的提取步驟、腳本程式碼及驗證方法，請參閱 [095_holdings_items_migration_workflow.md](095_holdings_items_migration_workflow.md)。

---

## 9. HRID 處理

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

> **注意**：`resetHridSettings: true` 僅在 `updateHridSettings: true` 時生效。重置會在執行**開始前**將 HRID 計數器歸零，僅建議在首次正式遷移時使用。

---

## 10. 已知問題與限制

### 10.1 HoldingsCsvTransformer 檔案路徑 Bug

**問題**：HoldingsCsvTransformer 的來源檔案路徑被 hardcoded 為 `source_data/items/`，而非預期的 `source_data/holdings/`。

**原因**：`holdings_csv_transformer.py` 中兩處使用了 `self.folder_structure.data_folder / "items"` 而非 `self.folder_structure.legacy_records_folder`。

**影響**：即使日誌顯示 `Source records files folder is .../source_data/holdings`，實際搜尋路徑卻是 `source_data/items/`。

**Workaround**：將 Holdings TSV 檔案複製到 `source_data/items/` 目錄：

```bash
cp source_data/holdings/holdings_from_095.tsv source_data/items/
```

> 詳細分析請參閱 [folio_migration_tools_issue_holdings_csv_path.md](folio_migration_tools_issue_holdings_csv_path.md)。

### 10.2 Instance 必須先存在

Holdings 記錄依賴 Instance UUID。HoldingsCsvTransformer 會透過 `instances_id_map.json` 查找 Mapping 中 `instanceId` 對應的 Legacy ID，將其轉換為 Instance UUID。

**必要的執行順序**：

```
1. BibsTransformer (transform_bibs)          → 產出 instances_id_map.json
2. BatchPoster (post_instances)              → 將 Instances 匯入 FOLIO
3. HoldingsCsvTransformer (holdings_from_095) → 使用 instances_id_map.json
4. BatchPoster (post_holdings)               → 將 Holdings 匯入 FOLIO
```

如果跳過步驟 1，或 `instances_id_map.json` 不存在，HoldingsCsvTransformer 將無法建立 Holdings 與 Instance 的關聯。

### 10.3 測試階段 HRID 設定建議

- 使用 `"updateHridSettings": false` 避免每次測試都推高 FOLIO 的 HRID 計數器
- `"resetHridSettings": true` 僅在首次正式遷移時使用，測試階段不建議
- 若測試時不慎推高了計數器，可透過 FOLIO Settings → Inventory → HRID handling 手動調整

---

## 11. 常見問題排解

### 11.1 找不到來源檔案

```
CRITICAL    None of the files listed in task configuration found in
.../source_data/items. Listed files: holdings_from_095.tsv
```

**原因**：檔案路徑 Bug（見 [10.1](#101-holdingscsvtransformer-檔案路徑-bug)）

**解決**：將 TSV 檔複製到 `source_data/items/` 目錄。

### 11.2 Holdings type not found in FOLIO

```
Holdings type with ID xxx not found in FOLIO.
```

**原因**：`fallbackHoldingsTypeId` 的 UUID 在 FOLIO 租戶中不存在。

**解決**：透過 Web Portal 的 FOLIO Reference Data 查詢正確的 Holdings Type UUID。

### 11.3 Merge criteria is not a property of a holdingsrecord

```
CRITICAL    Merge criteria(s) is not a property of a holdingsrecord: xxx
```

**原因**：`holdingsMergeCriteria` 中包含了 FOLIO Holdings Schema 中不存在的屬性名稱。

**解決**：檢查拼寫，確保使用正確的 FOLIO Holdings 屬性名稱（如 `instanceId`、`permanentLocationId`、`callNumber`）。

### 11.4 No instance id in parsed record

```
TransformationRecordFailedError: No instance id in parsed record
```

**原因**：Holdings Mapping 中 `instanceId` 對應的 legacy_field 值無法在 `instances_id_map.json` 中找到。

**解決**：
1. 確認 BibsTransformer 已執行並產出 `instances_id_map.json`
2. 確認 Mapping 中 `instanceId` 的 `legacy_field` 值與 BibsTransformer 使用的 Legacy ID 格式一致

### 11.5 認證失敗 (401 Unauthorized)

**原因**：FOLIO 帳密錯誤或環境變數未設定。

**解決**：
1. 確認 `FOLIO_MIGRATION_TOOLS_FOLIO_PASSWORD` 和 `FOLIO_MIGRATION_TOOLS_OKAPI_PASSWORD` 環境變數已設定
2. 確認 `okapiUsername` 在 `libraryInformation` 中已填寫
3. 若使用 Web Portal，確認 Credentials 頁面中的帳號密碼正確

### 11.6 Source data file 欄位不匹配

```
KeyError: 'location'
```

**原因**：TSV 檔案的欄位名稱與 Holdings Mapping JSON 中的 `legacy_field` 不一致。

**解決**：檢查 TSV 檔案的標題列欄位名稱，確保與 Mapping 中的 `legacy_field` 完全一致（大小寫敏感）。

---

## 12. 相關文件

| 文件 | 說明 |
|------|------|
| [batch_poster_guide.md](batch_poster_guide.md) | Holdings 匯入 FOLIO 的操作指南 |
| [holdings_items_migration_guide.md](holdings_items_migration_guide.md) | 完整 Holdings/Items 遷移概覽 |
| [095_holdings_items_migration_workflow.md](095_holdings_items_migration_workflow.md) | 095 欄位提取詳細流程 |
| [bibs_transformer_guide.md](bibs_transformer_guide.md) | 前置步驟 — Instances 轉檔 |
| [folio_migration_tools_issue_holdings_csv_path.md](folio_migration_tools_issue_holdings_csv_path.md) | 檔案路徑 Bug 詳細記錄 |
| [task-config-parameters.md](task-config-parameters.md) | 所有任務類型的參數參考 |

---

## 附錄：檔案位置總覽

| 檔案 | 位置 | 說明 |
|------|------|------|
| 任務配置 | `mapping_files/migration_config.json` | 任務定義與參數 |
| 圖書館配置 | `mapping_files/library_config.json` | FOLIO 連線資訊 |
| Holdings Mapping | `mapping_files/holdings_mapping_095.json` | 欄位對應 JSON |
| 位置對應 | `mapping_files/locations.tsv` | 位置代碼對應 |
| 索書號類型對應 | `mapping_files/call_number_type_mapping.tsv` | 索書號類型對應 |
| 來源資料 | `iterations/{iter}/source_data/items/` | Holdings TSV 輸入（因路徑 Bug） |
| 結果檔案 | `iterations/{iter}/results/` | 轉檔後的 JSON |
| 報告檔案 | `iterations/{iter}/reports/` | 執行報告 |
| ID 對應表 | `iterations/{iter}/results/holdings_id_map.json` | Legacy ↔ FOLIO UUID |
