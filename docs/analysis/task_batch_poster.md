# BatchPoster 任務分析

## 概述

BatchPoster 負責將 Transform 階段產生的 FOLIO JSON 檔案批次寫入 FOLIO 平台。它是所有 Transform 任務的下游步驟，支援多種物件類型，可批次或逐筆 POST，並具備 upsert、失敗重跑等功能。

## 任務類型

- **類別**: Post（批次寫入）
- **migration_task_type**: `BatchPoster`
- **支援物件類型**: Instances, Holdings, Items, Users, Extradata, Organizations, Orders

## 工作流程

```
FOLIO JSON 檔案（由 Transform 產生）
    ↓ 讀取 JSON 記錄
    ↓ 組裝 batch（依 batch_size）
    ↓ POST 到 FOLIO API
    ↓ 處理失敗記錄（寫入 failed_recs）
    ↓ （選用）以 batch_size=1 重跑失敗記錄
記錄寫入 FOLIO 平台
```

## 呼叫的 FOLIO API

### 依物件類型使用的 API Endpoint

| object_type | API Endpoint (POST) | Query Endpoint (GET) | 批次模式 |
|---|---|---|---|
| `Instances` | `/instance-storage/batch/synchronous` | `/instance-storage/instances` | 批次 |
| `Holdings` | `/holdings-storage/batch/synchronous` | `/holdings-storage/holdings` | 批次 |
| `Items` | `/item-storage/batch/synchronous` | `/item-storage/items` | 批次 |
| `Users` | `/user-import` | — | 批次 |
| `Extradata` | 依 object_name 動態決定（見下表） | — | 逐筆 |
| `Organizations` | `/organizations/organizations` | — | 逐筆 |
| `Orders` | `/orders/composite-orders` | — | 逐筆 |

### Unsafe 模式

設定 `use_safe_inventory_endpoints: false` 時：

| object_type | Unsafe Endpoint |
|---|---|
| `Instances` | `/instance-storage/batch/synchronous-unsafe` |
| `Holdings` | `/holdings-storage/batch/synchronous-unsafe` |
| `Items` | `/item-storage/batch/synchronous-unsafe` |

> Unsafe 模式繞過 Optimistic Locking，速度更快但不檢查版本衝突。

### Extradata 物件類型對應

BatchPoster 以 `object_type: "Extradata"` 模式處理時，每行 extradata 的第一個 tab 前的名稱決定目標 API：

| object_name | API Endpoint |
|---|---|
| `account` | `/accounts` |
| `feefineaction` | `/feefineactions` |
| `boundwithPart` | `/inventory-storage/bound-with-parts` |
| `precedingSucceedingTitles` | `/preceding-succeeding-titles` |
| `notes` | `/notes` |
| `course` | `/coursereserves/courses` |
| `courselisting` | `/coursereserves/courselistings` |
| `instructor` | `/coursereserves/courselistings/{id}/instructors` |
| `contacts` | `/organizations-storage/contacts` |
| `interfaces` | `/organizations-storage/interfaces` |
| `interfaceCredential` | `/organizations-storage/interfaces/{id}/credentials` |
| `bankInfo` | `/organizations/banking-information` |

### Upsert 相關

| API Endpoint | HTTP Method | 用途 |
|---|---|---|
| Query Endpoint（如 `/instance-storage/instances`） | GET | 查詢現有記錄的 `_version`（upsert 時需要） |

## 輸入檔案

| 檔案 | 來源 | 說明 |
|---|---|---|
| `folio_instances.json` | Transform 產出 | Instance 記錄 |
| `folio_holdings.json` | Transform 產出 | Holdings 記錄 |
| `folio_items.json` | Transform 產出 | Item 記錄 |
| `folio_users.json` | Transform 產出 | User 記錄 |
| `extradata` | Transform 產出 | Fee/Fine 等 extradata |

## 輸出檔案

| 檔案 | 路徑 | 說明 |
|---|---|---|
| `failed_records` | `results/` | 寫入失敗的記錄 |
| `batch_poster_report.md` | `reports/` | 寫入報告（成功/失敗統計） |

## 關鍵設定

### 批次寫入 Instances

```json
{
    "name": "post_instances",
    "migration_task_type": "BatchPoster",
    "object_type": "Instances",
    "files": [{"file_name": "folio_instances.json"}],
    "batch_size": 250
}
```

### 批次寫入 Holdings

```json
{
    "name": "post_holdings",
    "migration_task_type": "BatchPoster",
    "object_type": "Holdings",
    "files": [{"file_name": "folio_holdings.json"}],
    "batch_size": 250
}
```

### 批次寫入 Items

```json
{
    "name": "post_items",
    "migration_task_type": "BatchPoster",
    "object_type": "Items",
    "files": [{"file_name": "folio_items.json"}],
    "batch_size": 250
}
```

### 批次寫入 Users

```json
{
    "name": "post_users",
    "migration_task_type": "BatchPoster",
    "object_type": "Users",
    "files": [{"file_name": "folio_users.json"}],
    "batch_size": 250
}
```

### 寫入 Extradata（Fee/Fines）

```json
{
    "name": "post_feefines",
    "migration_task_type": "BatchPoster",
    "object_type": "Extradata",
    "files": [{"file_name": "extradata"}],
    "batch_size": 1
}
```

### 設定說明

- **batch_size**: 每批次筆數。Inventory 建議 250，Users 建議 250，Extradata 固定 1
- **rerun_failed_records**: 是否以 batch_size=1 重跑失敗記錄（預設 true）
- **use_safe_inventory_endpoints**: 使用安全模式（預設 true，支援 Optimistic Locking）
- **upsert**: 若記錄已存在則更新（預設 false）
- **preserve_statistical_codes**: upsert 時保留現有統計代碼
- **preserve_administrative_notes**: upsert 時保留現有管理附註
- **patch_existing_records**: upsert 時只更新指定欄位（配合 patch_paths）

## 授權重試

BatchPoster 會自動處理 HTTP 401 錯誤：

1. 偵測到 401 → 呼叫 `folio_client.login()` 重新取得 token
2. 以新 token 重新 POST 同一批次

## 注意事項

- **執行順序**: 必須在對應的 Transform 完成後執行
- **Inventory 寫入順序**: Instances → Holdings → Items（有依賴關係）
- **Users 特殊 API**: `/user-import` 接受 `{users: [...], totalRecords: N}` 格式，自動處理 create/update
- **Extradata 逐筆寫入**: batch_size 設為 1，每行獨立 POST
- **重跑機制**: 失敗記錄會存到 `failed_records`，若 `rerun_failed_records: true` 會自動以 batch_size=1 重跑
- **大量記錄**: batch_size 過大可能導致 HTTP 413（Request Entity Too Large），建議不超過 500
- **Record count 驗證**: BatchPoster 會在寫入前後比較 FOLIO 中的記錄數量，報告差異
