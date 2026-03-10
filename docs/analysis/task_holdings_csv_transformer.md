# HoldingsCsvTransformer 任務分析

## 概述

HoldingsCsvTransformer 將 CSV/TSV 格式的館藏記錄轉換為 FOLIO Holdings 物件。它依據 JSON 欄位映射檔和 TSV 參考資料對應表，將來源系統的館藏資料（館藏地、索書號等）轉換為符合 FOLIO Holdings Schema 的 JSON 物件。

## 任務類型

- **類別**: Transform（轉換）
- **migration_task_type**: `HoldingsCsvTransformer`
- **FOLIO 物件類型**: Holdings Record
- **來源資料格式**: TSV（Tab-Separated Values）

## 工作流程

```
holdings.tsv（來源資料）
    ↓ 讀取 TSV 記錄
    ↓ 套用 holdingsrecord_mapping.json 欄位映射
    ↓ 查詢 locations.tsv 對應 → 透過 API 取得 Location UUID
    ↓ 查詢 call_number_type_mapping.tsv → 取得 Call Number Type UUID
    ↓ 讀取 instance_id_map.json → 關聯到 Instance
    ↓ 依合併條件合併重複 Holdings
    ↓ 產生 FOLIO UUID
FOLIO Holdings JSON 檔案
```

## 呼叫的 FOLIO API

### 初始化階段（讀取參考資料）

| API Endpoint | HTTP Method | 用途 |
|---|---|---|
| `/holdings-types` | GET | 取得所有 Holdings 類型（用於設定 holdingsTypeId） |
| `/holdings-sources` | GET | 取得 Holdings 來源清單（FOLIO、MARC 等） |
| `/locations` | GET | 取得所有館藏地點（用於 RefDataMapping，驗證 locations.tsv 中的 `folio_code` 是否存在） |
| `/call-number-types` | GET | 取得所有索書號類型（用於 RefDataMapping，驗證 call_number_type_mapping.tsv） |
| `/ill-policies` | GET | 取得館際互借政策 |
| `/holdings-note-types` | GET | 取得 Holdings 附註類型 |
| `/statistical-codes` | GET | 取得統計代碼（若有設定） |
| `/hrid-settings-storage/hrid-settings` | GET | 取得 HRID 計數器 |
| `/holdings-storage/holdings` | GET | 取得 Holdings Schema（用於驗證 merge criteria） |

### 結束階段

| API Endpoint | HTTP Method | 用途 |
|---|---|---|
| `/hrid-settings-storage/hrid-settings` | PUT | 更新 HRID 計數器（若 `update_hrid_settings: true`） |

### GitHub（非 FOLIO API）

| 來源 | 用途 |
|---|---|
| `folio-org/mod-inventory-storage/ramls/holdingsrecord.json` | 下載 Holdings JSON Schema |

## 輸入檔案

| 檔案 | 來源目錄 | 說明 |
|---|---|---|
| `holdings.tsv` | `source_data/items/`⚠️ | 館藏來源資料（TSV 格式） |
| `holdingsrecord_mapping.json` | `mapping_files/` | 欄位映射定義 |
| `locations.tsv` | `mapping_files/` | 館藏地對應表（legacy_code → folio_code） |
| `call_number_type_mapping.tsv` | `mapping_files/` | 索書號類型對應表 |
| `instance_id_map.json` | `results/`（由 BibsTransformer 產生） | Instance ID 對應表 |

> ⚠️ **已知 Bug**: HoldingsCsvTransformer 的 `process_single_file()` 強制從 `source_data/items/` 讀取檔案，而非使用 `legacy_records_folder`。需將 `holdings.tsv` 放在 `source_data/items/` 目錄下。

## 輸出檔案

| 檔案 | 路徑 | 說明 |
|---|---|---|
| `folio_holdings.json` | `results/` | FOLIO Holdings JSON（每行一筆） |
| `holdings_id_map.json` | `results/` | Legacy ID → Holdings UUID 對應表（供 Items 使用） |
| `holdings_transformation.md` | `reports/` | 轉換報告 |

## 關鍵設定

```json
{
    "name": "transform_holdings",
    "migration_task_type": "HoldingsCsvTransformer",
    "hrid_handling": "default",
    "files": [{"file_name": "holdings.tsv", "suppress": false}],
    "holdings_map_file_name": "holdingsrecord_mapping.json",
    "location_map_file_name": "locations.tsv",
    "call_number_type_map_file_name": "call_number_type_mapping.tsv",
    "default_call_number_type_name": "Library of Congress classification",
    "fallback_holdings_type_id": "03c9c400-b9e3-4a07-ac10-ebce228a9b6b",
    "holdings_type_uuid_for_boundwiths": "",
    "previously_generated_holdings_files": [],
    "reset_hrid_settings": false,
    "update_hrid_settings": true
}
```

### 設定說明

- **fallback_holdings_type_id**: 預設 Holdings 類型的 UUID（當來源無法對應時使用）
- **holdings_merge_criteria**: 合併條件（預設 `["instanceId", "permanentLocationId", "callNumber"]`），相同條件的 Holdings 會合併為一筆
- **previously_generated_holdings_files**: 載入先前已產生的 Holdings 檔案（用於避免重複）

## 注意事項

- 必須在 BibsTransformer 之後執行（依賴 `instance_id_map.json`）
- 必須在 ItemsTransformer 之前執行（產出 `holdings_id_map.json`）
- 來源檔案路徑 Bug：必須將 `holdings.tsv` 放在 `source_data/items/` 目錄
- Holdings 會依 merge criteria 自動合併，一個 Instance 可能有多個 Holdings（不同館藏地或索書號）
