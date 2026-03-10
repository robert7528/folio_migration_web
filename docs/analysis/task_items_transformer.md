# ItemsTransformer 任務分析

## 概述

ItemsTransformer 將 CSV/TSV 格式的館藏單品記錄轉換為 FOLIO Item 物件。它依據 JSON 欄位映射檔和多個 TSV 參考資料對應表，將來源系統的單品資料（條碼、資料類型、借閱類型、狀態等）轉換為符合 FOLIO Item Schema 的 JSON 物件。

## 任務類型

- **類別**: Transform（轉換）
- **migration_task_type**: `ItemsTransformer`
- **FOLIO 物件類型**: Item
- **來源資料格式**: TSV（Tab-Separated Values）

## 工作流程

```
items.tsv（來源資料）
    ↓ 讀取 TSV 記錄
    ↓ 套用 item_mapping.json 欄位映射
    ↓ 查詢 locations.tsv → 透過 API 取得 Location UUID
    ↓ 查詢 material_types.tsv → 透過 API 取得 Material Type UUID
    ↓ 查詢 loan_types.tsv → 透過 API 取得 Loan Type UUID
    ↓ 查詢 item_statuses.tsv → 對應 FOLIO Item Status
    ↓ 查詢 call_number_type_mapping.tsv → 取得 Call Number Type UUID
    ↓ 讀取 holdings_id_map.json → 關聯到 Holdings Record
    ↓ 產生 FOLIO UUID
FOLIO Item JSON 檔案
```

## 呼叫的 FOLIO API

### 初始化階段（讀取參考資料）

| API Endpoint | HTTP Method | 用途 |
|---|---|---|
| `/locations` | GET | 取得所有館藏地點（驗證 locations.tsv 的 `folio_code`） |
| `/material-types` | GET | 取得所有資料類型（驗證 material_types.tsv 的 `folio_name`） |
| `/loan-types` | GET | 取得所有借閱類型（驗證 loan_types.tsv 的 `folio_name`） |
| `/call-number-types` | GET | 取得所有索書號類型（驗證 call_number_type_mapping.tsv） |
| `/item-note-types` | GET | 取得 Item 附註類型 |
| `/statistical-codes` | GET | 取得統計代碼（若有設定） |
| `/hrid-settings-storage/hrid-settings` | GET | 取得 HRID 計數器 |

### GitHub（非 FOLIO API）

| 來源 | 用途 |
|---|---|
| `folio-org/mod-inventory-storage/ramls/item.json` | 下載 Item JSON Schema |

### 結束階段

| API Endpoint | HTTP Method | 用途 |
|---|---|---|
| `/hrid-settings-storage/hrid-settings` | PUT | 更新 HRID 計數器（若 `update_hrid_settings: true`） |

## 輸入檔案

| 檔案 | 來源目錄 | 說明 |
|---|---|---|
| `items.tsv` | `source_data/items/` | 單品來源資料 |
| `item_mapping.json` | `mapping_files/` | 欄位映射定義 |
| `locations.tsv` | `mapping_files/` | 館藏地對應表（legacy_code → folio_code） |
| `material_types.tsv` | `mapping_files/` | 資料類型對應表（legacy_name → folio_name） |
| `loan_types.tsv` | `mapping_files/` | 借閱類型對應表（legacy_name → folio_name） |
| `item_statuses.tsv` | `mapping_files/` | 單品狀態對應表（legacy_status → folio_name） |
| `call_number_type_mapping.tsv` | `mapping_files/` | 索書號類型對應表 |
| `holdings_id_map.json` | `results/`（由 HoldingsCsvTransformer 產生） | Holdings ID 對應表 |

## 輸出檔案

| 檔案 | 路徑 | 說明 |
|---|---|---|
| `folio_items.json` | `results/` | FOLIO Item JSON（每行一筆） |
| `item_transformation.md` | `reports/` | 轉換報告 |

## 關鍵設定

```json
{
    "name": "transform_items",
    "migration_task_type": "ItemsTransformer",
    "hrid_handling": "default",
    "files": [{"file_name": "items.tsv", "suppress": false}],
    "items_mapping_file_name": "item_mapping.json",
    "location_map_file_name": "locations.tsv",
    "material_types_map_file_name": "material_types.tsv",
    "loan_types_map_file_name": "loan_types.tsv",
    "item_statuses_map_file_name": "item_statuses.tsv",
    "call_number_type_map_file_name": "call_number_type_mapping.tsv",
    "default_call_number_type_name": "Library of Congress classification",
    "reset_hrid_settings": false,
    "update_hrid_settings": true
}
```

### 設定說明

- **temp_location_map_file_name**: 臨時館藏地對應（選用）
- **temp_loan_types_map_file_name**: 臨時借閱類型對應（選用）
- **boundwith_relationship_file_path**: Bound-with 關係檔（Voyager 格式，選用）

## 注意事項

- 必須在 HoldingsCsvTransformer 之後執行（依賴 `holdings_id_map.json`）
- Item 透過 `holdingsRecordId` 與 Holdings 關聯
- Item 狀態對應：來源系統狀態需對應到 FOLIO 允許的狀態名稱（Available, Checked out, In transit 等）
- `folio_name` 值在 TSV 中必須完全匹配 FOLIO 系統中的名稱（大小寫敏感）
