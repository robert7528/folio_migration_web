# BatchPoster 任務完整操作流程指南

## 概述

BatchPoster 是 FOLIO Migration Tools 中用於將 Transformer 產出的 JSON 記錄批次匯入 FOLIO 的通用任務。支援 Instances、Holdings、Items、Users、Orders 等多種物件類型。

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
    post_instances \
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
      "name": "post_instances",
      "migrationTaskType": "BatchPoster",
      "objectType": "Instances",
      "batchSize": 500,
      "files": [
        {
          "file_name": "folio_instances_transform_bibs.json"
        }
      ]
    }
  ]
}
```

### 2.2 必要參數

| 參數 | 類型 | 說明 |
|------|------|------|
| `name` | string | 任務名稱，用於執行和識別 |
| `migrationTaskType` | string | 固定為 `"BatchPoster"` |
| `objectType` | string | 物件類型（見第 3 節） |
| `batchSize` | integer | 每批次的記錄數量 |
| `files` | array | 要匯入的 JSON 檔案列表（Transformer 的產出檔案） |

### 2.3 選用參數

| 參數 | 類型 | 預設值 | 說明 |
|------|------|--------|------|
| `rerunFailedRecords` | boolean | `true` | 是否自動重試失敗的批次 |
| `useSafeInventoryEndpoints` | boolean | `true` | 使用安全的 Inventory 端點（支援 Optimistic Locking） |
| `upsert` | boolean | `false` | 啟用 upsert 模式（存在時更新，不存在時新增） |
| `patchExistingRecords` | boolean | `false` | upsert 時使用 PATCH（部分更新）而非完整替換 |
| `patchPaths` | string[] | `[]` | PATCH 時要更新的欄位路徑列表（空陣列 = 更新所有欄位） |
| `preserveStatisticalCodes` | boolean | `false` | upsert 時是否保留現有統計代碼 |
| `preserveAdministrativeNotes` | boolean | `false` | upsert 時是否保留現有管理備註 |
| `preserveTemporaryLocations` | boolean | `false` | upsert 時是否保留 Item 的臨時館藏地 |
| `preserveTemporaryLoanTypes` | boolean | `false` | upsert 時是否保留 Item 的臨時借閱類型 |
| `preserveItemStatus` | boolean | `true` | upsert 時是否保留 Item 狀態 |
| `extradataEndpoints` | object | `{}` | Extradata 自訂端點字典 |

---

## 3. 支援的 objectType

### 3.1 類型列表

| objectType | API 端點 | 批次處理 | Upsert | 建議 batchSize |
|-----------|----------|---------|--------|---------------|
| `Instances` | `/instance-storage/batch/synchronous` | 是 | 是 | 250–500 |
| `Holdings` | `/holdings-storage/batch/synchronous` | 是 | 是 | 1000 |
| `Items` | `/item-storage/batch/synchronous` | 是 | 是 | 1000 |
| `ShadowInstances` | `/instance-storage/batch/synchronous` | 是 | 是 | 250–500 |
| `Users` | `/user-import` | 是 | 否 | 250 |
| `Authorities` | Authority 端點 | 是 | 是 | 250 |
| `Orders` | `/orders/composite-orders` | 否（逐筆） | 否 | 1 |
| `Organizations` | `/organizations/organizations` | 否（逐筆） | 否 | 1 |
| `Extradata` | 自訂端點 | 否（逐筆） | 是 | 1 |

### 3.2 不再支援的類型

| objectType | 狀態 | 替代方案 |
|-----------|------|---------|
| `SRS` | v1.10.2 已移除 | 使用 FOLIO Data Import UI 匯入 `.mrc` 檔案 |

> 詳細說明請參閱 [folio_migration_tools_issues.md](folio_migration_tools_issues.md) 問題三。

---

## 4. 常見 BatchPoster 任務配置範例

### 4.1 post_instances（匯入 Instance 記錄）

接續 BibsTransformer 的產出，將 Instance 記錄匯入 FOLIO。

```json
{
  "name": "post_instances",
  "migrationTaskType": "BatchPoster",
  "objectType": "Instances",
  "batchSize": 500,
  "files": [
    {
      "file_name": "folio_instances_transform_bibs.json"
    }
  ]
}
```

**來源檔案**：`iterations/{iteration}/results/folio_instances_transform_bibs.json`

> 搭配 BibsTransformer 使用的完整流程，請參閱 [bibs_transformer_guide.md](bibs_transformer_guide.md)。

### 4.2 post_holdings（匯入 Holdings 記錄）

```json
{
  "name": "post_holdings",
  "migrationTaskType": "BatchPoster",
  "objectType": "Holdings",
  "batchSize": 1000,
  "files": [
    {
      "file_name": "folio_holdings_transform_holdings.json"
    }
  ]
}
```

### 4.3 post_items（匯入 Item 記錄）

可同時匯入多個來源檔案，按順序處理：

```json
{
  "name": "post_items",
  "migrationTaskType": "BatchPoster",
  "objectType": "Items",
  "batchSize": 1000,
  "files": [
    {
      "file_name": "folio_items_transform_mfhd_items.json"
    },
    {
      "file_name": "folio_items_transform_csv_items.json"
    }
  ]
}
```

### 4.4 post_users（匯入 User 記錄）

```json
{
  "name": "post_users",
  "migrationTaskType": "BatchPoster",
  "objectType": "Users",
  "batchSize": 250,
  "files": [
    {
      "file_name": "folio_users_user_transform.json"
    }
  ]
}
```

### 4.5 post_orders（匯入 Order 記錄）

Orders 為複合物件，必須逐筆處理：

```json
{
  "name": "post_orders",
  "migrationTaskType": "BatchPoster",
  "objectType": "Orders",
  "batchSize": 1,
  "files": [
    {
      "file_name": "folio_orders_orders.json"
    }
  ]
}
```

### 4.6 post_extradata（匯入附加資料）

Extradata 處理備註、權限、費用、課程保留等非 Inventory 記錄，使用 `.extradata` 格式：

```json
{
  "name": "post_extradata",
  "migrationTaskType": "BatchPoster",
  "objectType": "Extradata",
  "batchSize": 1,
  "files": [
    {
      "file_name": "extradata_transform_bw_holdings.extradata"
    },
    {
      "file_name": "extradata_user_transform.extradata"
    }
  ]
}
```

---

## 5. 執行順序

BatchPoster 任務必須按照資料依賴關係的順序執行：

```
1. Authorities（如有）
        ↓
2. Instances ← Holdings 和 Items 依賴 Instance ID
        ↓
3. SRS/MARC（透過 FOLIO Data Import UI，非 BatchPoster）
        ↓
4. Holdings ← Items 依賴 Holdings ID
        ↓
5. Items
        ↓
6. Users
        ↓
7. Loans / Requests / Orders（依需求）
        ↓
8. Extradata（備註、費用、課程保留等）
```

> **關鍵**：Instances 必須先於 Holdings 和 Items 匯入，因為 Holdings 記錄中的 `instanceId` 和 Items 記錄中的 `holdingsRecordId` 必須指向已存在的記錄。

---

## 6. Upsert 模式

### 6.1 基本用法

當需要更新已存在的記錄時，啟用 upsert 模式：

```json
{
  "name": "update_instances",
  "migrationTaskType": "BatchPoster",
  "objectType": "Instances",
  "batchSize": 500,
  "upsert": true,
  "files": [
    {
      "file_name": "folio_instances_transform_bibs.json"
    }
  ]
}
```

### 6.2 部分更新（PATCH）

僅更新指定欄位，保留其他欄位不變：

```json
{
  "name": "patch_items",
  "migrationTaskType": "BatchPoster",
  "objectType": "Items",
  "batchSize": 1000,
  "upsert": true,
  "patchExistingRecords": true,
  "patchPaths": ["statisticalCodeIds", "administrativeNotes"],
  "files": [
    {
      "file_name": "folio_items_transform_items.json"
    }
  ]
}
```

### 6.3 資料保留選項

Upsert 時可選擇保留既有資料：

```json
{
  "upsert": true,
  "preserveStatisticalCodes": true,
  "preserveAdministrativeNotes": true,
  "preserveItemStatus": true,
  "preserveTemporaryLocations": true,
  "preserveTemporaryLoanTypes": true
}
```

---

## 7. 輸出檔案

### 7.1 結果檔案位置

```
{client_path}/iterations/{iteration}/
├── results/
│   └── failed_records_{object_type}.jsonl    # 匯入失敗的記錄（如有）
│
└── reports/
    └── report_{task_name}.md                 # 執行報告
```

### 7.2 報告檔案內容

報告檔案 (`report_{task_name}.md`) 包含：

- 處理統計
  - 總記錄數
  - 成功匯入數
  - 失敗數
- 失敗記錄詳情
- API 回應錯誤訊息

---

## 8. 常見問題排解

### 8.1 認證失敗 (401 Unauthorized)

**原因**：FOLIO 帳密錯誤或 Token 過期

**解決方案**：
1. 確認 Credentials 頁面中的帳號密碼正確
2. 確認 `library_config.json` 中的 `okapiUsername` 已填寫
3. 重新儲存 Credentials

### 8.2 找不到輸入檔案

**原因**：Transformer 尚未執行或檔案名稱不符

**解決方案**：
1. 確認對應的 Transformer 任務已執行完成
2. 確認 `files[].file_name` 與 `iterations/{iteration}/results/` 下的實際檔案名稱一致

### 8.3 Optimistic Locking 錯誤

**原因**：使用安全端點時記錄版本衝突

**解決方案**：
1. 確認沒有其他程序同時修改相同記錄
2. 如為測試環境可暫時設定 `"useSafeInventoryEndpoints": false`

### 8.4 objectType 不支援

**錯誤訊息**：

```
ERROR Wrong type. Only one of Extradata, Items, Holdings, Instances, ShadowInstances, Users, Organizations, Orders are allowed
```

**解決方案**：
確認 `objectType` 為上述支援的類型之一。注意 `SRS` 已不受支援。

### 8.5 批次匯入部分失敗

**原因**：部分記錄資料不合規（如缺少必要欄位、UUID 無效）

**解決方案**：
1. 檢查 `failed_records_{object_type}.jsonl` 中的失敗記錄
2. 若 `rerunFailedRecords: true`，系統會自動重試
3. 修正來源資料後重新執行 Transformer 和 BatchPoster

---

## 9. 已知問題與限制

### 9.1 SRS 不受支援

folio_migration_tools 1.10.2 已從 BatchPoster 移除 `objectType: "SRS"` 的支援。SRS/MARC 記錄需透過 FOLIO Data Import UI 手動匯入 `.mrc` 檔案。

> 詳見 [folio_migration_tools_issues.md](folio_migration_tools_issues.md) 問題三。

### 9.2 User 刪除後重新匯入失敗

在測試迭代中，已匯入的 User 經批次刪除後重新匯入會失敗。此問題涉及 FOLIO `/user-import` 端點的兩個行為。

#### 問題一：FOLIO 無法重用已刪除 User 的 UUID

**現象**：匯入帶有 `id` 欄位的 User JSON 時，全部失敗：

```
Failed to create new user with externalSystemId: d10055001@thu.edu.tw
```

**原因**：FOLIO 刪除 User 後，該 UUID 在系統中仍被保留（audit log、事件記錄等）。`/user-import` 端點無法以相同 UUID 重新建立 User。

**驗證結果**：

| 測試 | 結果 |
|------|------|
| 全新 user，不帶 `id` | 成功 |
| 全新 user，帶新 `id` | 成功 |
| 已刪除 user 的舊 `id` | **失敗** — 即使 Request Preference 已清除 |

#### 問題二：`/user-import` 先建 Request Preference 再建 User，失敗不回滾

**現象**：匯入帶有 `requestPreference` 的 User JSON 時，全部報錯：

```
Request preference for specified user already exists
```

但實際上 User 沒有被建立，Request Preference 卻被建立了。

**原因**：FOLIO `/user-import` 端點的處理順序：

1. 先為所有 User 建立 Request Preference（成功）
2. 再逐筆建立 User（因 UUID 衝突失敗）
3. **Request Preference 不會回滾**，變成孤兒資料

這會形成惡性循環 — 下次匯入時 Request Preference 已存在，又產生新的錯誤。

#### 影響範圍

| 場景 | 影響 |
|------|------|
| **正式遷移（首次匯入）** | **無影響** — 沒有舊 UUID，不會衝突 |
| **測試迭代（刪除 → 重新匯入）** | **必須處理** — 舊 UUID 無法重用 |

#### 解決方案：`removeIdAndRequestPreferences: true`

在 `migration_config.json` 的 UserTransformer 任務中設定：

```json
{
  "name": "transform_users",
  "migrationTaskType": "UserTransformer",
  "removeIdAndRequestPreferences": true,
  ...
}
```

此設定會移除產出 JSON 中的 `id` 和 `requestPreference` 欄位，匯入時 FOLIO 自行產生新 UUID，避免所有衝突。

**相關參數**：

| 參數 | 預設值 | 說明 |
|------|--------|------|
| `removeIdAndRequestPreferences` | `false` | 同時移除 User ID 和 Request Preference |
| `removeRequestPreferences` | `false` | 僅移除 Request Preference（保留 ID） |

> **注意**：僅用 `removeRequestPreferences: true`（保留 `id`）無法解決問題，因為舊 UUID 本身就無法重用。

#### 測試迭代的正確操作順序

1. **批次刪除 User**（Web Portal Deletion 功能）
2. **清除孤兒 Request Preference**：
   - Web Portal：`POST /api/clients/{client_code}/deletion/cleanup-request-preferences`
   - 或 API 批次刪除：
     ```bash
     curl -s "{OKAPI_URL}/request-preference-storage/request-preference?limit=200" \
       -H 'x-okapi-tenant: {TENANT}' -H "x-okapi-token: $TOKEN" \
       | jq -r '.requestPreferences[].id' > /tmp/rp_ids.txt
     while read id; do
       curl -s -X DELETE "{OKAPI_URL}/request-preference-storage/request-preference/$id" \
         -H 'x-okapi-tenant: {TENANT}' -H "x-okapi-token: $TOKEN"
     done < /tmp/rp_ids.txt
     ```
3. **設定 UserTransformer**：`"removeIdAndRequestPreferences": true`
4. **重新執行 transform_users**
5. **執行 post_users**
6. **驗證**：確認 Users 數量正確，Request Preferences 為 0

> **副作用**：每次匯入 User 都會取得新的 UUID。如果其他已匯入的記錄（如 Loans）引用舊的 User UUID，關聯會斷開。因此建議在測試迭代中，User 相關的資料（Loans 等）應在 User 匯入後重新匯入。

### 9.3 Holdings/Items/Instances 不回報 created/updated 數量

BatchPoster 對 Users 物件會回報 `created` 和 `updated` 的數量，但對 Holdings、Items、Instances 僅回報成功/失敗數，無法區分新建或更新。

> 詳見 [folio_migration_tools_issue_batchposter_created_updated.md](folio_migration_tools_issue_batchposter_created_updated.md)。

---

## 10. 最佳實踐

### 10.1 測試建議

1. **小量測試先行**：先用少量記錄測試，確認 API 連線和資料格式正確
2. **檢查失敗記錄**：每次執行後檢查報告和 `failed_records` 檔案
3. **注意執行順序**：嚴格遵守 Instances → Holdings → Items 的順序

### 10.2 配置建議

```json
{
  "migrationTaskType": "BatchPoster",
  "objectType": "Instances",
  "batchSize": 500,
  "rerunFailedRecords": true,
  "useSafeInventoryEndpoints": true
}
```

### 10.3 大量資料處理

- **調整 batchSize**：過大可能導致 API timeout，過小則效率低
- **監控記憶體**：大量記錄時注意伺服器記憶體使用
- **分階段匯入**：可將檔案分批，透過多個 BatchPoster 任務依序處理

---

## 附錄：完整遷移流程中的 BatchPoster 位置

```
┌─────────────────────────────────────────────────────────┐
│  Transform 階段                                          │
│  BibsTransformer → folio_instances_*.json               │
│  HoldingsTransformer → folio_holdings_*.json            │
│  ItemsTransformer → folio_items_*.json                  │
│  UserTransformer → folio_users_*.json                   │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│  Load 階段（BatchPoster）                                │
│  post_instances → FOLIO Instances                       │
│  post_holdings  → FOLIO Holdings                        │
│  post_items     → FOLIO Items                           │
│  post_users     → FOLIO Users                           │
│  post_extradata → FOLIO Notes / Fees / Courses          │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│  手動步驟                                                │
│  FOLIO Data Import UI ← folio_marc_instances_*.mrc      │
└─────────────────────────────────────────────────────────┘
```

---

## 相關文件

| 文件 | 說明 |
|------|------|
| [bibs_transformer_guide.md](bibs_transformer_guide.md) | BibsTransformer 操作指南 |
| [holdings_items_migration_guide.md](holdings_items_migration_guide.md) | Holdings/Items 遷移指南 |
| [task-config-parameters.md](task-config-parameters.md) | 所有任務類型的完整參數文件 |
| [folio_migration_tools_issues.md](folio_migration_tools_issues.md) | 已知問題報告 |
| [folio_migration_tools_issue_batchposter_created_updated.md](folio_migration_tools_issue_batchposter_created_updated.md) | BatchPoster created/updated 計數問題 |
