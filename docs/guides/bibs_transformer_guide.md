# BibsTransformer 任務完整操作流程指南

## 概述

BibsTransformer 是 FOLIO Migration Tools 中用於將 MARC 書目記錄轉換為 FOLIO Instance 記錄的核心任務。本文件詳細說明其執行流程、配置需求及輸出結果。

---

## 1. 任務執行命令

### 基本命令格式

```bash
# 密碼透過環境變數傳遞，避免在 ps 輸出中暴露
export FOLIO_MIGRATION_TOOLS_FOLIO_PASSWORD="your_password"

python -m folio_migration_tools <config_path> <task_name> --base_folder_path <path>
```

### 實際範例

```bash
export FOLIO_MIGRATION_TOOLS_FOLIO_PASSWORD="your_password"

python -m folio_migration_tools \
    /path/to/client/mapping_files/migration_config.json \
    transform_bibs \
    --base_folder_path /path/to/client
```

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
    },
)
```

---

## 2. 配置檔案結構

### 2.1 migration_config.json 中的任務定義

```json
{
  "migrationTasks": [
    {
      "name": "transform_bibs",
      "migrationTaskType": "BibsTransformer",
      "useTenantMappingRules": true,
      "ilsFlavour": "tag001",
      "tags_to_delete": ["999"],
      "files": [
        {
          "file_name": "bibs.mrc",
          "suppressed": false
        }
      ],
      "hridHandling": "default",
      "deactivateLegacyMarcMappingForBibs": false
    }
  ]
}
```

### 2.2 關鍵參數說明

| 參數 | 類型 | 說明 |
|------|------|------|
| `name` | string | 任務名稱，用於執行和識別 |
| `migrationTaskType` | string | 必須為 `BibsTransformer` |
| `useTenantMappingRules` | boolean | 是否從 FOLIO 租戶取得 MARC 對應規則 |
| `ilsFlavour` | string | ILS 類型，決定 Legacy ID 提取方式 |
| `tags_to_delete` | array | 轉換前要刪除的 MARC 標籤 |
| `files` | array | 要處理的 MARC 檔案列表 |
| `hridHandling` | string | HRID 處理模式 |
| `deactivateLegacyMarcMappingForBibs` | boolean | 是否停用舊版 MARC 對應 |
| `addAdministrativeNotesWithLegacyIds` | boolean | 是否在 Instance 中加入含 Legacy ID 的管理備註 |
| `updateHridSettings` | boolean | 是否更新 FOLIO HRID 計數器（預設 `true`） |
| `resetHridSettings` | boolean | 是否重置 HRID 計數器至起始值（預設 `false`） |
| `createSourceRecords` | boolean | 是否產生 SRS 記錄（預設 `false`，與 `dataImportMarc` 互斥） |
| `dataImportMarc` | boolean | 是否產生 MARC 檔供 Data Import 匯入（預設 `true`，與 `createSourceRecords` 互斥） |

---

## 3. ILS Flavour 選項

ILS Flavour 決定如何從 MARC 記錄中提取 Legacy ID（原系統識別碼）。

### 支援的 ILS 類型

| ilsFlavour | 說明 | Legacy ID 來源 |
|------------|------|----------------|
| `voyager` | Ex Libris Voyager | 001 欄位 |
| `aleph` | Ex Libris Aleph | 001 欄位（去除前綴） |
| `sierra` | Innovative Sierra | 907$a 或 .b 欄位 |
| `koha` | Koha ILS | 999$c 或 001 |
| `millennium` | Innovative Millennium | 907$a |
| `symphony` | SirsiDynix Symphony | 001 欄位 |
| `tag001` | 通用 - 直接使用 001 | 001 欄位原值 |
| `tagf990a` | 自定義 990$a | 990$a 子欄位 |
| `custom` | 完全自定義 | 需額外配置 |

### 使用建議

- **大多數情況**：使用 `tag001` 最為通用
- **特定 ILS**：選擇對應的類型以確保正確提取 Legacy ID
- **自定義需求**：使用 `custom` 並配合額外的對應配置

---

## 4. HRID 處理模式

HRID（Human Readable ID）是 FOLIO Instance 的可讀識別碼。

### 可用選項

| 模式 | 說明 |
|------|------|
| `default` | FOLIO 自動產生 HRID（推薦） |
| `preserve001` | 保留 MARC 001 欄位作為 HRID |

### updateHridSettings 與 resetHridSettings

| 參數 | 預設值 | 說明 |
|------|--------|------|
| `updateHridSettings` | `true` | 執行後自動更新 FOLIO HRID 計數器，使後續產生的 HRID 不會與遷移資料衝突 |
| `resetHridSettings` | `false` | 執行前先將 HRID 計數器重置至起始值 |

### 測試 vs 正式遷移建議

| 階段 | updateHridSettings | resetHridSettings | 說明 |
|------|-------------------|-------------------|------|
| 測試階段 | `false` | `false` | 避免影響 FOLIO 計數器，方便反覆測試 |
| 正式遷移 | `true`（預設） | 視需求 | 確保計數器正確遞增，避免後續 HRID 衝突 |

### 注意事項

- **`default`**：最安全的選項，避免 HRID 衝突
- **`preserve001`**：需確保 001 欄位值唯一且符合 FOLIO HRID 格式要求
- **HRID 計數器衝突風險**：若測試時 `updateHridSettings: true`，每次執行都會推高計數器。正式遷移前若需重置，可設定 `resetHridSettings: true` 或透過 FOLIO 管理介面手動調整

---

## 5. MARC 對應規則來源（重要）

### 5.1 規則取得方式

**關鍵發現**：MARC 對應規則**不是**儲存在本地 `mapping_files` 目錄中，而是在執行時從 FOLIO 租戶的 API 動態取得。

### 5.2 API 端點

```
GET {folio_url}/mapping-rules/marc-bib
Headers:
  x-okapi-tenant: {tenant_id}
  x-okapi-token: {auth_token}
```

### 5.3 規則內容結構

```json
{
  "rules": [
    {
      "field": "245",
      "rules": [
        {
          "conditions": [
            {
              "type": "set_instance_title_type_name",
              "value": "title"
            }
          ],
          "value": ""
        }
      ]
    }
  ]
}
```

### 5.4 配置選項

在 `migration_config.json` 中：

```json
{
  "useTenantMappingRules": true
}
```

- **`true`**（推薦）：從 FOLIO 租戶取得最新對應規則
- **`false`**：使用內建的預設對應規則

---

## 6. 檔案處理流程

### 6.1 輸入檔案

位置：`{client_path}/iterations/{iteration}/source_data/`

```
source_data/
└── bibs.mrc          # MARC 書目記錄檔
```

### 6.2 處理步驟

```
┌─────────────────────────────────────────────────────────────┐
│  1. 讀取 migration_config.json 中的任務配置                   │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  2. 連線 FOLIO 並取得認證 Token                               │
│     POST {folio_url}/authn/login                            │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  3. 取得 MARC 對應規則                                        │
│     GET {folio_url}/mapping-rules/marc-bib                  │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  4. 逐筆讀取 MARC 記錄                                        │
│     - 刪除指定的 MARC 標籤 (tags_to_delete)                   │
│     - 提取 Legacy ID (依據 ilsFlavour)                       │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  5. 套用 MARC 對應規則，轉換為 FOLIO Instance                  │
│     - 標題 (title)                                          │
│     - 識別碼 (identifiers)                                   │
│     - 貢獻者 (contributors)                                  │
│     - 出版資訊 (publication)                                 │
│     - 等等...                                                │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  6. 處理 HRID                                                │
│     - default: 留空由 FOLIO 自動產生                          │
│     - preserve001: 使用 001 欄位值                           │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│  7. 輸出結果檔案                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 7. 輸出檔案

### 7.1 結果檔案位置

```
{client_path}/iterations/{iteration}/
├── results/
│   ├── folio_instances_{task_name}.json              # FOLIO Instance 記錄
│   ├── folio_marc_instances_{task_name}.mrc          # MARC 輸出（dataImportMarc: true 時產生）
│   └── instances_id_map.json                         # Legacy ID ↔ FOLIO UUID 對應表
│
└── reports/
    └── report_{task_name}.md                         # 轉換報告
```

### 7.2 Instance JSON 格式

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "hrid": "in00000001",
  "source": "MARC",
  "title": "書名範例",
  "indexTitle": "書名範例",
  "instanceTypeId": "6312d172-f0cf-40f6-b27d-9fa8feaf332f",
  "contributors": [
    {
      "name": "作者名",
      "contributorTypeId": "...",
      "contributorNameTypeId": "...",
      "primary": true
    }
  ],
  "identifiers": [
    {
      "identifierTypeId": "...",
      "value": "ISBN-值"
    }
  ],
  "publication": [
    {
      "publisher": "出版社",
      "dateOfPublication": "2024",
      "place": "出版地"
    }
  ],
  "_version": 1
}
```

### 7.3 報告檔案內容

報告檔案 (`report_{task_name}.md`) 包含：

- 處理統計
  - 總記錄數
  - 成功轉換數
  - 失敗數
- 錯誤詳情
- 警告訊息
- 對應規則使用統計

---

## 8. 常見問題排解

### 8.1 認證失敗 (401 Unauthorized)

**原因**：FOLIO 帳密錯誤或 `okapiUsername` 未設定

**解決方案**：
1. 確認 Credentials 頁面中的帳號密碼正確
2. 確認 `library_config.json` 中的 `okapiUsername` 已填寫
3. 重新儲存 Credentials，系統會自動更新配置檔

### 8.2 找不到 MARC 檔案

**原因**：檔案未放置在正確位置

**解決方案**：
確認檔案位於 `iterations/{iteration}/source_data/` 目錄下

### 8.3 Legacy ID 提取錯誤

**原因**：`ilsFlavour` 設定與實際 MARC 結構不符

**解決方案**：
1. 檢查 MARC 記錄的 001 欄位格式
2. 選擇正確的 `ilsFlavour` 或使用 `tag001`

### 8.4 HRID 衝突

**原因**：使用 `preserve001` 但 001 欄位值重複

**解決方案**：
1. 改用 `default` 讓 FOLIO 自動產生
2. 或確保 001 欄位值唯一

---

## 9. 已知問題與限制

> 詳細的問題分析與原始碼追蹤，請參閱 [folio_migration_tools_issues.md](../issues/folio_migration_tools_issues.md)。

### 9.1 `createSourceRecords` 與 `dataImportMarc` 互斥

`createSourceRecords` 只有在 `dataImportMarc: false` 時才會實際生效。這是因為 `rules_mapper_base.py` 中的邏輯要求兩個條件同時滿足：

```python
self.create_source_records = (
    self.task_configuration.create_source_records
    and not self.task_configuration.data_import_marc
)
```

由於 `dataImportMarc` 預設為 `true`，僅設定 `createSourceRecords: true` 而不明確設定 `dataImportMarc: false` 時，SRS JSON 檔案不會被產生。

### 9.2 `dataImportMarc: false` 時 Subject Source 錯誤

當設定 `dataImportMarc: false` 時，執行可能在第一筆記錄即失敗，錯誤訊息如：

```
CRITICAL Subject source not found for  =650  \0$aComputer science.
```

即使 FOLIO 租戶中已正確配置 Subject Sources 和 Mapping Rules，工具仍無法正確解析。此問題可能與 mapping rule 的 indicator 比對邏輯有關。

### 9.3 BatchPoster 不支援 `objectType: "SRS"`

folio_migration_tools 1.10.2 的 BatchPoster 已從支援的 `objectType` 清單中移除 `SRS`。即使成功產生 SRS JSON 檔案，也無法透過 BatchPoster 匯入 FOLIO。

### 9.4 目前 Workaround

使用預設的 `dataImportMarc: true`（或不設定此參數），透過以下兩步驟完成遷移：

1. **BatchPoster 匯入 Instances**：使用 `folio_instances_{task_name}.json`
2. **FOLIO Data Import UI 匯入 MARC/SRS**：手動上傳 `folio_marc_instances_{task_name}.mrc`

```json
{
  "name": "transform_bibs",
  "migrationTaskType": "BibsTransformer",
  "dataImportMarc": true,
  "ilsFlavour": "tag001",
  "hridHandling": "default",
  "updateHridSettings": false
}
```

> **注意**：此方式無法完全自動化，SRS 部分需手動操作。

---

## 10. Web Portal 執行流程

### 10.1 透過介面執行

1. 進入客戶專案詳情頁
2. 點擊「Execute Tasks」按鈕
3. 選擇要執行的任務（如 `transform_bibs`）
4. 選擇 Iteration
5. 確認使用儲存的 Credentials
6. 點擊「Start Execution」

### 10.2 即時監控

- 即時顯示執行日誌
- 進度條顯示處理進度
- 可隨時取消執行

### 10.3 查看結果

執行完成後：
1. 進入 Execution History 查看歷史記錄
2. 點擊特定執行查看詳情
3. 下載輸出檔案（Instance JSON、報告等）

---

## 11. 最佳實踐

### 11.1 測試建議

1. **小量測試先行**：先用少量記錄（如 10-100 筆）測試
2. **檢查輸出品質**：確認轉換後的 Instance 記錄格式正確
3. **驗證 Legacy ID**：確保 Legacy ID 正確提取，後續 Holdings/Items 關聯需要

### 11.2 配置建議

```json
{
  "useTenantMappingRules": true,
  "ilsFlavour": "tag001",
  "hridHandling": "default",
  "tags_to_delete": ["999"]
}
```

### 11.3 大量資料處理

- 分批處理：將大型 MARC 檔案分成多個小檔案
- 監控資源：注意記憶體使用
- 錯誤處理：檢查報告中的錯誤並修正來源資料

---

## 下一步：匯入 FOLIO

BibsTransformer 完成後，需使用 BatchPoster 將產出的 Instance 記錄匯入 FOLIO。請參閱 [batch_poster_guide.md](batch_poster_guide.md)。

---

## 附錄：相關檔案位置

| 檔案 | 位置 | 說明 |
|------|------|------|
| 任務配置 | `mapping_files/migration_config.json` | 任務定義與參數 |
| 圖書館配置 | `mapping_files/library_config.json` | FOLIO 連線資訊 |
| 來源資料 | `iterations/{iter}/source_data/` | MARC 輸入檔案 |
| 結果檔案 | `iterations/{iter}/results/` | 轉換後的 JSON |
| 報告檔案 | `iterations/{iter}/reports/` | 執行報告 |
| 執行日誌 | `iterations/{iter}/logs/` | 詳細執行日誌 |
