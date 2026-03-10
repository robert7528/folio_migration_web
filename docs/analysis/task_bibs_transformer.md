# BibsTransformer 任務分析

## 概述

BibsTransformer 負責將 MARC 書目記錄（Bibliographic Records）轉換為 FOLIO Instance 物件。它讀取 MARC 21 格式的原始檔案，依據 FOLIO 的 MARC-to-Instance 映射規則，產生符合 FOLIO Instance Schema 的 JSON 物件。

## 任務類型

- **類別**: Transform（轉換）
- **migration_task_type**: `BibsTransformer`
- **FOLIO 物件類型**: Instance
- **來源資料格式**: MARC 21 二進制檔（.mrc）

## 工作流程

```
MARC 21 檔案 (.mrc)
    ↓ 讀取 MARC Records
    ↓ 套用 MARC-to-Instance 映射規則
    ↓ 產生 FOLIO UUID（基於 legacy ID + namespace）
    ↓ 處理 HRID（人類可讀識別碼）
    ↓ 建立 Instance ID Map（legacy_id → folio_id）
FOLIO Instance JSON 檔案
```

## 呼叫的 FOLIO API

### 初始化階段（讀取參考資料）

| API Endpoint | HTTP Method | 用途 |
|---|---|---|
| `/mapping-rules/marc-bib` | GET | 取得 FOLIO 的 MARC 書目映射規則（定義 MARC 欄位如何對應到 Instance 屬性） |
| `/hrid-settings-storage/hrid-settings` | GET | 取得 HRID 計數器設定（用於產生新的 HRID） |
| `/instance-formats` | GET | 取得所有 Instance 格式參考資料 |
| `/instance-types` | GET | 取得所有 Instance 類型參考資料 |
| `/identifier-types` | GET | 取得所有識別碼類型（ISBN、ISSN 等） |
| `/contributor-types` | GET | 取得所有作者類型 |
| `/contributor-name-types` | GET | 取得作者名稱類型 |
| `/classification-types` | GET | 取得分類號類型（DDC、LCC 等） |
| `/instance-note-types` | GET | 取得 Instance 附註類型 |
| `/alternative-title-types` | GET | 取得替代題名類型 |
| `/electronic-access-relationships` | GET | 取得電子存取關係類型 |
| `/modes-of-issuance` | GET | 取得出版模式 |
| `/nature-of-content-terms` | GET | 取得內容性質術語 |
| `/statistical-codes` | GET | 取得統計代碼（若有設定 statistical_codes_map_file_name） |

### 結束階段

| API Endpoint | HTTP Method | 用途 |
|---|---|---|
| `/hrid-settings-storage/hrid-settings` | PUT | 更新 HRID 計數器（若 `update_hrid_settings: true`） |

### GitHub（非 FOLIO API）

| 來源 | 用途 |
|---|---|
| `folio-org/mod-inventory-storage/ramls/instance.json` | 下載 Instance JSON Schema（用於驗證輸出格式） |

## 輸入檔案

| 檔案 | 來源 | 說明 |
|---|---|---|
| `*.mrc` | `source_data/instances/` | MARC 21 書目記錄檔 |
| `statistical_codes.tsv` | `mapping_files/`（選用） | 統計代碼對應表 |

## 輸出檔案

| 檔案 | 路徑 | 說明 |
|---|---|---|
| `folio_instances.json` | `results/` | FOLIO Instance JSON（每行一筆） |
| `instance_id_map.json` | `results/` | Legacy ID → FOLIO ID 對應表（供 Holdings 使用） |
| `marc_xml_*` | `results/` | 處理後的 MARC XML（若 create_source_records=true） |
| `instance_transformation.md` | `reports/` | 轉換報告 |

## 關鍵設定

```json
{
    "name": "transform_bibs",
    "migration_task_type": "BibsTransformer",
    "hrid_handling": "default",
    "files": [{"file_name": "bibs.mrc", "suppress": false}],
    "ils_flavour": "tag001",
    "create_source_records": true,
    "reset_hrid_settings": false,
    "update_hrid_settings": true
}
```

### 設定說明

- **ils_flavour**: 決定如何提取 Legacy BIB ID
  - `tag001`: 使用 001 欄位（最常見）
  - `voyager`, `sierra`, `aleph`, `koha` 等: 各 ILS 專用邏輯
  - `custom`: 搭配 `custom_bib_id_field` 自定義
- **hrid_handling**: `default`（FOLIO 產生新 HRID）或 `preserve001`（保留 001 作為 HRID）
- **create_source_records**: 是否在 Source Record Storage 保留原始 MARC

## 注意事項

- BibsTransformer 產出的 `instance_id_map.json` 是 HoldingsCsvTransformer 的必要輸入
- 執行順序：必須在 Holdings/Items Transform 之前完成
- 大量 MARC 記錄會佔用較多記憶體，建議分批處理
