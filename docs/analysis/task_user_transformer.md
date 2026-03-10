# UserTransformer 任務分析

## 概述

UserTransformer 將 CSV/TSV 格式的讀者記錄轉換為 FOLIO User 物件。它依據 JSON 欄位映射檔和 TSV 參考資料對應表，將來源系統的讀者資料（姓名、條碼、讀者類型等）轉換為符合 FOLIO User Schema 的 JSON 物件。

## 任務類型

- **類別**: Transform（轉換）
- **migration_task_type**: `UserTransformer`
- **FOLIO 物件類型**: User
- **來源資料格式**: TSV 或 CSV

## 工作流程

```
users.tsv（來源資料）
    ↓ 讀取 TSV/CSV 記錄
    ↓ 套用 user_mapping.json 欄位映射
    ↓ 查詢 user_groups.tsv → 透過 API 取得 Patron Group UUID
    ↓ 處理地址（移除空地址、確保唯一 primary）
    ↓ 產生 FOLIO UUID
FOLIO User JSON 檔案
```

## 呼叫的 FOLIO API

### 初始化階段（讀取參考資料）

| API Endpoint | HTTP Method | 用途 |
|---|---|---|
| `/groups` | GET | 取得所有讀者群組（Patron Groups），用於 RefDataMapping 驗證 user_groups.tsv 的 `folio_group` 值 |
| `/departments` | GET | 取得所有部門（若有設定 departments_map_path） |
| `/addresstypes` | GET | 取得地址類型 |

### GitHub（非 FOLIO API）

| 來源 | 用途 |
|---|---|
| `folio-org/mod-user-import/ramls/schemas/userdataimport.json` | User import schema |
| `folio-org/mod-user-import/ramls/schemas/userImportRequestPreference.json` | Request preference schema |

## 輸入檔案

| 檔案 | 來源目錄 | 說明 |
|---|---|---|
| `users.tsv` | `source_data/users/` | 讀者來源資料 |
| `user_mapping.json` | `mapping_files/` | 欄位映射定義 |
| `user_groups.tsv` | `mapping_files/` | 讀者群組對應表（legacy_group → folio_group） |
| `departments.tsv` | `mapping_files/`（選用） | 部門對應表 |

## 輸出檔案

| 檔案 | 路徑 | 說明 |
|---|---|---|
| `folio_users.json` | `results/` | FOLIO User JSON（每行一筆） |
| `user_id_map.json` | `results/` | Legacy ID → User UUID 對應表 |
| `user_transformation.md` | `reports/` | 轉換報告 |

## 關鍵設定

```json
{
    "name": "transform_users",
    "migration_task_type": "UserTransformer",
    "user_mapping_file_name": "user_mapping.json",
    "group_map_path": "user_groups.tsv",
    "departments_map_path": "",
    "use_group_map": true,
    "user_file": {"file_name": "users.tsv"},
    "remove_id_and_request_preferences": false,
    "remove_request_preferences": false
}
```

### 設定說明

- **group_map_path**: 讀者群組對應表路徑（必填）
- **use_group_map**: 是否使用群組對應（預設 true）
- **remove_id_and_request_preferences**: 移除 user ID 和 request preferences（預設 false）
- **remove_request_preferences**: 僅移除 request preferences（預設 false）
- **remove_username**: 移除 username（注意：移除後不相容 mod-user-import）

## user_groups.tsv 格式

```tsv
legacy_group	folio_group
Faculty	faculty
Graduate Student	graduate
Undergraduate	undergrad
Staff	staff
```

- **legacy_group**: 來源系統的讀者類型名稱
- **folio_group**: FOLIO 中的 Patron Group 名稱（必須完全匹配 `/groups` API 回傳的 `group` 欄位值）

## 注意事項

- UserTransformer 獨立於 Inventory 轉換流程，可在任何時間執行
- 但必須在 LoansMigrator 和 RequestsMigrator 之前完成（因為借閱和預約需要 User 存在於 FOLIO）
- 地址處理邏輯：自動移除空地址、確保只有一個 primary address
- Email 警告：轉換時會提醒檢查是否包含真實 email（避免遷移後誤寄通知）
- BatchPoster 使用 `/user-import` API，支援 upsert（自動建立或更新）
